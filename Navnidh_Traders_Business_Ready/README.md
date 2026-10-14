# Navnidh Traders — Business Store Package

A Flask-based chair/furniture storefront and separate admin dashboard using one shared database.

## Run on Windows (local testing)

1. Extract this ZIP to a folder you can write to.
2. Double-click `setup.bat`. The first run creates a virtual environment, privately asks you to create the admin password, generates secret keys, and installs Python packages.
3. Double-click `run_both.bat`.
4. Customer site: http://127.0.0.1:5000
5. Admin dashboard: http://127.0.0.1:5001/login
6. Use the admin email/password you entered during setup. The password is not printed to the console.

If Windows says Python is not recognized, install Python 3.11+ and select **Add Python to PATH**, then rerun `setup.bat`.

## Important: this ZIP does not contain your private config or business data

- `.env` files are deliberately not shipped. `setup_config.py` generates them on first run.
- Your old ZIP did not contain the production database or uploaded product images. If you have existing data, back it up before migration. Copy the old database to `customer/instance/navnidh.db` and product images to `customer/static/uploads/` only after making a backup.
- The app now seeds 24 public Nilkamal model references as a starter catalogue. Every item starts with stock 0. These are not verified Navnidh Traders inventory; confirm actual stock, final selling price, exact model, delivery and warranty in the admin panel before accepting orders. Review `CATALOG_IMPORT_GUIDE.md` and `CATALOG_STARTER.csv`.
- `.env`, databases, uploads and the virtual environment are excluded from Git via `.gitignore`.

## Configure real business details

After first setup, stop both apps and edit `customer/.env` and `admin/.env`:

- `WHATSAPP_NUMBER`: real WhatsApp number in international format, digits only, e.g. `91` followed by the 10-digit Indian mobile number.
- `BUSINESS_NAME`, `BUSINESS_PHONE`, `BUSINESS_EMAIL`, `BUSINESS_ADDRESS`, `BUSINESS_HOURS`: actual shop details shown on the storefront and contact page. Fill these before launch.
- `SHIPPING_CHARGE` and `FREE_DELIVERY_THRESHOLD`: delivery charge and free-delivery threshold in INR. Defaults preserve the prior behavior (₹250 under ₹5,000); change them to match your real policy.
- `DELIVERY_POLICY` and `WARRANTY_POLICY`: plain-text policy summaries shown on product pages. Set only terms the business can actually honor.
- `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`: from your own Razorpay merchant account. Keep the secret private.
- `RAZORPAY_WEBHOOK_SECRET`: create a webhook secret in the Razorpay dashboard and configure the webhook URL `/payment/razorpay-webhook` on the **public HTTPS customer domain**. Subscribe to `payment.captured` and/or `order.paid`.
- Set `ADMIN_BASE_URL` and `CUSTOMER_BASE_URL` to your real HTTPS URLs when deployed.
- Set `COOKIE_SECURE=1` only after the site is served over HTTPS. Keep it `0` for localhost.
- If using PostgreSQL/MySQL, configure the exact same `DATABASE_URL` in both `.env` files and install the appropriate driver. Legacy Render `postgres://` URLs are normalized to `postgresql://`. Back up the existing SQLite DB first; changing the URL does not migrate data automatically. A database URL change is not a data migration.

Online payment will remain disabled until valid Razorpay credentials are configured. A payment gateway key is not supplied in this ZIP and cannot be fabricated; obtain credentials from your own verified merchant account. Do not test with real customer payments until test-mode payment success/failure, webhook signature verification, duplicate callbacks, refunds and order reconciliation have been checked.

## Core functionality

- Customer catalogue, categories, search, product detail, cart and checkout.
- Admin product/category management, orders, order status, payment status, customers, help requests, and printable invoices.
- COD checkout and optional Razorpay checkout with server-side signature verification.
- Razorpay webhook signature verification and idempotent stock deduction guard.
- Shared customer/admin database and shared product image directory.
- Token-protected public invoice links for WhatsApp sharing; customer order confirmation page is restricted to the session that placed the order (or the signed-in owner).
- CSRF protection for form routes, password hashing, separate admin/customer session cookies, and generated secret keys.

## Before accepting real orders

1. Replace all demo catalogue content and add accurate business address/contact information.
2. Set actual delivery areas, shipping charges, warranty, cancellation, return and refund policies.
3. Confirm applicable GST/invoice requirements with your accountant and configure business/tax details accurately. Do not treat the included basic invoice as automatically GST-compliant.
4. Use a production WSGI server (for example Gunicorn), HTTPS, persistent database/storage, automatic backups and error monitoring. Do not run Flask debug mode publicly.
5. Test admin access control, checkout, stock, COD, online payment success/failure, webhook events, invoice/WhatsApp links, cancellations, refunds and recovery from backup.
6. The webhook cannot guarantee stock availability after a payment has already been captured. If an item has been sold out concurrently, the app logs the case for manual order/refund review. Test inventory concurrency and define an operational refund process before launch.

## Changes in this revision

- Fresh installations no longer seed fictional chair products or fabricated star ratings by default; categories are created and the owner adds actual inventory through the admin panel. Set `DEMO_DATA=1` only for a demo environment.
- Normalized legacy `postgres://` database URLs for compatibility with SQLAlchemy 2.x / Render PostgreSQL configuration.

- Removed placeholder customer testimonials and unverified star-rating claims from customer-facing product cards.
- Replaced contact-page placeholders with configurable business settings and clear warnings when required shop details are missing.
- Made delivery policy text configurable and made delivery charge / free-delivery threshold environment-driven rather than hard-coded in checkout calculations.
- Corrected price filtering and price sorting to use the actual selling price when a discount price is set.
- Improved product, about and contact copy to ask customers to confirm availability, delivery and warranty rather than promising unverified service levels.
- Updated customer/admin order bills to show items subtotal and the remaining delivery/other charges included in the saved order total; renamed the generic bill so it is not falsely represented as a GST tax invoice.
- Added cancellation stock restoration and stock re-check when an admin reopens a cancelled order. Online refunds still need to be processed separately in the payment provider.

## Visual previews

Open `previews/storefront_preview.png` and `previews/admin_dashboard_preview.png` for visual direction. These are clearly labelled mockups using sample content, not screenshots of a running live site or real customer/order data. The working pages are rendered by the Flask apps and use your database/configuration.

## Offline project checks

Run:

```bash
python check_project.py
```

This checks Python syntax, key files and confirms that private `.env` files are not bundled. It is not a substitute for integration tests with your database, payment account, email provider, hosting and real business settings.


## Customer experience additions in this revision

- Added a browser-local wishlist on product cards and product detail pages. It is stored only in that browser using localStorage; it is not synced between devices or accounts.
- Added a recently viewed products row on the homepage, based on the same device/browser's local history.
- Improved small-screen product card spacing and wishlist controls.
- These features do not require customer accounts and do not send browsing history to the server. Customers can clear the site's browser data to remove these saved items.

These UI additions do not replace live checkout testing, verified business details, production hosting, or real Razorpay merchant configuration.


## Catalogue starter set (important)

This revision adds 24 public model references and product imagery. Some images are official external manufacturer CDN images; the rest are original illustrative SVGs clearly labelled as illustrations. Confirm image-use permission for manufacturer photos and replace illustration assets with your own/authorized photos before marketing the exact product. All newly seeded products have stock 0 to prevent accidental sales until you confirm actual inventory. Public reference prices can change; update prices and stock in Admin.

## Inventory and cart/checkout verification (v6.3)
- Run `setup_inventory.bat` from the project root to enter the shop's verified stock and final selling prices. Blank values keep current values.
- A product with stock `0` intentionally cannot be added to cart. Do not enter stock unless it is physically available.
- Follow `CART_CHECKOUT_TEST_GUIDE.md` to verify cart, COD order, admin order visibility, stock deduction/restoration, and over-stock rejection.
- Razorpay live payment must be tested separately using Razorpay test credentials before enabling live payments.
