import os, re, uuid, hmac, hashlib, time
from pathlib import Path
from datetime import datetime
from functools import wraps
from urllib.parse import quote
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

def _find_customer_dir():
    configured = os.getenv('CUSTOMER_APP_DIR', '').strip()
    if configured:
        return os.path.abspath(configured)
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath(os.path.join(here, '..', 'customer')),  # combined project layout
        os.path.abspath(os.path.join(here, '..', 'navnidh_traders')),
        os.path.abspath(os.path.join(os.path.dirname(here), 'navnidh_traders')),
        os.path.abspath(os.path.join(here, '..', '..', 'navnidh_traders')),
    ]
    # Common local setup: admin is on D:\k while customer is D:\navnidh_traders.
    drive_root = os.path.splitdrive(here)[0] + os.sep
    candidates.append(os.path.join(drive_root, 'navnidh_traders'))
    for c in candidates:
        if os.path.isfile(os.path.join(c, 'app.py')) and os.path.isdir(os.path.join(c, 'static')):
            return c
    return candidates[0]

def _database_url():
    if os.getenv('DATABASE_URL'):
        value = os.getenv('DATABASE_URL').strip()
        # Render may still expose the legacy postgres:// scheme. SQLAlchemy 2.x expects postgresql://.
        if value.startswith('postgres://'):
            value = 'postgresql://' + value[len('postgres://'):]
        return value
    customer_dir = _find_customer_dir()
    # Match the customer's Flask-SQLAlchemy relative SQLite default.
    db_candidates = [os.path.join(customer_dir, 'instance', 'navnidh.db'),
                     os.path.join(customer_dir, 'navnidh.db')]
    db_path = next((p for p in db_candidates if os.path.isfile(p)), db_candidates[0])
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return 'sqlite:///' + os.path.abspath(db_path).replace('\\', '/')

def _upload_dir():
    configured = os.getenv('SHARED_UPLOAD_DIR', '').strip()
    if configured:
        return os.path.abspath(configured)
    customer_dir = _find_customer_dir()
    return os.path.abspath(os.path.join(customer_dir, 'static', 'uploads'))

app.config.update(
    SECRET_KEY=os.getenv('ADMIN_SECRET_KEY') or os.getenv('SECRET_KEY'),
    SQLALCHEMY_DATABASE_URI=_database_url(),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_NAME='navnidh_admin_session',
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '0').lower() in ('1','true','yes'),
    PERMANENT_SESSION_LIFETIME=3600,
    MAX_CONTENT_LENGTH=4 * 1024 * 1024,
    UPLOAD_DIR=_upload_dir()
)
CUSTOMER_BASE_URL = os.getenv('CUSTOMER_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')  # public invoice link for customers
if not app.config['SECRET_KEY']:
    raise RuntimeError('ADMIN_SECRET_KEY is missing. Run setup.bat to generate secure local configuration.')

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
os.makedirs(app.config['UPLOAD_DIR'], exist_ok=True)
STATUSES = ['Pending', 'Confirmed', 'Processing', 'Shipped', 'Delivered', 'Cancelled']

class User(db.Model):
    __tablename__='users'
    id=db.Column(db.Integer, primary_key=True)
    name=db.Column(db.String(100), nullable=False)
    email=db.Column(db.String(150), unique=True, index=True, nullable=False)
    password_hash=db.Column(db.String(255), nullable=False)
    is_admin=db.Column(db.Boolean, default=False)
    created_at=db.Column(db.DateTime, default=datetime.utcnow)

class Category(db.Model):
    __tablename__='categories'
    id=db.Column(db.Integer, primary_key=True)
    name=db.Column(db.String(80), nullable=False)
    slug=db.Column(db.String(90), unique=True, index=True, nullable=False)
    description=db.Column(db.String(200))
    color=db.Column(db.String(7), default='#8b5e3c')
    products=db.relationship('Product', backref='category')

class Product(db.Model):
    __tablename__='products'
    id=db.Column(db.Integer, primary_key=True)
    name=db.Column(db.String(150), nullable=False, index=True)
    slug=db.Column(db.String(170), unique=True, index=True, nullable=False)
    category_id=db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False, index=True)
    brand=db.Column(db.String(80), default='Navnidh')
    description=db.Column(db.Text)
    specs=db.Column(db.Text)
    price=db.Column(db.Integer, nullable=False)
    discount_price=db.Column(db.Integer)
    stock=db.Column(db.Integer, default=10)
    rating=db.Column(db.Float, default=4.5)
    image=db.Column(db.String(200))
    featured=db.Column(db.Boolean, default=False)
    bestseller=db.Column(db.Boolean, default=False)
    is_new=db.Column(db.Boolean, default=False)
    created_at=db.Column(db.DateTime, default=datetime.utcnow)
    @property
    def now_price(self): return self.discount_price or self.price
    @property
    def off(self): return round(100 - self.now_price*100/self.price) if self.discount_price else 0

class Order(db.Model):
    __tablename__='orders'
    id=db.Column(db.Integer, primary_key=True)
    user_id=db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    name=db.Column(db.String(100)); phone=db.Column(db.String(15)); email=db.Column(db.String(150))
    address=db.Column(db.String(300)); city=db.Column(db.String(80)); state=db.Column(db.String(80)); pincode=db.Column(db.String(10)); notes=db.Column(db.String(300))
    payment=db.Column(db.String(40)); status=db.Column(db.String(20), default='Pending', index=True); total=db.Column(db.Integer)
    gateway_order_id=db.Column(db.String(100), unique=True, index=True)
    gateway_payment_id=db.Column(db.String(100), unique=True, index=True)
    payment_status=db.Column(db.String(30), default='unpaid', index=True)
    invoice_token = db.Column(db.String(64), index=True)
    stock_deducted = db.Column(db.Boolean, default=False, nullable=False)
    created_at=db.Column(db.DateTime, default=datetime.utcnow)
    items=db.relationship('OrderItem', backref='order', cascade='all, delete-orphan')

class OrderItem(db.Model):
    __tablename__='order_items'
    id=db.Column(db.Integer, primary_key=True)
    order_id=db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    product_id=db.Column(db.Integer, db.ForeignKey('products.id', ondelete='SET NULL'))
    name=db.Column(db.String(150)); price=db.Column(db.Integer); qty=db.Column(db.Integer)

class Contact(db.Model):
    __tablename__='contacts'
    id=db.Column(db.Integer, primary_key=True)
    name=db.Column(db.String(100)); email=db.Column(db.String(150)); message=db.Column(db.Text)
    created_at=db.Column(db.DateTime, default=datetime.utcnow)
    status=db.Column(db.String(20), default='Open', index=True)
    admin_note=db.Column(db.Text)


def ensure_schema():
    """Use the customer's existing schema; only create missing tables/columns when needed."""
    with app.app_context():
        db.create_all()
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        if 'orders' in inspector.get_table_names():
            existing = {c['name'] for c in inspector.get_columns('orders')}
            additions = {
                'gateway_order_id': 'VARCHAR(100)',
                'gateway_payment_id': 'VARCHAR(100)',
                'payment_status': "VARCHAR(30) DEFAULT 'unpaid'",
                'invoice_token': 'VARCHAR(64)',
                'stock_deducted': "BOOLEAN DEFAULT FALSE",
            }
            for name, definition in additions.items():
                if name not in existing:
                    db.session.execute(text(f'ALTER TABLE orders ADD COLUMN {name} {definition}'))
            db.session.commit()
        if 'contacts' in inspector.get_table_names():
            existing = {c['name'] for c in inspector.get_columns('contacts')}
            additions = {'status': "VARCHAR(20) DEFAULT 'Open'", 'admin_note': 'TEXT'}
            for name, definition in additions.items():
                if name not in existing:
                    db.session.execute(text(f'ALTER TABLE contacts ADD COLUMN {name} {definition}'))
            db.session.commit()

def initialize_database():
    """Connect to the customer's database and ensure one usable admin account exists."""
    ensure_schema()
    with app.app_context():
        from sqlalchemy import text
        db.session.execute(text("UPDATE contacts SET status='Open' WHERE status IS NULL")); db.session.commit()
        email = os.getenv('ADMIN_EMAIL', '').strip().lower()
        password = os.getenv('ADMIN_PASSWORD', '')
        if not email or not password or len(password) < 12:
            raise RuntimeError('Set ADMIN_EMAIL and an ADMIN_PASSWORD of at least 12 characters in admin/.env.')
        admin = User.query.filter_by(email=email).first()
        if not admin:
            admin = User(name=os.getenv('ADMIN_NAME', 'Navnidh Admin'), email=email,
                         password_hash=generate_password_hash(password), is_admin=True)
            db.session.add(admin); db.session.commit()
        elif not admin.is_admin:
            admin.is_admin = True; db.session.commit()
        # Rotate the configured admin password once after first setup. A marker prevents
        # profile password changes from being overwritten on every subsequent restart.
        marker = Path(app.root_path).parent / 'customer' / 'instance' / '.admin-password-initialized'
        marker.parent.mkdir(parents=True, exist_ok=True)
        if not marker.exists():
            admin.password_hash = generate_password_hash(password)
            admin.is_admin = True
            db.session.commit()
            marker.write_text('initialized\n', encoding='utf-8')


def slugify(s): return re.sub(r'[^a-z0-9]+','-',s.lower()).strip('-')
def normalize_phone(phone):
    p=re.sub(r'\D','',phone or '')
    if len(p)==10: p='91'+p
    if p.startswith('0') and len(p)==11: p='91'+p[1:]
    return p

def wa_order_url(o):
    phone=normalize_phone(o.phone)
    if not o.invoice_token:
        o.invoice_token = uuid.uuid4().hex + uuid.uuid4().hex
        db.session.commit()
    lines=[f'Hello {o.name},',f'Navnidh Traders order #{o.id}',f'Amount: ₹{o.total:,}',f'Status: {o.status}',f'Payment: {o.payment}',f'Payment status: {o.payment_status or "unpaid"}',f'Bill: {CUSTOMER_BASE_URL}/order/{o.id}/invoice?token={o.invoice_token}']
    msg=quote('\n'.join(lines))
    return f'https://wa.me/{phone}?text={msg}' if phone else f'https://wa.me/?text={msg}'

def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get('admin_uid'): return redirect(url_for('login', next=request.path))
        u=db.session.get(User, session['admin_uid'])
        if not u or not u.is_admin:
            session.clear(); return redirect(url_for('login', next=request.full_path))
        return f(*args, **kwargs)
    return wrapped

@app.context_processor
def inject():
    return {'admin_user': db.session.get(User, session.get('admin_uid',0)), 'wa_order_url': wa_order_url}

@app.route('/bridge-login')
def bridge_login():
    # Accept only a short-lived, signed hand-off from the Customer login.
    try:
        uid = int(request.args.get('uid', '0'))
        ts = int(request.args.get('ts', '0'))
    except (TypeError, ValueError):
        abort(403)
    token = request.args.get('token', '')
    if not uid or not token or abs(int(time.time()) - ts) > 60:
        abort(403)
    secret_value = os.getenv('ADMIN_BRIDGE_SECRET', '')
    if not secret_value: abort(503)
    secret = secret_value.encode()
    payload = f'{uid}:{ts}'
    expected = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(token, expected):
        abort(403)
    u = db.session.get(User, uid)
    if not u or not u.is_admin:
        abort(403)
    session.clear()
    session['admin_uid'] = u.id
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        u=User.query.filter_by(email=email, is_admin=True).first()
        if u and check_password_hash(u.password_hash,password):
            session.clear(); session['admin_uid']=u.id
            return redirect(request.form.get('next') or url_for('dashboard'))
        flash('Invalid admin email or password.','danger')
    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/')
@admin_required
def dashboard():
    revenue=db.session.query(db.func.coalesce(db.func.sum(Order.total),0)).filter(Order.status!='Cancelled').scalar() or 0
    stats=[('Products',Product.query.count(),'bi-box-seam'),('Orders',Order.query.count(),'bi-bag-check'),('Pending',Order.query.filter_by(status='Pending').count(),'bi-hourglass-split'),('Delivered',Order.query.filter_by(status='Delivered').count(),'bi-check2-circle'),('Customers',User.query.filter_by(is_admin=False).count(),'bi-people'),('Revenue',f'₹{revenue:,}','bi-currency-rupee')]
    recent=Order.query.order_by(Order.id.desc()).limit(8).all()
    low=Product.query.filter(Product.stock<=5).order_by(Product.stock.asc()).limit(8).all()
    return render_template('dashboard.html',stats=stats,recent=recent,low=low)

@app.route('/products')
@admin_required
def products():
    q=Product.query
    term=request.args.get('q','').strip()
    if term: q=q.filter(Product.name.ilike(f'%{term}%'))
    cid=request.args.get('category',type=int)
    if cid: q=q.filter_by(category_id=cid)
    stock=request.args.get('stock')
    if stock=='low': q=q.filter(Product.stock<=5)
    elif stock=='out': q=q.filter(Product.stock<=0)
    return render_template('products.html', products=q.order_by(Product.id.desc()).all(), categories=Category.query.order_by(Category.name).all(), term=term, selected_category=cid, stock_filter=stock)

@app.route('/products/new', methods=['GET','POST'])
@app.route('/products/<int:pid>/edit', methods=['GET','POST'])
@admin_required
def product_form(pid=None):
    p=db.session.get(Product,pid) if pid else None
    if pid and not p: abort(404)
    if request.method=='POST':
        f=request.form
        try:
            name=f.get('name','').strip(); price=int(f.get('price','0')); cat=int(f.get('category_id','0')); stock=int(f.get('stock','0'))
            disc=int(f['discount_price']) if f.get('discount_price') else None
            rating=float(f.get('rating') or 4.5)
            if not name or price<=0 or stock<0 or (disc is not None and (disc<=0 or disc>=price)) or not db.session.get(Category,cat): raise ValueError
            if not 0<=rating<=5: raise ValueError
        except (ValueError,TypeError):
            flash('Check name, category, price, discount, stock and rating.','danger')
            return render_template('product_form.html',p=p,categories=Category.query.order_by(Category.name).all())
        if not p:
            base=slugify(name) or 'product'; slug=base
            n=2
            while Product.query.filter_by(slug=slug).first(): slug=f'{base}-{n}'; n+=1
            p=Product(slug=slug); db.session.add(p)
        p.name=name; p.category_id=cat; p.brand=f.get('brand','Navnidh')[:80]; p.price=price; p.discount_price=disc; p.stock=stock; p.rating=rating
        p.description=f.get('description',''); p.specs=f.get('specs',''); p.featured=bool(f.get('featured')); p.bestseller=bool(f.get('bestseller')); p.is_new=bool(f.get('is_new'))
        image_url=f.get('image_url','').strip()
        if image_url: p.image=image_url[:200]
        up=request.files.get('image')
        if up and up.filename:
            ext=secure_filename(up.filename).rsplit('.',1)[-1].lower()
            if ext not in ('jpg','jpeg','png','webp'):
                flash('Only JPG, JPEG, PNG or WEBP images are allowed.','danger'); return render_template('product_form.html',p=p,categories=Category.query.order_by(Category.name).all())
            fn=uuid.uuid4().hex+'.'+ext; up.save(os.path.join(app.config['UPLOAD_DIR'],fn)); p.image=fn
        db.session.commit(); flash('Product saved successfully.','success'); return redirect(url_for('products'))
    return render_template('product_form.html',p=p,categories=Category.query.order_by(Category.name).all())

@app.route('/products/<int:pid>/delete',methods=['POST'])
@admin_required
def delete_product(pid):
    p=db.get_or_404(Product,pid); OrderItem.query.filter_by(product_id=pid).update({'product_id':None}); db.session.delete(p); db.session.commit(); flash('Product deleted.','success'); return redirect(url_for('products'))

@app.route('/categories',methods=['GET','POST'])
@admin_required
def categories():
    if request.method=='POST':
        name=request.form.get('name','').strip(); desc=request.form.get('description','').strip(); color=request.form.get('color','#8b5e3c')
        if not name: flash('Category name is required.','danger')
        elif Category.query.filter(db.or_(Category.name.ilike(name),Category.slug==slugify(name))).first(): flash('Category already exists.','danger')
        else:
            db.session.add(Category(name=name[:80],slug=slugify(name),description=desc[:200],color=color if re.fullmatch(r'#[0-9a-fA-F]{6}',color) else '#8b5e3c')); db.session.commit(); flash('Category added.','success')
    return render_template('categories.html',categories=Category.query.order_by(Category.name).all())

@app.route('/categories/<int:cid>/delete',methods=['POST'])
@admin_required
def delete_category(cid):
    c=db.get_or_404(Category,cid)
    if Product.query.filter_by(category_id=cid).first(): flash('Move/delete the products in this category first.','warning')
    else: db.session.delete(c); db.session.commit(); flash('Category deleted.','success')
    return redirect(url_for('categories'))

@app.route('/orders')
@admin_required
def orders():
    q=Order.query
    term=request.args.get('q','').strip(); status=request.args.get('status',''); pay=request.args.get('payment','')
    if term: q=q.filter(db.or_(Order.name.ilike(f'%{term}%'),Order.email.ilike(f'%{term}%'),Order.phone.ilike(f'%{term}%')))
    if status: q=q.filter_by(status=status)
    if pay: q=q.filter(Order.payment.ilike(f'%{pay}%'))
    return render_template('orders.html',orders=q.order_by(Order.id.desc()).all(),statuses=STATUSES,term=term,status_filter=status,payment_filter=pay)

@app.route('/orders/<int:oid>')
@admin_required
def order_detail(oid): return render_template('order_detail.html',o=db.get_or_404(Order,oid),wa_url=wa_order_url(db.get_or_404(Order,oid)))

@app.route('/orders/<int:oid>/status',methods=['POST'])
@admin_required
def order_status(oid):
    o=db.get_or_404(Order,oid); s=request.form.get('status')
    if s not in STATUSES:
        flash('Invalid status.','danger')
    elif s == 'Cancelled' and o.status != 'Cancelled':
        # Return previously deducted stock once when an order is cancelled.
        if o.stock_deducted:
            for item in o.items:
                p=db.session.get(Product,item.product_id) if item.product_id else None
                if p: p.stock += item.qty or 0
            o.stock_deducted=False
        o.status='Cancelled'; db.session.commit()
        flash(f'Order #{o.id} cancelled. Stock was restored when it had previously been deducted. If an online payment was captured, process any refund separately in the payment provider.','warning')
    elif o.status == 'Cancelled' and s != 'Cancelled':
        # Re-opening a cancelled order must re-check inventory before reserving it again.
        unavailable=[]
        for item in o.items:
            p=db.session.get(Product,item.product_id) if item.product_id else None
            if p and p.stock < (item.qty or 0): unavailable.append(p.name)
        if unavailable:
            flash('Cannot reopen order: insufficient stock for ' + ', '.join(unavailable) + '.','danger')
        else:
            for item in o.items:
                p=db.session.get(Product,item.product_id) if item.product_id else None
                if p: p.stock -= item.qty or 0
            o.stock_deducted=True; o.status=s; db.session.commit()
            flash(f'Order #{o.id} reopened as {s}; stock was checked and deducted.','success')
    else:
        o.status=s; db.session.commit(); flash(f'Order #{o.id} updated to {s}.','success')
    return redirect(request.referrer or url_for('orders'))

@app.route('/orders/<int:oid>/payment',methods=['POST'])
@admin_required
def order_payment(oid):
    o=db.get_or_404(Order,oid); ps=request.form.get('payment_status','')
    if ps in ('unpaid','created','paid','failed','cod'): o.payment_status=ps; db.session.commit(); flash('Payment status updated.','success')
    return redirect(request.referrer or url_for('order_detail',oid=oid))

@app.route('/orders/<int:oid>/invoice')
@admin_required
def invoice(oid): return render_template('invoice.html',o=db.get_or_404(Order,oid))

@app.route('/customers')
@admin_required
def customers():
    term=request.args.get('q','').strip(); q=User.query.filter_by(is_admin=False)
    if term: q=q.filter(db.or_(User.name.ilike(f'%{term}%'),User.email.ilike(f'%{term}%')))
    users=q.order_by(User.id.desc()).all()
    customer_rows=[]
    for u in users:
        os_q=Order.query.filter_by(user_id=u.id)
        order_count=os_q.count()
        spent=db.session.query(db.func.coalesce(db.func.sum(Order.total),0)).filter(Order.user_id==u.id, Order.status!='Cancelled').scalar() or 0
        last=os_q.order_by(Order.id.desc()).first()
        customer_rows.append({'user':u,'orders':order_count,'spent':spent,'last':last})
    return render_template('customers.html',customers=customer_rows,term=term)

@app.route('/help')
@admin_required
def customer_help():
    status=request.args.get('status','')
    q=Contact.query
    if status in ('Open','Resolved'): q=q.filter_by(status=status)
    return render_template('customer_help.html',messages=q.order_by(Contact.id.desc()).all(),status_filter=status)

@app.route('/help/<int:cid>/status',methods=['POST'])
@admin_required
def help_status(cid):
    c=db.get_or_404(Contact,cid); s=request.form.get('status')
    if s in ('Open','Resolved'):
        c.status=s; c.admin_note=request.form.get('admin_note','').strip()[:2000]; db.session.commit(); flash('Customer help request updated.','success')
    return redirect(request.referrer or url_for('customer_help'))

@app.route('/profile',methods=['GET','POST'])
@admin_required
def profile():
    u=db.session.get(User,session['admin_uid'])
    if request.method=='POST':
        name=request.form.get('name','').strip(); newpass=request.form.get('new_password','')
        if not name: flash('Name is required.','danger')
        elif newpass and len(newpass)<8: flash('New password must be at least 8 characters.','danger')
        else:
            u.name=name[:100]
            if newpass: u.password_hash=generate_password_hash(newpass)
            db.session.commit(); flash('Profile updated.','success')
    return render_template('profile.html',u=u)

@app.route('/media/<path:filename>')
@admin_required
def media(filename):
    # Serve the same product image folder used by the customer app.
    return send_from_directory(app.config['UPLOAD_DIR'], filename)

@app.route('/health')
def health(): return {'ok':True,'service':'navnidh-admin'}

@app.errorhandler(404)
def not_found(e): return render_template('404.html'),404

# Initialize tables before the first request so /login never fails on a fresh install.
initialize_database()

if __name__=='__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('ADMIN_PORT','5001')), debug=os.getenv('FLASK_DEBUG','0')=='1')
