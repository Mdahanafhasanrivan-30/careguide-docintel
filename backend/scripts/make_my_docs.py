"""Make 3 made-up test invoices for Build 13, each with a layout the Phase 2 dummy set does not have.

Run inside Docker:  dcrun python -m scripts.make_my_docs
Output: my_docs/  (git-ignored)
    my1_bdt_left_totals.pdf   currency after the number, columns Rate before Qty, totals box on the LEFT
    my2_discount_shipping.pdf discount row + shipping row + sales tax, date written as 'March 4, 2026'
    my3_eur_scan.jpg          European number format (1.234,56), a scanned photo of a PDF (OCR test)
Every file gets a label  <name>.json  with the issue codes you expect ([] = clean invoice).
All companies and numbers are made up.
"""
import json
import random
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[1] / 'my_docs'
W, H = A4
CENT = Decimal('0.01')


def d(text: str) -> Decimal:
    return Decimal(text)


def money(x: Decimal) -> str:
    """12345.6 -> '12,345.60' (English format)."""
    return f'{x:,.2f}'


def euro(x: Decimal) -> str:
    """12345.6 -> '12.345,60' (European format)."""
    return f'{x:,.2f}'.replace(',', '#').replace('.', ',').replace('#', '.')


def pct(x: Decimal, rate: str) -> Decimal:
    return (x * d(rate) / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def text(c, x, y, s, size=10, bold=False, right=False):
    c.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
    (c.drawRightString if right else c.drawString)(x, y, s)


def write_label(name: str, expected_issues: list[str], note: str):
    (OUT / f'{name}.json').write_text(
        json.dumps({'expected_issues': expected_issues, 'note': note}, indent=2), encoding='utf-8')


# ---------------------------------------------------------------- document 1
def doc1(path: Path):
    items = [('Surgical gloves (box)', d('250.00'), 5), ('Hand sanitizer 500 ml', d('180.00'), 4),
             ('Digital thermometer', d('650.00'), 2)]
    rows = [(n, rate, qty, rate * qty) for n, rate, qty in items]
    subtotal = sum(r[3] for r in rows)
    vat = pct(subtotal, '15')
    total = subtotal + vat
    c = canvas.Canvas(str(path), pagesize=A4)
    text(c, W - 50, H - 60, 'TAX INVOICE', 20, True, right=True)
    text(c, W - 50, H - 80, 'Invoice No: SPT/26/0418', 10, right=True)
    text(c, W - 50, H - 94, 'Date: 14/10/2026', 10, right=True)
    text(c, 50, H - 60, 'Sundarban Pharma Traders', 14, True)
    text(c, 50, H - 76, 'House 12, Road 4, Dhanmondi, Dhaka', 9)
    text(c, 50, H - 140, 'Billed to:', 10, True)
    text(c, 50, H - 154, 'Rivan Demo Clinic', 10)
    y = H - 200
    text(c, 50, y, 'ITEM', 9, True); text(c, 300, y, 'RATE', 9, True, True)
    text(c, 370, y, 'QTY', 9, True, True); text(c, W - 50, y, 'AMOUNT', 9, True, True)
    y -= 18
    for name, rate, qty, amount in rows:
        text(c, 50, y, name); text(c, 300, y, f'{money(rate)} BDT', right=True)
        text(c, 370, y, str(qty), right=True); text(c, W - 50, y, f'{money(amount)} BDT', right=True)
        y -= 16
    c.line(50, y + 8, W - 50, y + 8)
    y -= 30                                    # totals box on the LEFT side
    c.rect(50, y - 62, 230, 80)
    text(c, 58, y, 'Subtotal'); text(c, 272, y, f'{money(subtotal)} BDT', right=True)
    text(c, 58, y - 18, 'VAT (15%)'); text(c, 272, y - 18, f'{money(vat)} BDT', right=True)
    text(c, 58, y - 42, 'TOTAL', 11, True); text(c, 272, y - 42, f'{money(total)} BDT', 11, True, True)
    text(c, 50, 60, 'Payment within 15 days. All amounts in Bangladeshi Taka.', 8)
    c.save()
    return total


# ---------------------------------------------------------------- document 2
def doc2(path: Path):
    items = [('Desk lamp', d('49.50'), 4), ('Ergonomic chair', d('389.00'), 1), ('Paper ream A4', d('7.00'), 5)]
    rows = [(i + 1, n, f'{q} x {money(r)}', r * q) for i, (n, r, q) in enumerate(items)]
    subtotal = sum(r[3] for r in rows)
    discount = pct(subtotal, '10')
    shipping = d('18.00')
    tax = pct(subtotal - discount + shipping, '8')
    total = subtotal - discount + shipping + tax
    c = canvas.Canvas(str(path), pagesize=A4)
    text(c, 50, H - 60, 'Lakeview Office Supply LLC', 16, True)
    text(c, 50, H - 76, '2210 Harbor Blvd, Portland, OR 97201', 9)
    text(c, 50, H - 120, 'INVOICE #LV-5530', 12, True)
    text(c, 50, H - 136, 'Issued: March 4, 2026', 10)
    text(c, 50, H - 150, 'Currency: USD', 10)
    text(c, 330, H - 120, 'Customer', 10, True)
    text(c, 330, H - 134, 'Harbor Dental Group', 10)
    y = H - 200
    c.setFillGray(0.9); c.rect(45, y - 4, W - 90, 16, fill=1, stroke=0); c.setFillGray(0)
    text(c, 50, y, '#', 9, True); text(c, 75, y, 'Description', 9, True)
    text(c, 380, y, 'Qty x Rate', 9, True, True); text(c, W - 50, y, 'Amount', 9, True, True)
    y -= 20
    for no, name, qr, amount in rows:
        text(c, 50, y, str(no)); text(c, 75, y, name); text(c, 380, y, qr, right=True)
        text(c, W - 50, y, money(amount), right=True)
        y -= 16
    y -= 14
    for label, value, bold in [('Subtotal', money(subtotal), False),
                               ('Discount (10%)', f'-{money(discount)}', False),
                               ('Shipping', money(shipping), False),
                               ('Sales tax (8%)', money(tax), False),
                               ('TOTAL DUE', money(total), True)]:
        text(c, 380, y, label, 10, bold, True); text(c, W - 50, y, value, 10, bold, True)
        y -= 16
    text(c, 50, 60, 'Thank you for your business.', 8)
    c.save()
    return total


# ---------------------------------------------------------------- document 3 (becomes a scan)
def doc3(path: Path):
    items = [('Ultraschall-Gel (Karton)', d('42.50'), 8), ('Untersuchungshandschuhe', d('31.00'), 12),
             ('Wanduhr', d('19.90'), 3)]
    rows = [(n, q, r, r * q) for n, r, q in items]
    subtotal = sum(r[3] for r in rows)
    vat = pct(subtotal, '19')
    total = subtotal + vat
    c = canvas.Canvas(str(path), pagesize=A4)
    text(c, 50, H - 60, 'Alpenblick Trading GmbH', 16, True)
    text(c, 50, H - 76, 'Hauptstrasse 15, 80331 Muenchen', 9)
    text(c, 50, H - 120, 'Rechnung', 14, True)
    text(c, 50, H - 138, 'Rechnungsnummer: AB-2026-0933', 10)
    text(c, 50, H - 152, 'Datum: 30.09.2026', 10)
    text(c, 50, H - 166, 'Currency: EUR', 10)
    text(c, 50, H - 190, 'Kunde: Riverside Medical Centre', 10)
    y = H - 235
    text(c, 50, y, 'Position', 9, True); text(c, 300, y, 'Menge', 9, True, True)
    text(c, 400, y, 'Einzelpreis', 9, True, True); text(c, W - 50, y, 'Betrag', 9, True, True)
    y -= 18
    for name, qty, price, amount in rows:
        text(c, 50, y, name); text(c, 300, y, str(qty), right=True)
        text(c, 400, y, f'{euro(price)} \u20ac', right=True); text(c, W - 50, y, f'{euro(amount)} \u20ac', right=True)
        y -= 16
    y -= 14
    for label, value, bold in [('Zwischensumme', euro(subtotal), False), ('MwSt 19%', euro(vat), False),
                               ('Gesamtbetrag', euro(total), True)]:
        text(c, 400, y, label, 10, bold, True); text(c, W - 50, y, f'{value} \u20ac', 10, bold, True)
        y -= 16
    c.save()
    return total


def main(hard: bool) -> None:
    OUT.mkdir(exist_ok=True)
    t1 = doc1(OUT / 'my1_bdt_left_totals.pdf')
    write_label('my1_bdt_left_totals', [], f'clean; total {money(t1)} BDT, rate before qty, totals box left')
    t2 = doc2(OUT / 'my2_discount_shipping.pdf')
    write_label('my2_discount_shipping', [], f'clean; total {money(t2)} USD; discount + shipping rows; date in words')
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / 'my3.pdf'
        t3 = doc3(src)
        try:
            from scripts.make_dataset import scan_copy      # the Phase 2 scanner effect (needs PyMuPDF)
        except ImportError:
            print('scripts.make_dataset not found: my3 was not created')
        else:
            scan_copy(src, OUT / 'my3_eur_scan.jpg', random.Random(7), hard=hard)
            write_label('my3_eur', [], f'clean; total {euro(t3)} EUR; European numbers; scanned photo')
    print(f'Made files in {OUT}')
    for p in sorted(OUT.iterdir()):
        print(' ', p.name)
    print(f'Totals: my1 {money(t1)} BDT | my2 {money(t2)} USD | my3 {euro(t3)} EUR')


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--hard', action='store_true', help='stronger scan damage for my3 (tilt, noise)')
    main(ap.parse_args().hard)