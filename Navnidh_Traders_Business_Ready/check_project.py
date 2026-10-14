"""Offline preflight checks; does not prove payment-provider or live-hosting behavior."""
from pathlib import Path
import ast, sys

root = Path(__file__).resolve().parent
failed = False

for rel in ('customer/app.py', 'admin/app.py', 'setup_config.py'):
    path = root / rel
    try:
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        print(f'PASS syntax: {rel}')
    except (SyntaxError, OSError) as exc:
        failed = True
        print(f'FAIL syntax: {rel}: {exc}')

required = (
    'requirements.txt', 'run_both.bat', 'setup.bat', 'customer/templates/thanks.html',
    'customer/templates/invoice.html', 'admin/templates/invoice.html', 'README.md',
    'DEPLOYMENT_CHECKLIST.md', 'customer/.env.example', 'admin/.env.example',
)
for rel in required:
    if (root / rel).is_file():
        print(f'PASS file: {rel}')
    else:
        failed = True
        print(f'FAIL missing: {rel}')

for rel in ('customer/.env', 'admin/.env'):
    if (root / rel).exists():
        failed = True
        print(f'FAIL private config must not be shipped: {rel}')
    else:
        print(f'PASS no bundled secrets: {rel}')

customer = (root / 'customer/app.py').read_text(encoding='utf-8')
admin = (root / 'admin/app.py').read_text(encoding='utf-8')
checks = {
    'starter catalogue seeding enabled': 'Catalogue note: model and public reference price only' in customer and 'stock=0' in customer,
    'customer database URL normalization': 'def normalize_database_url(value):' in customer and "value.startswith('postgres://')" in customer,
    'admin database URL normalization': "value.startswith('postgres://')" in admin,
    'payment webhook signature verification': 'hmac.compare_digest(signature, expected)' in customer,
    'CSRF protection enabled': 'csrf = CSRFProtect(app)' in customer and 'csrf = CSRFProtect(app)' in admin,
}
for label, ok in checks.items():
    print(f'{"PASS" if ok else "FAIL"} {label}')
    failed = failed or not ok

sys.exit(1 if failed else 0)

# Catalogue starter assets and review guide
if (root / 'CATALOG_STARTER.csv').is_file() and (root / 'CATALOG_IMPORT_GUIDE.md').is_file():
    print('PASS catalogue starter files')
else:
    print('FAIL catalogue starter files'); failed = True
