"""Safely configure real stock and selling prices for Navnidh Traders products.
Run from the project root after setup.bat has completed.
Blank input keeps existing values; stock must reflect physically verified inventory.
"""
from pathlib import Path
import os, shutil, sys
ROOT = Path(__file__).resolve().parent
CUSTOMER = ROOT / 'customer'
if not (CUSTOMER / '.env').exists():
    print('ERROR: customer/.env is missing. Run setup.bat first.')
    raise SystemExit(1)
# Flask app loads .env from the current working directory.
os.chdir(CUSTOMER)
sys.path.insert(0, str(CUSTOMER))
try:
    import app as store
except Exception as exc:
    print('Could not load store app:', exc)
    print('Run setup.bat and check the error above.')
    raise SystemExit(1)

def ask_int(label, current, minimum=0):
    while True:
        raw = input(f'  {label} [{current}] (Enter = keep): ').strip()
        if not raw:
            return current
        try:
            value = int(raw)
            if value < minimum:
                raise ValueError
            return value
        except ValueError:
            print(f'  Enter a whole number >= {minimum}.')

with store.app.app_context():
    products = store.Product.query.order_by(store.Product.id).all()
    if not products:
        print('No products found. Check database setup and run run_both.bat once.')
        raise SystemExit(1)
    print('\nNAVNIDH TRADERS — INVENTORY SETUP')
    print('Enter only stock physically verified in your shop/warehouse.')
    print('Blank keeps a value unchanged. Selling price must be greater than zero.')
    print(f'Products found: {len(products)}\n')
    for p in products:
        print(f'#{p.id} {p.name} | Current price ₹{p.now_price:,} | Stock {p.stock}')
        stock = ask_int('Actual stock units', p.stock, 0)
        price = ask_int('Final selling price in rupees', p.now_price, 1)
        p.stock = stock
        # Keep regular price and discount semantics consistent with the selected final price.
        p.price = price
        p.discount_price = None
        print()
    store.db.session.commit()
    print('Inventory and selling prices saved successfully.')
    print('IMPORTANT: Verify all values in Admin > Products before accepting real orders.')
