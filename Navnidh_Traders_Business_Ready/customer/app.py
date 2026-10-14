import os, re, uuid, hashlib, hmac, time
from datetime import datetime
from functools import wraps
from urllib.parse import quote
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response, abort
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
try:
    import razorpay
except ImportError:
    razorpay = None
load_dotenv()

def normalize_database_url(value):
    """Normalize legacy Render PostgreSQL URLs for SQLAlchemy 2.x."""
    value = (value or 'sqlite:///navnidh.db').strip()
    if value.startswith('postgres://'):
        value = 'postgresql://' + value[len('postgres://'):]
    return value

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv('SECRET_KEY'),
    SQLALCHEMY_DATABASE_URI=normalize_database_url(os.getenv('DATABASE_URL')),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_NAME='navnidh_customer_session',  # separate from admin session cookie
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '0').lower() in ('1','true','yes'),
    PERMANENT_SESSION_LIFETIME=3600,
    MAX_CONTENT_LENGTH=4 * 1024 * 1024,
    UPLOAD_DIR=os.path.join(app.root_path, 'static', 'uploads'))
if not app.config['SECRET_KEY']:
    raise RuntimeError('SECRET_KEY is missing. Run setup.bat to generate secure local configuration.')

db = SQLAlchemy(app)
os.makedirs(app.config['UPLOAD_DIR'], exist_ok=True)
csrf = CSRFProtect(app)
WA = os.getenv('WHATSAPP_NUMBER', '91XXXXXXXXXX')
BUSINESS_NAME = os.getenv('BUSINESS_NAME', 'Navnidh Traders')
BUSINESS_PHONE = os.getenv('BUSINESS_PHONE', '')
BUSINESS_EMAIL = os.getenv('BUSINESS_EMAIL', '')
BUSINESS_ADDRESS = os.getenv('BUSINESS_ADDRESS', '')
BUSINESS_HOURS = os.getenv('BUSINESS_HOURS', '')
DELIVERY_POLICY = os.getenv('DELIVERY_POLICY', 'Delivery availability and charges are confirmed before order dispatch.')
WARRANTY_POLICY = os.getenv('WARRANTY_POLICY', 'Warranty depends on the product and supplier. Confirm the terms before purchase.')
SHIPPING_CHARGE = max(0, int(os.getenv('SHIPPING_CHARGE', '250') or 250))
FREE_DELIVERY_THRESHOLD = max(0, int(os.getenv('FREE_DELIVERY_THRESHOLD', '5000') or 5000))
STATUSES = ['Pending', 'Confirmed', 'Processing', 'Shipped', 'Delivered', 'Cancelled']
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET', '')
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) if razorpay and RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET else None

# ---------- Models ----------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(90), unique=True, index=True, nullable=False)
    description = db.Column(db.String(200))
    color = db.Column(db.String(7), default='#8b5e3c')
    products = db.relationship('Product', backref='category')

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    slug = db.Column(db.String(170), unique=True, index=True, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False, index=True)
    brand = db.Column(db.String(80), default='Navnidh')
    description = db.Column(db.Text)
    specs = db.Column(db.Text)  # one "Label: value" per line
    price = db.Column(db.Integer, nullable=False)
    discount_price = db.Column(db.Integer)
    stock = db.Column(db.Integer, default=10)
    rating = db.Column(db.Float, default=4.5)
    image = db.Column(db.String(200))
    featured = db.Column(db.Boolean, default=False)
    bestseller = db.Column(db.Boolean, default=False)
    is_new = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    @property
    def now_price(self): return self.discount_price or self.price
    @property
    def off(self): return round(100 - self.now_price * 100 / self.price) if self.discount_price else 0
    @property
    def img(self):
        if self.image and self.image.startswith(('http://', 'https://')):
            return self.image  # image URL entered in Admin
        return url_for('static', filename='uploads/' + self.image) if self.image else url_for('chair_svg', color=self.category.color[1:])
    @property
    def spec_list(self):
        return [l.split(':', 1) for l in (self.specs or '').splitlines() if ':' in l]

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    name = db.Column(db.String(100)); phone = db.Column(db.String(15)); email = db.Column(db.String(150))
    address = db.Column(db.String(300)); city = db.Column(db.String(80)); state = db.Column(db.String(80))
    pincode = db.Column(db.String(10)); notes = db.Column(db.String(300))
    payment = db.Column(db.String(40)); status = db.Column(db.String(20), default='Pending', index=True)
    total = db.Column(db.Integer)
    gateway_order_id = db.Column(db.String(100), unique=True, index=True)
    gateway_payment_id = db.Column(db.String(100), unique=True, index=True)
    payment_status = db.Column(db.String(30), default='unpaid', index=True)
    invoice_token = db.Column(db.String(64), index=True)
    stock_deducted = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', cascade='all, delete-orphan')

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='SET NULL'))
    name = db.Column(db.String(150)); price = db.Column(db.Integer); qty = db.Column(db.Integer)

class Contact(db.Model):
    __tablename__ = 'contacts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100)); email = db.Column(db.String(150)); message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Open', index=True)  # used by Admin > Customer Help
    admin_note = db.Column(db.Text)

# ---------- Helpers ----------
def slugify(s): return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')

def cart_items():
    out = []
    for pid, qty in session.get('cart', {}).items():
        p = db.session.get(Product, int(pid))
        if p: out.append((p, qty))
    return out

def totals(items):
    sub = sum(p.now_price * q for p, q in items)
    ship = 0 if (sub >= FREE_DELIVERY_THRESHOLD or sub == 0) else SHIPPING_CHARGE
    return sub, ship, sub + ship

def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        u = db.session.get(User, session.get('uid', 0))
        if not u or not u.is_admin: return redirect(url_for('login', next=request.path))
        return f(*a, **k)
    return w

def normalize_phone(phone):
    phone = re.sub(r'\D', '', phone or '')
    if phone.startswith('0') and len(phone) == 11:
        phone = '91' + phone[1:]
    elif len(phone) == 10:
        phone = '91' + phone
    return phone

def order_whatsapp_url(o):
    """Open the customer's WhatsApp chat with a complete bill summary and public invoice link."""
    phone = normalize_phone(o.phone)
    if not o.invoice_token:
        o.invoice_token = uuid.uuid4().hex + uuid.uuid4().hex
        db.session.commit()
    invoice_link = url_for('invoice', oid=o.id, token=o.invoice_token, _external=True)
    lines = [
        f"Hello {o.name},",
        f"Your Navnidh Traders order #{o.id} is confirmed.",
        "",
        "🧾 BILL / ORDER DETAILS",
        f"Order: #{o.id}",
        f"Amount: ₹{o.total:,}",
        f"Payment: {o.payment}",
        f"Payment Status: {o.payment_status.title() if o.payment_status else 'Unpaid'}",
        "",
        f"View your online bill: {invoice_link}",
        "",
        "Thank you for shopping with Navnidh Traders."
    ]
    message = '\n'.join(lines)
    if not phone:
        return f"https://wa.me/?text={quote(message)}"
    return f"https://wa.me/{phone}?text={quote(message)}"

def deduct_order_stock_once(o):
    """Idempotently deduct inventory when an order becomes payable/confirmed."""
    if o.stock_deducted:
        return
    for item in o.items:
        p = db.session.get(Product, item.product_id) if item.product_id else None
        if p:
            if p.stock < item.qty:
                raise ValueError(f'Insufficient stock for {p.name}; manual review/refund may be required.')
            p.stock -= item.qty
    o.stock_deducted = True

def create_gateway_order(o):
    if not razorpay_client:
        return None
    gateway_order = razorpay_client.order.create({
        'amount': int(o.total) * 100,
        'currency': 'INR',
        'receipt': f'NAV-{o.id}',
        'notes': {'order_id': str(o.id)}
    })
    o.gateway_order_id = gateway_order['id']
    o.payment_status = 'created'
    db.session.commit()
    return gateway_order

@app.context_processor
def inject():
    return dict(cart_count=sum(session.get('cart', {}).values()), nav_cats=Category.query.all(),
                wa_number=WA, business_name=BUSINESS_NAME, business_phone=BUSINESS_PHONE,
                business_email=BUSINESS_EMAIL, business_address=BUSINESS_ADDRESS, business_hours=BUSINESS_HOURS,
                delivery_policy=DELIVERY_POLICY, warranty_policy=WARRANTY_POLICY,
                shipping_charge=SHIPPING_CHARGE, free_delivery_threshold=FREE_DELIVERY_THRESHOLD,
                user=db.session.get(User, session.get('uid', 0)),
                wa_link=lambda n=None: f"https://wa.me/{WA}?text=" + quote(
                    f"Hello Navnidh Traders, I am interested in {n}. Please share price, availability and delivery details."
                    if n else "Hello Navnidh Traders, I would like to enquire about your chairs."))

@app.route('/img/<color>.svg')
def chair_svg(color):
    color = re.sub(r'[^0-9a-fA-F]', '', color)[:6] or '8b5e3c'
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"><rect width="400" height="400" fill="#f4efe9"/>
<ellipse cx="200" cy="350" rx="110" ry="14" fill="#0001"/><rect x="120" y="60" width="160" height="150" rx="40" fill="#{color}"/>
<rect x="105" y="200" width="190" height="45" rx="18" fill="#{color}" opacity=".85"/><rect x="193" y="245" width="14" height="70" fill="#333"/>
<path d="M200 315 L110 345 M200 315 L290 345 M200 315 L200 348" stroke="#333" stroke-width="10" stroke-linecap="round"/></svg>'''
    return Response(svg, mimetype='image/svg+xml', headers={'Cache-Control': 'public, max-age=86400'})

# ---------- Storefront ----------
@app.route('/')
def index():
    # Real manufacturer product photography for category cards (not generated SVG chair icons).
    # These are reference catalogue images; confirm commercial-use permission and exact variants.
    category_images = {
        'office-chairs': 'https://www.nilkamalhomes.com/cdn/shop/files/Giza_black_LS_1_800x_73d6a47e-3879-4e3c-972a-6e1fead13ef9.jpg?v=1728385490',
        'executive-chairs': 'https://www.nilkamalhomes.com/cdn/shop/files/KyotobrownLS_800x_d6afc567-7229-439d-ae80-0679cadea744.jpg?v=1729509182',
        'gaming-chairs': 'https://www.nilkamalhomes.com/cdn/shop/files/Alba_HB_LS.jpg?v=1691735760',
        'study-chairs': 'https://www.nilkamalhomes.com/cdn/shop/products/AMAZECHAIRWITHTABLETBLACK_LS.jpg?v=1637752554',
        'dining-chairs': 'https://www.nilkamalhomes.com/cdn/shop/products/Zinglifestyle.jpg?v=1635502859',
        'visitor-chairs': 'https://www.nilkamalhomes.com/cdn/shop/products/Contract_Chair_02_CONTRACT02PVCABLK_LF_With_Arm.jpg?v=1595670423',
        'plastic-chairs': 'https://www.nilkamalhomes.com/cdn/shop/products/CONTRACT_02_SOFT_PVC_WITHOUT_ARM_BLACK_CONTRACT02PVCBLK_LS.jpg?v=1595670422',
        'reception-chairs': 'https://www.nilkamalhomes.com/cdn/shop/products/GLORYMIDBACKOFFICECHAIRBLACK_FLOCGLORYMBBLACK_00.jpg?v=1635101966',
    }
    return render_template('index.html', cats=Category.query.all(), category_images=category_images,
        featured=Product.query.filter_by(featured=True).limit(8).all(),
        best=Product.query.filter_by(bestseller=True).limit(4).all())

@app.route('/shop')
def shop():
    a = request.args
    q = Product.query.join(Category)
    s = a.get('q', '').strip()
    if s:
        l = f'%{s}%'
        q = q.filter(db.or_(Product.name.ilike(l), Product.description.ilike(l), Product.specs.ilike(l),
                            Product.brand.ilike(l), Category.name.ilike(l)))
    if a.get('category'): q = q.filter(Category.slug == a['category'])
    if a.get('max', type=int): q = q.filter(db.func.coalesce(Product.discount_price, Product.price) <= a.get('max', type=int))
    if a.get('rating', type=float): q = q.filter(Product.rating >= a.get('rating', type=float))
    if a.get('instock'): q = q.filter(Product.stock > 0)
    current_price = db.func.coalesce(Product.discount_price, Product.price)
    order = {'new': Product.created_at.desc(), 'low': current_price.asc(), 'high': current_price.desc()}.get(a.get('sort'), Product.bestseller.desc())
    pg = q.order_by(order, Product.id).paginate(page=a.get('page', 1, type=int), per_page=12, error_out=False)
    args = {k: v for k, v in a.items() if k != 'page' and v}
    return render_template('shop.html', pg=pg, args=args, cats=Category.query.all())

@app.route('/category/<slug>')
def category(slug):
    get_or_404 = Category.query.filter_by(slug=slug).first_or_404()
    return redirect(url_for('shop', category=get_or_404.slug))

@app.route('/product/<slug>')
def product(slug):
    p = Product.query.filter_by(slug=slug).first_or_404()
    rel = Product.query.filter(Product.category_id == p.category_id, Product.id != p.id).limit(4).all()
    return render_template('product.html', p=p, rel=rel)

@app.route('/api/suggest')
def suggest():
    s = request.args.get('q', '').strip()
    if len(s) < 2: return jsonify([])
    return jsonify([p.name for p in Product.query.filter(Product.name.ilike(f'%{s}%')).limit(6)])

@app.route('/cart')
def cart():
    items = cart_items()
    return render_template('cart.html', items=items, t=totals(items))

@app.route('/cart/add/<int:pid>', methods=['POST'])
def cart_add(pid):
    p = db.get_or_404(Product, pid)
    qty = max(1, min(request.form.get('qty', 1, type=int), 20))
    if p.stock < 1:
        flash('Sorry, this item is out of stock.', 'danger'); return redirect(request.referrer or url_for('shop'))
    c = session.get('cart', {}); c[str(pid)] = min(c.get(str(pid), 0) + qty, p.stock)
    session['cart'] = c
    flash(f'{p.name} added to cart.', 'success')
    if request.form.get('buy'): return redirect(url_for('checkout'))
    return redirect(request.referrer or url_for('cart'))

@app.route('/cart/update/<int:pid>', methods=['POST'])
def cart_update(pid):
    c = session.get('cart', {}); qty = request.form.get('qty', 1, type=int)
    if qty <= 0: c.pop(str(pid), None)
    elif str(pid) in c:
        p = db.session.get(Product, pid)
        c[str(pid)] = min(qty, 20, p.stock if p else 0)
        if c[str(pid)] <= 0: c.pop(str(pid), None)
    session['cart'] = c
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    items = cart_items()
    if not items:
        flash('Your cart is empty.', 'warning'); return redirect(url_for('shop'))
    t = totals(items); f = request.form
    if request.method == 'POST':
        err = []
        for k in ('name', 'address', 'city', 'state'):
            if not f.get(k, '').strip(): err.append(f'{k.title()} is required.')
        if not re.fullmatch(r'[6-9]\d{9}', f.get('phone', '')): err.append('Enter a valid 10-digit mobile number.')
        if not re.fullmatch(r'\d{6}', f.get('pincode', '')): err.append('Enter a valid 6-digit pincode.')
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', f.get('email', '')): err.append('Enter a valid email.')
        method = f.get('payment', 'cod')
        if method == 'online' and not razorpay_client:
            err.append('Online payment is not configured yet. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in Render Environment Variables.')
        if err:
            for e in err: flash(e, 'danger')
            return render_template('checkout.html', items=items, t=t, f=f)

        # Re-check stock at the moment the order is created.
        for p, q in items:
            if p.stock < q:
                flash(f'Sorry, only {p.stock} unit(s) of {p.name} are available.', 'danger')
                return render_template('checkout.html', items=items, t=t, f=f)

        o = Order(user_id=session.get('uid'), name=f['name'][:100], phone=f['phone'], email=f['email'][:150],
                  address=f['address'][:300], city=f['city'][:80], state=f['state'][:80], pincode=f['pincode'],
                  notes=f.get('notes', '')[:300], total=t[2],
                  payment='Online Payment (Razorpay)' if method == 'online' else 'Cash on Delivery',
                  status='Pending', payment_status='unpaid', invoice_token=uuid.uuid4().hex + uuid.uuid4().hex)
        for p, q in items:
            o.items.append(OrderItem(product_id=p.id, name=p.name, price=p.now_price, qty=q))
        db.session.add(o); db.session.commit()

        if method == 'online':
            try:
                create_gateway_order(o)
            except Exception:
                db.session.rollback()
                db.session.delete(o)
                db.session.commit()
                flash('Online payment gateway could not be started. Please try again.', 'danger')
                return render_template('checkout.html', items=items, t=t, f=f)
            session['pending_order_id'] = o.id
            return render_template('payment.html', o=o, razorpay_key=RAZORPAY_KEY_ID, gateway_order_id=o.gateway_order_id)

        # COD order is placed immediately, so reserve stock now.
        for p, q in items:
            p.stock = max(0, p.stock - q)
        o.stock_deducted = True
        o.payment_status = 'cod'
        db.session.commit(); session['cart'] = {}; session['last_order_id'] = o.id
        return redirect(url_for('order_done', oid=o.id))
    return render_template('checkout.html', items=items, t=t, f=f)

@app.route('/payment/verify/<int:oid>', methods=['POST'])
def verify_payment(oid):
    o = db.get_or_404(Order, oid)
    if o.payment_status == 'paid':
        return jsonify(ok=True, redirect=url_for('order_done', oid=o.id))
    if not razorpay_client or not o.gateway_order_id:
        return jsonify(ok=False, message='Payment gateway is not configured.'), 400
    data = request.get_json(silent=True) or {}
    required = ('razorpay_payment_id', 'razorpay_order_id', 'razorpay_signature')
    if any(not data.get(k) for k in required):
        return jsonify(ok=False, message='Incomplete payment response.'), 400
    if data['razorpay_order_id'] != o.gateway_order_id:
        return jsonify(ok=False, message='Payment order mismatch.'), 400
    try:
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': data['razorpay_order_id'],
            'razorpay_payment_id': data['razorpay_payment_id'],
            'razorpay_signature': data['razorpay_signature']
        })
        # Razorpay signature verification is the server-side authenticity check.
        o.gateway_payment_id = data['razorpay_payment_id']
        o.payment_status = 'paid'
        o.status = 'Confirmed'
        deduct_order_stock_once(o)
        db.session.commit()
        session.pop('pending_order_id', None); session['cart'] = {}; session['last_order_id'] = o.id
        return jsonify(ok=True, redirect=url_for('order_done', oid=o.id))
    except Exception:
        db.session.rollback()
        return jsonify(ok=False, message='Payment verification failed. No order was marked as paid.'), 400

@app.route('/payment/razorpay-webhook', methods=['POST'])
@csrf.exempt
def razorpay_webhook():
    """Verify Razorpay webhook signatures and process captured/paid events idempotently."""
    webhook_secret = os.getenv('RAZORPAY_WEBHOOK_SECRET', '')
    signature = request.headers.get('X-Razorpay-Signature', '')
    if not webhook_secret or not signature:
        return jsonify(ok=False, message='Webhook is not configured.'), 503
    body = request.get_data()
    expected = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return jsonify(ok=False, message='Invalid webhook signature.'), 400
    payload = request.get_json(silent=True) or {}
    event = payload.get('event', '')
    if event not in ('payment.captured', 'order.paid'):
        return jsonify(ok=True, ignored=True)
    entity = (payload.get('payload', {}).get('payment', {}).get('entity') or
              payload.get('payload', {}).get('order', {}).get('entity') or {})
    gateway_order_id = entity.get('order_id') or entity.get('id')
    payment_id = entity.get('id') if entity.get('order_id') else None
    if not gateway_order_id:
        return jsonify(ok=False, message='Missing gateway order ID.'), 400
    o = Order.query.filter_by(gateway_order_id=gateway_order_id).first()
    if not o:
        # A webhook can arrive before a newly created order is visible during deploys;
        # return a retryable error rather than silently losing the event.
        return jsonify(ok=False, message='Order not found.'), 404
    if o.payment_status != 'paid':
        o.payment_status = 'paid'
        o.status = 'Confirmed'
        if payment_id and not o.gateway_payment_id:
            o.gateway_payment_id = payment_id
        try:
            deduct_order_stock_once(o)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            o = db.session.get(Order, o.id)
            o.payment_status = 'paid'
            o.status = 'Pending'
            if payment_id and not o.gateway_payment_id:
                o.gateway_payment_id = payment_id
            marker = '[URGENT: PAYMENT CAPTURED; STOCK/REFUND REVIEW REQUIRED]'
            o.notes = ((o.notes + '\n') if o.notes else '') + marker
            db.session.commit()
            app.logger.critical('Paid order %s requires stock/refund review: %s', o.id, exc)
            # Acknowledge the signed event to prevent repeated webhook retries; admin must review it.
            return jsonify(ok=True, manual_review=True), 200
    return jsonify(ok=True)

@app.route('/payment/failed/<int:oid>')
def payment_failed(oid):
    o = db.get_or_404(Order, oid)
    if o.payment_status != 'paid':
        o.payment_status = 'failed'; db.session.commit()
    return render_template('payment_failed.html', o=o)

@app.route('/order/<int:oid>/thanks')
def order_done(oid):
    o = db.get_or_404(Order, oid)
    current = db.session.get(User, session.get('uid', 0))
    if session.get('last_order_id') != o.id and not (current and o.user_id == current.id):
        abort(403)
    if not o.invoice_token:
        o.invoice_token = uuid.uuid4().hex + uuid.uuid4().hex
        db.session.commit()
    return render_template('thanks.html', o=o, wa_url=order_whatsapp_url(o), invoice_token=o.invoice_token)

@app.route('/order/<int:oid>/invoice')
def invoice(oid):
    o = db.get_or_404(Order, oid)
    current = db.session.get(User, session.get('uid', 0))
    token = request.args.get('token', '')
    if not o.invoice_token:
        o.invoice_token = uuid.uuid4().hex + uuid.uuid4().hex
        db.session.commit()
    if not hmac.compare_digest(token, o.invoice_token) and not (current and o.user_id == current.id) and session.get('last_order_id') != o.id:
        abort(403)
    return render_template('invoice.html', o=o, wa_url=order_whatsapp_url(o))

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        f = request.form
        if f.get('name', '').strip() and f.get('message', '').strip():
            db.session.add(Contact(name=f['name'][:100], email=f.get('email', '')[:150], message=f['message'][:2000]))
            db.session.commit(); flash('Thank you! We will get back to you soon.', 'success')
            return redirect(url_for('contact'))
        flash('Please enter your name and message.', 'danger')
    return render_template('contact.html')

@app.route('/about')
def about(): return render_template('about.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = User.query.filter_by(email=request.form.get('email', '').lower().strip()).first()
        if u and check_password_hash(u.password_hash, request.form.get('password', '')):
            cart = session.get('cart', {})
            if u.is_admin:
                # Admin credentials entered on the customer login are handed off to the
                # separate Admin app using a short-lived signed bridge token.
                ts = str(int(time.time()))
                secret_value = os.getenv('ADMIN_BRIDGE_SECRET', '')
                if not secret_value: abort(503)
                secret = secret_value.encode()
                payload = f'{u.id}:{ts}'
                token = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
                admin_url = os.getenv('ADMIN_BASE_URL', 'http://127.0.0.1:5001').rstrip('/')
                session.clear()
                return redirect(f'{admin_url}/bridge-login?uid={u.id}&ts={ts}&token={token}')
            session.clear(); session['uid'] = u.id; session['cart'] = cart
            return redirect(url_for('index'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html', mode='login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        f = request.form; email = f.get('email', '').lower().strip()
        if not f.get('name', '').strip() or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email) or len(f.get('password', '')) < 8:
            flash('Enter name, valid email and a password of 8+ characters.', 'danger')
        elif User.query.filter_by(email=email).first(): flash('Email already registered.', 'danger')
        else:
            u = User(name=f['name'][:100], email=email, password_hash=generate_password_hash(f['password']))
            db.session.add(u); db.session.commit(); session['uid'] = u.id
            return redirect(url_for('index'))
    return render_template('login.html', mode='register')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('index'))

@app.route('/robots.txt')
def robots(): return Response(f"User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: {url_for('sitemap', _external=True)}\n", mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap():
    urls = [url_for(e, _external=True) for e in ('index', 'shop', 'about', 'contact')]
    urls += [url_for('product', slug=p.slug, _external=True) for p in Product.query.all()]
    x = ''.join(f'<url><loc>{u}</loc></url>' for u in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{x}</urlset>', mimetype='application/xml')

@app.errorhandler(404)
def nf(e): return render_template('404.html'), 404

@app.errorhandler(500)
def ise(e): return render_template('404.html', server=True), 500

# ---------- Seed ----------
def seed():
    """Create tables, categories, and a starter catalogue of public model references.

    Catalogue stock is intentionally zero until the shop owner confirms real inventory.
    Prices are reference prices observed on public manufacturer listings and can change.
    """
    db.create_all()
    if not User.query.filter_by(is_admin=True).first():
        admin_email = os.getenv('ADMIN_EMAIL', '').strip().lower()
        admin_password = os.getenv('ADMIN_PASSWORD', '')
        if not admin_email or len(admin_password) < 12:
            raise RuntimeError('Set ADMIN_EMAIL and an ADMIN_PASSWORD of at least 12 characters in customer/.env.')
        db.session.add(User(name=os.getenv('ADMIN_NAME', 'Navnidh Admin'), email=admin_email, is_admin=True,
            password_hash=generate_password_hash(admin_password)))

    category_rows = [
        ('Office Chairs', '#6b4a33', 'Ergonomic comfort for workdays'),
        ('Executive Chairs', '#2f2a26', 'Premium seating for offices and meeting rooms'),
        ('Gaming Chairs', '#b23a30', 'Supportive seating for gaming setups'),
        ('Study Chairs', '#4f7a8a', 'Practical seating for study desks'),
        ('Dining Chairs', '#a67c52', 'Comfortable seating for dining spaces'),
        ('Visitor Chairs', '#5c6b5a', 'Guest seating for offices and waiting rooms'),
        ('Plastic Chairs', '#7d8a99', 'Lightweight everyday seating'),
        ('Reception Chairs', '#8a5a6b', 'Welcoming seating for lobbies'),
    ]
    existing_categories = {c.name: c for c in Category.query.all()}
    for name, color, description in category_rows:
        if name not in existing_categories:
            cat = Category(name=name, slug=slugify(name), color=color, description=description)
            db.session.add(cat)
            existing_categories[name] = cat
    db.session.flush()

    # Product model names and reference prices are from publicly listed Nilkamal models.
    # Do not imply that Navnidh Traders has these items in stock until the owner verifies them.
    photo = {
        'Giza Mid Back Office Chair': 'https://www.nilkamalhomes.com/cdn/shop/files/Giza_black_LS_1_800x_73d6a47e-3879-4e3c-972a-6e1fead13ef9.jpg?v=1728385490',
        'Contract Soft PVC Visitor Chair with Arm - Black': 'https://www.nilkamalhomes.com/cdn/shop/products/Contract_Chair_02_CONTRACT02PVCABLK_LF_With_Arm.jpg?v=1595670423',
        'Contract Soft PVC Visitor Chair without Arm - Black': 'https://www.nilkamalhomes.com/cdn/shop/products/CONTRACT_02_SOFT_PVC_WITHOUT_ARM_BLACK_CONTRACT02PVCBLK_LS.jpg?v=1595670422',
        'Zing Medium Back Office Chair - Brown': 'https://www.nilkamalhomes.com/cdn/shop/products/Zinglifestyle.jpg?v=1635502859',
        'Glory Mid Back Office Chair - Black': 'https://www.nilkamalhomes.com/cdn/shop/products/GLORYMIDBACKOFFICECHAIRBLACK_FLOCGLORYMBBLACK_00.jpg?v=1635101966',
        'Alba High Back Mesh Chair - Black': 'https://www.nilkamalhomes.com/cdn/shop/files/Alba_HB_LS.jpg?v=1691735760',
        'Kyoto High Back Office Chair - Brown': 'https://www.nilkamalhomes.com/cdn/shop/files/KyotobrownLS_800x_d6afc567-7229-439d-ae80-0679cadea744.jpg?v=1729509182',
        'Amaze Chair with Tablet - Black': 'https://www.nilkamalhomes.com/cdn/shop/products/AMAZECHAIRWITHTABLETBLACK_LS.jpg?v=1637752554',
        'Libra High Back Soft Leatherette Office Chair': 'https://www.nilkamalhomes.com/cdn/shop/files/MLIBRAHBSLBLK_800x_16f7d557-de1c-4ebb-86e8-97119c44ec73.jpg?v=1728535937',
        'Astor Mid Back Mesh Office Chair - Black': 'https://www.nilkamalhomes.com/cdn/shop/products/ASTOR.jpg?v=1682337131',
    }
    # (name, category, mrp, public_reference_sale_price, description, specs, official image if available)
    products = [
        ('Giza Mid Back Office Chair','Office Chairs',9000,6100,'Mid-back office chair model listed by Nilkamal. Confirm dimensions, finish and availability before sale.','Brand: Nilkamal\nType: Mid-back office chair\nColour: Black',None),
        ('Contract Soft PVC Visitor Chair with Arm - Black','Visitor Chairs',6000,4800,'PVC visitor chair with armrests, listed in the manufacturer catalogue.','Brand: Nilkamal\nMaterial: PVC and metal frame\nColour: Black',None),
        ('Contract Soft PVC Visitor Chair without Arm - Black','Visitor Chairs',5500,4200,'Compact visitor chair without armrests. Confirm current model details before sale.','Brand: Nilkamal\nMaterial: PVC and metal frame\nColour: Black',None),
        ('Zing Medium Back Office Chair - Brown','Office Chairs',10000,6500,'Medium-back office chair in brown, listed in the manufacturer catalogue.','Brand: Nilkamal\nBack: Medium\nColour: Brown',None),
        ('Glory Mid Back Office Chair - Black','Office Chairs',15900,12700,'Mid-back office chair model listed by Nilkamal. Verify exact upholstery and features.','Brand: Nilkamal\nBack: Medium\nColour: Black',None),
        ('Alba High Back Mesh Chair - Black','Office Chairs',16500,11400,'High-back mesh chair model listed by Nilkamal. Verify the exact variant and accessories.','Brand: Nilkamal\nBack: High\nMaterial: Mesh\nColour: Black',None),
        ('Kyoto High Back Office Chair - Brown','Executive Chairs',15000,11500,'High-back office chair in brown, listed in the manufacturer catalogue.','Brand: Nilkamal\nBack: High\nColour: Brown',None),
        ('Amaze Chair with Tablet - Black','Study Chairs',6800,6300,'Chair with attached writing tablet, suitable for training or study environments.','Brand: Nilkamal\nFeature: Writing tablet\nColour: Black',None),
        ('Libra High Back Soft Leatherette Office Chair','Executive Chairs',19900,14800,'High-back soft leatherette office chair model listed by Nilkamal.','Brand: Nilkamal\nBack: High\nUpholstery: Soft leatherette',None),
        ('Astor Mid Back Mesh Office Chair - Black','Office Chairs',9200,6900,'Mid-back mesh office chair model listed by Nilkamal.','Brand: Nilkamal\nBack: Medium\nMaterial: Mesh\nColour: Black',None),
        ('Mega High Back Office Chair','Executive Chairs',14500,7490,'High-back office chair listed on the Nilkamal Furniture website. Confirm the current variant and price.','Brand: Nilkamal\nBack: High',None),
        ('Poise High Back Office Chair','Executive Chairs',14800,12100,'High-back office chair model from the public Nilkamal catalogue.','Brand: Nilkamal\nBack: High',None),
        ('Victory Mid Back Office Chair','Office Chairs',10700,8900,'Mid-back office chair model from the public Nilkamal catalogue.','Brand: Nilkamal\nBack: Medium',None),
        ('Poise Mid Back Office Chair','Office Chairs',14100,11400,'Mid-back office chair model from the public Nilkamal catalogue.','Brand: Nilkamal\nBack: Medium',None),
        ('Giza Plus Mid Back Office Chair','Office Chairs',8000,4670,'Mid-back office chair model from the public Nilkamal catalogue.','Brand: Nilkamal\nBack: Medium',None),
        ('Verona High Back Office Chair - Black','Office Chairs',10000,6130,'High-back office chair model from the public Nilkamal catalogue.','Brand: Nilkamal\nBack: High\nColour: Black',None),
        ('Soren Mid Back Cushion Office Chair','Office Chairs',5900,5500,'Cushioned mid-back office chair model from the public Nilkamal catalogue.','Brand: Nilkamal\nBack: Medium',None),
        ('Calida Mesh Back Office Chair','Office Chairs',6500,5950,'Mesh-back office chair model from the public Nilkamal catalogue.','Brand: Nilkamal\nBack: Medium\nMaterial: Mesh',None),
        ('Otis Mid Back Mesh Office Chair','Office Chairs',7900,6800,'Mid-back mesh office chair model from the public Nilkamal catalogue.','Brand: Nilkamal\nBack: Medium\nMaterial: Mesh',None),
        ('Solitaire Mid Back Chair','Office Chairs',7500,6600,'Mid-back chair model from the public Nilkamal catalogue.','Brand: Nilkamal\nBack: Medium',None),
        ('Thames Neo Mid Back Fabric Chair','Office Chairs',10900,7900,'Fabric mid-back office chair model from the public Nilkamal catalogue.','Brand: Nilkamal\nBack: Medium\nMaterial: Fabric',None),
        ('Belgrade High Back Office Chair','Executive Chairs',22700,16500,'High-back office chair model from the public Nilkamal catalogue.','Brand: Nilkamal\nBack: High',None),
        ('Hanoi Mid Back Office Chair','Office Chairs',8500,4590,'Mid-back office chair model from the public Nilkamal catalogue.','Brand: Nilkamal\nBack: Medium',None),
        ('Lusaka Mid Back Office Chair','Office Chairs',9000,5800,'Mid-back office chair model from the public Nilkamal catalogue.','Brand: Nilkamal\nBack: Medium',None),
    ]
    existing_slugs = {p.slug for p in Product.query.all()}
    for index, (name, category, mrp, sale, description, specs, _unused) in enumerate(products):
        slug = slugify(name)
        if slug in existing_slugs:
            continue
        db.session.add(Product(
            name=name, slug=slug, category_id=existing_categories[category].id,
            brand='Nilkamal (reference listing)', description=description + '\n\nCatalogue note: model and public reference price only. Navnidh Traders must confirm actual stock, final selling price, delivery and image-use permission before accepting orders.',
            specs=specs, price=mrp, discount_price=sale, stock=0, rating=0,
            image=photo.get(name) or (slugify(name) + ".svg"), featured=index < 6, bestseller=False, is_new=False))
    db.session.commit()

@app.cli.command('seed')
def seed_cmd(): seed(); print('Database ready.')

def ensure_order_payment_columns():
    """Add payment columns to an older SQLite/MySQL database without breaking existing orders."""
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    if 'orders' not in inspector.get_table_names():
        return
    existing = {c['name'] for c in inspector.get_columns('orders')}
    additions = {
        'gateway_order_id': 'VARCHAR(100)',
        'gateway_payment_id': 'VARCHAR(100)',
        'payment_status': "VARCHAR(30) DEFAULT 'unpaid'",
        'invoice_token': 'VARCHAR(64)',
        'stock_deducted': "BOOLEAN DEFAULT FALSE"
    }
    for name, definition in additions.items():
        if name not in existing:
            db.session.execute(text(f'ALTER TABLE orders ADD COLUMN {name} {definition}'))
    db.session.commit()

def ensure_contact_columns():
    """Additive: add Admin 'Customer Help' columns to an older contacts table."""
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    if 'contacts' not in inspector.get_table_names():
        return
    existing = {c['name'] for c in inspector.get_columns('contacts')}
    for name, definition in {'status': "VARCHAR(20) DEFAULT 'Open'", 'admin_note': 'TEXT'}.items():
        if name not in existing:
            db.session.execute(text(f'ALTER TABLE contacts ADD COLUMN {name} {definition}'))
    db.session.commit()

# Initialize the database for both local Flask and production WSGI servers (e.g. Render/Gunicorn).
# This keeps a fresh deployment from failing with missing tables such as 'categories'.
with app.app_context():
    ensure_order_payment_columns()
    ensure_contact_columns()
    seed()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('CUSTOMER_PORT', '5000')), debug=os.getenv('FLASK_DEBUG', '0') == '1')
