"""Generate 21 synthetic invoices that each test one validation corner case.

Run inside Docker:  dcrun python -m scripts.make_edge_cases          (PDFs + labels)
                    dcrun python -m scripts.make_edge_cases --scans  (also e01_discount_scan.jpg ...)
Output: eval_edge/  (e01_discount.pdf + e01_discount.json, ...)

Each JSON has 'expected' (true values, like eval_data), 'printed' (fields whose printed text
differs from the clean value) and 'expected_issues' (the issue codes validation must raise).
The order matters: duplicates (e14-e17) refer to invoices earlier in the list.
"""
import argparse
import json
import random
from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[1] / 'eval_edge'
CUSTOMER = 'Dhaka Care Clinic'
PADMA, KARNA = 'Padma Medical Supplies Ltd', 'Karnaphuli Traders'
MEGHNA, JAMUNA = 'Meghna Lab Equipment', 'Jamuna Office Solutions'


def case(name, supplier, number, date_iso, prefix, currency, items, summary, expect,
         date_printed=None, title='INVOICE'):
    """items: (description, qty, unit_price, amount) or (description, qty, unit_price, discount, amount)
    as printed; '' for an empty column.
    summary: (role, label, amount) rows under the table. role is subtotal, tax, adj, payment or total.
    The first 'tax' row is the tax field; later 'tax' rows become adjustments."""
    return dict(name=name, supplier=supplier, number=number, date_iso=date_iso,
                date_printed=date_printed or date_iso, prefix=prefix, currency=currency,
                items=items, summary=summary, expect=expect, title=title)


CASES = [
    # --- adjustments: these must NOT be flagged -------------------------------------
    case('e01_discount', PADMA, 'INV-7001', '2025-08-10', 'BDT ', 'BDT',
         [('Nitrile gloves (box)', '10', '450.00', '4,500.00'), ('Face masks (pack)', '20', '120.00', '2,400.00')],
         [('subtotal', 'Subtotal', '6,900.00'), ('adj', 'Discount (5%)', '-345.00'),
          ('tax', 'VAT 15%', '983.25'), ('total', 'Total', '7,538.25')], []),
    case('e02_shipping', KARNA, 'KT/2025/118', '2025-09-02', 'USD ', 'USD',
         [('Stethoscope', '3', '85.00', '255.00'), ('BP monitor', '2', '60.00', '120.00')],
         [('subtotal', 'Subtotal', '375.00'), ('adj', 'Shipping', '25.00'),
          ('tax', 'Sales tax 8%', '30.00'), ('total', 'Total', '430.00')], []),
    case('e03_rounding', MEGHNA, 'MLE-2025-0456', '2025-07-15', 'Tk ', 'BDT',
         [('Test tubes (100)', '7', '135.50', '948.50'), ('Pipettes', '3', '87.25', '261.75')],
         [('subtotal', 'Subtotal', '1,210.25'), ('tax', 'VAT 5%', '60.51'),
          ('adj', 'Rounding', '-0.76'), ('total', 'Total', '1,270.00')], []),
    case('e04_two_taxes', JAMUNA, 'JOS-0091', '2025-10-01', 'INR ', 'INR',
         [('Laser printer', '1', '18,000.00', '18,000.00'), ('Toner', '2', '2,500.00', '5,000.00')],
         [('subtotal', 'Subtotal', '23,000.00'), ('tax', 'CGST 9%', '2,070.00'),
          ('tax', 'SGST 9%', '2,070.00'), ('total', 'Total', '27,140.00')], []),
    case('e05_tax_included', PADMA, 'INV-7002', '2025-08-20', 'EUR ', 'EUR',
         [('Hand sanitiser 1 l', '10', '11.50', '115.00')],
         [('subtotal', 'Subtotal', '115.00'), ('tax', 'VAT 15% (included)', '15.00'),
          ('total', 'Total', '115.00')], ['tax_included']),
    case('e06_no_subtotal', KARNA, 'KT/2025/131', '2025-09-18', 'GBP ', 'GBP',
         [('Digital thermometer', '4', '12.50', '50.00'), ('AA batteries', '10', '1.20', '12.00')],
         [('tax', 'VAT 20%', '12.40'), ('total', 'Total', '74.40')], ['subtotal_missing']),
    case('e07_credit_note', MEGHNA, 'CN-2025-0012', '2025-10-05', 'BDT ', 'BDT',
         [('Returned pipettes', '-2', '87.25', '-174.50')],
         [('subtotal', 'Subtotal', '-174.50'), ('tax', 'VAT 5%', '-8.73'),
          ('total', 'Total', '-183.23')], ['negative_total'], title='CREDIT NOTE'),
    case('e08_zero_total', JAMUNA, 'JOS-0099', '2025-10-12', 'USD ', 'USD',
         [('Demo unit (free sample)', '1', '0.00', '0.00')],
         [('subtotal', 'Subtotal', '0.00'), ('tax', 'Tax', '0.00'), ('total', 'Total', '0.00')],
         ['zero_total']),
    # --- dates -----------------------------------------------------------------------
    case('e09_future_date', PADMA, 'INV-7010', '2030-01-15', 'BDT ', 'BDT',
         [('Surgical caps (box)', '5', '200.00', '1,000.00')],
         [('subtotal', 'Subtotal', '1,000.00'), ('tax', 'VAT 15%', '150.00'), ('total', 'Total', '1,150.00')],
         ['future_date']),
    case('e10_old_date', KARNA, 'KT/2015/007', '2015-06-30', 'USD ', 'USD',
         [('Wheelchair', '1', '320.00', '320.00')],
         [('subtotal', 'Subtotal', '320.00'), ('tax', 'Tax 5%', '16.00'), ('total', 'Total', '336.00')],
         ['old_date']),
    case('e11_ambiguous_date', MEGHNA, 'MLE-2025-0488', '2025-04-03', 'BDT ', 'BDT',
         [('Microscope slides', '12', '35.00', '420.00')],
         [('subtotal', 'Subtotal', '420.00'), ('tax', 'VAT 5%', '21.00'), ('total', 'Total', '441.00')],
         ['ambiguous_date'], date_printed='03/04/2025'),
    # --- currency --------------------------------------------------------------------
    case('e12_fake_currency', MEGHNA, 'MLE-2025-0470', '2025-08-01', 'XYZ ', 'XYZ',
         [('Centrifuge tubes', '50', '2.40', '120.00')],
         [('subtotal', 'Subtotal', '120.00'), ('tax', 'Tax 10%', '12.00'), ('total', 'Total', '132.00')],
         ['currency_unknown']),
    case('e13_dollar_only', JAMUNA, 'JOS-0105', '2025-10-20', '$ ', 'USD',
         [('Office chair', '2', '129.00', '258.00')],
         [('subtotal', 'Subtotal', '258.00'), ('tax', 'Tax 10%', '25.80'), ('total', 'Total', '283.80')],
         ['currency_assumed']),
    # --- duplicates (refer to earlier cases) -------------------------------------------
    case('e14_exact_duplicate', PADMA, 'INV-7001', '2025-08-10', 'BDT ', 'BDT',      # same as e01
         [('Nitrile gloves (box)', '10', '450.00', '4,500.00'), ('Face masks (pack)', '20', '120.00', '2,400.00')],
         [('subtotal', 'Subtotal', '6,900.00'), ('adj', 'Discount (5%)', '-345.00'),
          ('tax', 'VAT 15%', '983.25'), ('total', 'Total', '7,538.25')], ['duplicate_invoice']),
    case('e15_supplier_spelling', 'PADMA MEDICAL SUPPLIES LIMITED', 'inv 7002', '2025-08-20', 'EUR ', 'EUR',
         [('Hand sanitiser 1 l', '10', '11.50', '115.00')],                          # e05 retyped
         [('subtotal', 'Subtotal', '115.00'), ('tax', 'VAT 15% (included)', '15.00'),
          ('total', 'Total', '115.00')], ['tax_included', 'duplicate_invoice']),
    case('e16_same_date_and_total', KARNA, 'KT-2025-200', '2025-09-02', 'USD ', 'USD',   # e02 renumbered
         [('Stethoscope', '3', '85.00', '255.00'), ('BP monitor', '2', '60.00', '120.00')],
         [('subtotal', 'Subtotal', '375.00'), ('adj', 'Shipping', '25.00'),
          ('tax', 'Sales tax 8%', '30.00'), ('total', 'Total', '430.00')], ['possible_duplicate']),
    case('e17_number_drift', MEGHNA, '2025-0456', '2025-07-25', 'Tk ', 'BDT',          # e03 prefix dropped
         [('Pipettes', '4', '87.25', '349.00')],
         [('subtotal', 'Subtotal', '349.00'), ('tax', 'VAT 5%', '17.45'), ('total', 'Total', '366.45')],
         ['possible_duplicate']),
    # --- line items and payments -------------------------------------------------------
    case('e18_discount_row_in_table', JAMUNA, 'JOS-0112', '2025-11-02', 'USD ', 'USD',
         [('Wheelchair', '1', '950.00', '950.00'), ('Delivery fee', '', '', '15.00'),
          ('Loyalty discount', '', '', '-50.00')],
         [('subtotal', 'Subtotal', '915.00'), ('tax', 'Tax 5%', '45.75'), ('total', 'Total', '960.75')], []),
    case('e19_balance_due', JAMUNA, 'JOS-0110', '2025-11-05', 'USD ', 'USD',
         [('Filing cabinet', '2', '200.00', '400.00'), ('Desk lamp', '4', '25.00', '100.00')],
         [('subtotal', 'Subtotal', '500.00'), ('tax', 'Tax 0%', '0.00'), ('total', 'Total', '500.00'),
          ('payment', 'Advance paid', '-200.00'), ('payment', 'Balance due', '300.00')], []),
    case('e20_wrong_line_amount', KARNA, 'KT/2025/140', '2025-10-08', 'USD ', 'USD',
         [('Pulse oximeter', '3', '45.00', '145.00'), ('Gauze rolls', '10', '2.00', '20.00')],
         [('subtotal', 'Subtotal', '165.00'), ('tax', 'Tax 10%', '16.50'), ('total', 'Total', '181.50')],
         ['line_amount_mismatch']),
    case('e21_line_discount_column', MEGHNA, 'MLE-2025-0501', '2025-11-10', 'BDT ', 'BDT',
         [('Lab coat', '5', '800.00', '10%', '3,600.00'), ('Safety goggles', '10', '150.00', '50.00', '1,450.00'),
          ('Gloves (box)', '4', '450.00', '', '1,800.00')],
         [('subtotal', 'Subtotal', '6,850.00'), ('tax', 'VAT 5%', '342.50'), ('total', 'Total', '7,192.50')], []),
]


def columns(item: tuple) -> tuple:
    """Return (description, qty, unit_price, discount, amount) for 4- or 5-column rows."""
    return item if len(item) == 5 else (item[0], item[1], item[2], '', item[3])


def clean(amount: str) -> str:
    """'4,500.00' -> '4500.00' (these PDFs use English number format)."""
    return str(Decimal(amount.replace(',', '')))


def label(c: dict) -> dict:
    rows = c['summary']
    taxes = [r for r in rows if r[0] == 'tax']
    subtotal = next((clean(a) for role, _, a in rows if role == 'subtotal'), None)
    total = next(clean(a) for role, _, a in rows if role == 'total')
    adjustments = [{'label': lab, 'amount': clean(a)} for role, lab, a in rows if role == 'adj']
    adjustments += [{'label': lab, 'amount': clean(a)} for _, lab, a in taxes[1:]]
    printed = {'currency': c['prefix'].strip()}
    if c['date_printed'] != c['date_iso']:
        printed['invoice_date'] = c['date_printed']
    return {
        'expected': {
            'invoice_number': c['number'], 'invoice_date': c['date_iso'],
            'supplier_name': c['supplier'], 'customer_name': CUSTOMER,
            'subtotal': subtotal, 'tax': clean(taxes[0][2]) if taxes else None, 'total': total,
            'currency': c['currency'],
            'line_items': [{'description': d, 'quantity': q, 'unit_price': clean(u) if u else '',
                            'discount': disc, 'amount': clean(a)}
                           for d, q, u, disc, a in map(columns, c['items'])],
            'adjustments': adjustments,
        },
        'printed': printed,
        'expected_issues': c['expect'],
    }


def draw_pdf(c: dict, path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setFont('Helvetica-Bold', 16)
    pdf.drawString(50, 800, c['supplier'])
    pdf.setFont('Helvetica', 11)
    pdf.drawString(50, 780, c['title'])
    pdf.drawString(50, 755, f"Invoice No: {c['number']}")
    pdf.drawString(50, 738, f"Date: {c['date_printed']}")
    pdf.drawString(50, 721, f'Bill To: {CUSTOMER}')
    y = 690
    has_discount = any(len(item) == 5 for item in c['items'])
    heads = [(50, 'Description'), (260, 'Qty'), (310, 'Unit Price'), (400, 'Disc'), (470, 'Amount')]
    for x, head in heads if has_discount else [h for h in heads if h[1] != 'Disc']:
        pdf.drawString(x, y, head)
    for description, qty, unit, discount, amount in map(columns, c['items']):
        y -= 18
        for x, text in [(50, description), (260, qty), (310, unit), (400, discount), (470, amount)]:
            if text:
                pdf.drawString(x, y, text)
    y -= 18
    for role, row_label, amount in c['summary']:
        y -= 18
        pdf.setFont('Helvetica-Bold' if role == 'total' else 'Helvetica', 11)
        pdf.drawString(330, y, f"{row_label}: {c['prefix']}{amount}")
    pdf.save()


def main() -> None:
    ap = argparse.ArgumentParser(description='Generate corner-case invoices')
    ap.add_argument('--scans', action='store_true', help='also write a scanned-looking JPEG of each PDF')
    args = ap.parse_args()
    if args.scans:
        from scripts.make_dataset import scan_copy     # the Phase 2 scanner effect (needs PyMuPDF)
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    for c in CASES:
        pdf_path = OUT / f"{c['name']}.pdf"
        draw_pdf(c, pdf_path)
        files = [pdf_path.name]
        if args.scans:
            scan_copy(pdf_path, OUT / f"{c['name']}_scan.jpg", rng, hard=False)
            files.append(f"{c['name']}_scan.jpg")
        record = {'files': files, **label(c)}
        (OUT / f"{c['name']}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n',
                                              encoding='utf-8')
    print(f'Wrote {len(CASES)} edge-case invoices to {OUT}')


if __name__ == '__main__':
    main()