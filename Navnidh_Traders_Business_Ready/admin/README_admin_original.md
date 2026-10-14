# Navnidh Traders — Connected Admin Panel

Standalone admin panel connected to the **same database and product-image folder** used by the customer website. No customer records are copied into a second database.

## What appears in Admin
- Products already present on the customer site
- Categories
- Customer orders, order items, delivery address, payment and status
- Registered customers with order count, total spent and last order
- Customer contact submissions under **Customer Help** (Messages menu removed)
- Dashboard counts, revenue and low-stock products

## Product management
Add/edit a product with:
- Product name and category
- Brand
- MRP/price and discount/selling price
- Stock
- Rating
- JPG/PNG/WEBP image upload
- Image URL option
- Description
- Specifications (one `Label: Value` per line)
- Featured / Bestseller / New flags

Uploaded images are stored in the same `static/uploads` folder as the customer app when both run locally, so the customer website can display the new image immediately.

## Local Windows setup
Recommended:
```text
D:\navnidh_traders                         # customer project
D:\k\Navnidh_Traders_ADMIN_CONNECTED_FIXED # admin project
```

The admin auto-detects `D:\navnidh_traders` when no database environment variable is supplied. If your customer project is elsewhere, create `.env` from `.env.example` and set `CUSTOMER_APP_DIR`.

Run:
```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open the port printed by Flask (normally `http://127.0.0.1:5000`). If the customer app is already using port 5000, set `ADMIN_PORT=5001` in `.env` and run with `flask --app app run --port 5001`.

Default admin credentials for a database without an admin account:
- Email: `admin@example.com`
- Password: `ChangeMe@123`

Change the password from the Admin Profile before production use.

## Online deployment
Two separate online services must use the **same hosted MySQL/PostgreSQL `DATABASE_URL`**. Do not use two separate SQLite databases on Render. For images, use a shared object-storage/image URL when services are separate.

## Safety
Do not delete or replace the customer database just to fix the admin login. The admin is designed to connect to the existing customer database and add only missing schema columns/tables. Never commit `.env` or secret keys to GitHub.
