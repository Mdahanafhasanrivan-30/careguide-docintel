"""Generate a labeled invoice dataset: digital PDFs, 'scanned' JPEGs and one JSON label each.

Run inside Docker:  dcrun python -m scripts.make_dataset
Output: eval_data/  (inv_001.pdf, inv_001_scan.jpg, inv_001.json, ...)
"""
import json
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[1] / 'eval_data'
N_INVOICES = 30
SEED = 42

SUPPLIERS = ['ACME Supplies Ltd', 'Bengal Office Mart', 'Café Müller GmbH', 'Northwind Traders',
             'Delta Tech Solutions', 'Green Leaf Stationers', 'Orbit Electronics Ltd', 'Riverside Printing Co']
CUSTOMERS = ['Contoso Health Ltd', 'Dhaka Care Clinic', 'Fabrikam Inc', 'Sunrise Pharmacy',
             'Lakeside Diagnostics', 'Blue Sky Logistics', 'Medina Hospital', 'Tailspin Toys']
PRODUCTS = [('Printer paper A4 (box)', '12.50'), ('Toner cartridge', '45.00'), ('USB keyboard', '18.90'),
            ('Office chair', '129.00'), ('Hand sanitizer 500 ml', '3.75'), ('Laptop stand', '27.40'),
            ('Network cable 5 m', '6.20'), ('Consulting hour', '80.00'), ('Delivery fee', '15.00')]
CURRENCIES = [('USD', '$'), ('EUR', '€'), ('GBP', '£'), ('BDT', 'Tk')]
NUMBER_LABELS = ['Invoice Number:', 'Invoice No:', 'Invoice #']
DATE_LABELS = ['Invoice Date:', 'Date:', 'Issued:']
CUSTOMER_LABELS = ['Bill To:', 'Customer:']

# Edge cases planted on purpose (index -> name). They also feed Phase 3 validation.
EDGE_CASES = {5: 'missing_tax', 9: 'wrong_total', 13: 'no_currency', 17: 'no_customer',
              21: 'duplicate_number', 25: 'european_numbers'}
CENT = Decimal('0.01')


def money(value: Decimal, european: bool) -> str:
    text = f'{value:,.2f}'                                   # 1,234.56
    if european:
        text = text.replace(',', '_').replace('.', ',').replace('_', '.')   # 1.234,56
    return text


def make_invoice(i: int, rng: random.Random, numbers_used: list[str]) -> dict:
    edge = EDGE_CASES.get(i)
    code, symbol = rng.choice(CURRENCIES)
    european = edge == 'european_numbers' or (code == 'EUR' and rng.random() < 0.5)
    number = f'INV-{2025}-{rng.randint(1000, 9999)}'
    if edge == 'duplicate_number':
        number = numbers_used[2]                              # same number as invoice 3
    numbers_used.append(number)
    issued = date(2025, 1, 1) + timedelta(days=rng.randint(0, 300))
    date_style = rng.choice(['%Y-%m-%d', '%d/%m/%Y', '%d %b %Y', '%B %d, %Y'])

    items = []
    for description, price in rng.sample(PRODUCTS, rng.randint(1, 5)):
        qty = rng.randint(1, 20)
        unit = Decimal(price)
        items.append({'description': description, 'quantity': str(qty),
                      'unit_price': str(unit), 'amount': str((unit * qty).quantize(CENT))})
    subtotal = sum(Decimal(item['amount']) for item in items)
    rate = Decimal(rng.choice(['0.05', '0.10', '0.15']))
    tax = (subtotal * rate).quantize(CENT, ROUND_HALF_UP)
    if edge == 'missing_tax':
        tax = None
    total = subtotal + (tax or Decimal('0'))
    if edge == 'wrong_total':
        total += Decimal('10.00')                             # printed total is wrong on purpose

    show_currency = edge != 'no_currency'
    return {
        'edge_case': edge,
        'supplier': rng.choice(SUPPLIERS),
        'customer': None if edge == 'no_customer' else rng.choice(CUSTOMERS),
        'number': number, 'number_label': rng.choice(NUMBER_LABELS),
        'date': issued, 'date_text': issued.strftime(date_style), 'date_label': rng.choice(DATE_LABELS),
        'customer_label': rng.choice(CUSTOMER_LABELS),
        'currency': code if show_currency else None,
        'prefix': (rng.choice([symbol, code]) + ' ') if show_currency else '',
        'european': european, 'items': items,
        'subtotal': subtotal, 'tax': tax, 'rate': rate, 'total': total,
    }


def draw_pdf(inv: dict, path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont('Helvetica-Bold', 16)
    c.drawString(50, 800, inv['supplier'])
    c.setFont('Helvetica', 11)
    c.drawString(50, 780, 'INVOICE')
    c.drawString(50, 755, f"{inv['number_label']} {inv['number']}")
    c.drawString(50, 738, f"{inv['date_label']} {inv['date_text']}")
    if inv['customer']:
        c.drawString(50, 721, f"{inv['customer_label']} {inv['customer']}")
    y = 690
    for x, head in [(50, 'Description'), (300, 'Qty'), (370, 'Unit Price'), (470, 'Amount')]:
        c.drawString(x, y, head)
    eu = inv['european']
    for item in inv['items']:
        y -= 18
        c.drawString(50, y, item['description'])
        c.drawString(300, y, item['quantity'])
        c.drawString(370, y, money(Decimal(item['unit_price']), eu))
        c.drawString(470, y, money(Decimal(item['amount']), eu))
    y -= 36
    c.drawString(370, y, f"Subtotal: {inv['prefix']}{money(inv['subtotal'], eu)}")
    if inv['tax'] is not None:
        y -= 18
        c.drawString(370, y, f"Tax ({int(inv['rate'] * 100)}%): {inv['prefix']}{money(inv['tax'], eu)}")
    y -= 18
    c.setFont('Helvetica-Bold', 11)
    c.drawString(370, y, f"Total: {inv['prefix']}{money(inv['total'], eu)}")
    c.save()


def scan_copy(pdf_path: Path, out_path: Path, rng: random.Random, hard: bool) -> None:
    """Render the PDF to an image and damage it like a cheap office scanner."""
    with pymupdf.open(pdf_path) as doc:
        pix = doc[0].get_pixmap(dpi=150, colorspace=pymupdf.csRGB, alpha=False)
        img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    angle = rng.uniform(-4, 4) if hard else rng.uniform(-1.5, 1.5)
    img = img.convert('L').rotate(angle, expand=True, fillcolor=255)
    img = img.filter(ImageFilter.GaussianBlur(1.0 if hard else 0.5))
    arr = np.asarray(img, dtype=np.int16)
    noise = np.random.default_rng(rng.randint(0, 10**6)).normal(0, 18 if hard else 8, arr.shape)
    img = Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))
    img.save(out_path, 'JPEG', quality=45 if hard else 70)


def label(inv: dict) -> dict:
    def s(value):
        return None if value is None else str(value)
    return {
        'invoice_number': inv['number'],
        'invoice_date': inv['date'].isoformat(),
        'supplier_name': inv['supplier'],
        'customer_name': inv['customer'],
        'subtotal': s(inv['subtotal']),
        'tax': s(inv['tax']),
        'total': s(inv['total']),
        'currency': inv['currency'],
        'line_items': inv['items'],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    numbers_used: list[str] = []
    for i in range(1, N_INVOICES + 1):
        inv = make_invoice(i, rng, numbers_used)
        stem = f'inv_{i:03d}'
        draw_pdf(inv, OUT / f'{stem}.pdf')
        hard = i % 7 == 0
        scan_copy(OUT / f'{stem}.pdf', OUT / f'{stem}_scan.jpg', rng, hard)
        record = {'files': [f'{stem}.pdf', f'{stem}_scan.jpg'], 'edge_case': inv['edge_case'],
                  'hard_scan': hard, 'expected': label(inv)}
        (OUT / f'{stem}.json').write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n',
                                          encoding='utf-8')
    print(f'Wrote {N_INVOICES} invoices to {OUT}')


if __name__ == '__main__':
    main()