from pathlib import Path
import secrets, getpass, re

ROOT = Path(__file__).resolve().parent
CUSTOMER = ROOT / 'customer' / '.env'
ADMIN = ROOT / 'admin' / '.env'

def read_env(path):
    data = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1); data[k.strip()] = v.strip()
    return data

def write_env(path, data, comments):
    lines = [comments, '']
    for k, v in data.items(): lines.append(f'{k}={v}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

c = read_env(CUSTOMER); a = read_env(ADMIN)
if CUSTOMER.exists() and ADMIN.exists():
    print('Configuration files already exist; preserving them.')
else:
    print('\nNavnidh Traders first-time setup')
    print('If importing an old database, enter the email of the existing admin account to rotate its password.')
    email = (c.get('ADMIN_EMAIL') or a.get('ADMIN_EMAIL') or input('Admin email [owner@example.com]: ').strip() or 'admin@example.com').lower()
    password = c.get('ADMIN_PASSWORD') or a.get('ADMIN_PASSWORD')
    if not password:
        while True:
            password = getpass.getpass('Create admin password (minimum 12 characters): ')
            if len(password) >= 12 and re.search(r'[A-Za-z]', password) and re.search(r'\d', password): break
            print('Use at least 12 characters with letters and numbers.')
        confirm = getpass.getpass('Confirm admin password: ')
        if password != confirm: raise SystemExit('Passwords did not match. Run setup.bat again.')
    bridge = c.get('ADMIN_BRIDGE_SECRET') or a.get('ADMIN_BRIDGE_SECRET') or secrets.token_hex(32)
    cdata = {
      'SECRET_KEY': c.get('SECRET_KEY') or secrets.token_hex(32),
      'ADMIN_EMAIL': email, 'ADMIN_PASSWORD': password, 'ADMIN_NAME': c.get('ADMIN_NAME') or 'Navnidh Admin',
      'ADMIN_BRIDGE_SECRET': bridge, 'ADMIN_BASE_URL': c.get('ADMIN_BASE_URL') or 'http://127.0.0.1:5001',
      'CUSTOMER_PORT': c.get('CUSTOMER_PORT') or '5000', 'WHATSAPP_NUMBER': c.get('WHATSAPP_NUMBER') or '91XXXXXXXXXX',
      'BUSINESS_NAME': c.get('BUSINESS_NAME') or 'Navnidh Traders',
      'BUSINESS_PHONE': c.get('BUSINESS_PHONE') or '', 'BUSINESS_EMAIL': c.get('BUSINESS_EMAIL') or '',
      'BUSINESS_ADDRESS': c.get('BUSINESS_ADDRESS') or '', 'BUSINESS_HOURS': c.get('BUSINESS_HOURS') or '',
      'SHIPPING_CHARGE': c.get('SHIPPING_CHARGE') or '250',
      'FREE_DELIVERY_THRESHOLD': c.get('FREE_DELIVERY_THRESHOLD') or '5000',
      'DELIVERY_POLICY': c.get('DELIVERY_POLICY') or 'Delivery availability and charges are confirmed before order dispatch.',
      'WARRANTY_POLICY': c.get('WARRANTY_POLICY') or 'Warranty depends on the product and supplier. Confirm the terms before purchase.',
      'RAZORPAY_KEY_ID': c.get('RAZORPAY_KEY_ID') or '', 'RAZORPAY_KEY_SECRET': c.get('RAZORPAY_KEY_SECRET') or '',
      'RAZORPAY_WEBHOOK_SECRET': c.get('RAZORPAY_WEBHOOK_SECRET') or '',
      'COOKIE_SECURE': c.get('COOKIE_SECURE') or '0',
      'DEMO_DATA': c.get('DEMO_DATA') or '0'
    }
    adata = {
      'ADMIN_SECRET_KEY': a.get('ADMIN_SECRET_KEY') or secrets.token_hex(32),
      'ADMIN_EMAIL': email, 'ADMIN_PASSWORD': password, 'ADMIN_NAME': cdata['ADMIN_NAME'],
      'ADMIN_BRIDGE_SECRET': bridge, 'ADMIN_BASE_URL': cdata['ADMIN_BASE_URL'],
      'ADMIN_PORT': a.get('ADMIN_PORT') or '5001', 'CUSTOMER_BASE_URL': a.get('CUSTOMER_BASE_URL') or 'http://127.0.0.1:5000',
      'COOKIE_SECURE': a.get('COOKIE_SECURE') or '0'
    }
    write_env(CUSTOMER, cdata, '# Private local configuration. Never upload this file to GitHub.')
    write_env(ADMIN, adata, '# Private local configuration. Never upload this file to GitHub.')
    print(f'Created configuration. Admin email: {email}')
    print('Admin password was set privately; it is not printed.')
print('\nNext: run run_both.bat. Customer site: http://127.0.0.1:5000 | Admin: http://127.0.0.1:5001/login')
