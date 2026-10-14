# Production deployment checklist

## Required before launch
- [ ] Real business products, photos, prices, inventory, delivery areas and policies entered; no demo catalogue is being shown.
- [ ] Admin password changed to a strong unique password; private `.env` files excluded from Git.
- [ ] Public domain points to the production customer app and admin is protected appropriately; do not expose the admin app without HTTPS and strong access controls.
- [ ] HTTPS enabled; `COOKIE_SECURE=1`; Flask debug mode disabled.
- [ ] Persistent PostgreSQL/MySQL configured for production; same `DATABASE_URL` in both apps; migration and backup tested. Do not rely on an ephemeral filesystem for business records.
- [ ] Product uploads stored persistently and backed up.
- [ ] Razorpay test-mode success, failure, duplicate callback and webhook tests pass; webhook secret configured; refunds reconciled.
- [ ] COD order, cancellation, return, invoice, WhatsApp link and stock adjustment tested.
- [ ] Public invoice token links work; guessing order IDs alone does not reveal customer address/contact data.
- [ ] Logs, uptime checks, backups and a tested restore procedure exist.
- [ ] Privacy policy, terms, shipping/returns/refunds, warranty and correct business/tax details published.

## Current limitations to resolve for a true production launch
- Email delivery/password-reset email service is not configured.
- Shipping provider API and automated tracking are not integrated; delivery statuses are managed by admin.
- Product reviews are not a verified customer-review system.
- A payment captured after inventory is exhausted needs manual review/refund; stock reservation/expiry workflow should be added before high-volume use.
- No software package can be declared production-perfect without testing against the actual merchant account, production database, domain, delivery workflow and real inventory.
