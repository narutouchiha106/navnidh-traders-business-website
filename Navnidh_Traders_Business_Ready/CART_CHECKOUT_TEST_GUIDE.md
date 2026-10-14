# Cart and Checkout Verification

## Before testing
1. Run `setup.bat` once.
2. Run `setup_inventory.bat` and enter only physically verified stock and final selling prices.
3. Start the customer/admin apps with `run_both.bat`.
4. Open the customer site at `http://127.0.0.1:5000`.

## Manual smoke test
- Open a product with stock greater than zero; Add to cart should be enabled.
- Add quantity 1; the cart badge and `/cart` should show the item and correct subtotal.
- Change quantity and remove item; totals should recalculate.
- Checkout with valid Indian mobile number, email, address, city, state and 6-digit pincode.
- Place a COD test order. The confirmation page should open, cart should clear, and stock should decrease by the ordered quantity.
- Sign in to admin at `http://127.0.0.1:5001/login`; verify the order appears and stock/order status are correct.
- Cancel the test order from admin and confirm stock restoration.
- Try ordering more than available stock; checkout must refuse it.
- Online payment is not ready until real Razorpay test credentials are configured and a test payment is completed. Never use live credentials for initial tests.

## Troubleshooting
- If Add to cart is disabled, that product's stock is zero. Configure real inventory in Admin > Products or use `setup_inventory.bat`.
- If a database or import error appears, keep both CMD windows open and share the complete traceback.
- Do not set stock to a fake number just to make the button clickable.
- Product images use external manufacturer URLs in some cases; if they fail to load, confirm network access and URL availability. Commercial image rights must be confirmed by the business owner.
