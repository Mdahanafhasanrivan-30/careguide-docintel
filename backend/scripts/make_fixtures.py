from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pymupdf
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path('tests/fixtures')

HEADER = [
    'ACME Supplies Ltd',
    '123 Market Street, Dhaka 1212',
    'INVOICE',
    'Invoice Number: INV-2025-0042',
    'Invoice Date: 2025-03-14',
    'Due Date: 2025-04-13',
    'Bill To: Northwind Traders',
]
TABLE = [
    ['Description', 'Qty', 'Unit Price', 'Total'],
    ['Widget A', '10', '12.50', '125.00'],
    ['Widget B', '4', '30.00', '120.00'],
]
FOOTER = ['Subtotal 245.00', 'Tax (10%) 24.50', 'Total Due 269.50']


def make_digital_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 780
    for i, line in enumerate(HEADER):
        c.setFont('Helvetica-Bold' if i in (0, 2) else 'Helvetica', 14)
        c.drawString(50, y, line)
        y -= 26
    y -= 20
    c.setFont('Helvetica', 14)
    for row in TABLE:
        for x, cell in zip((50, 280, 380, 480), row):
            c.drawString(x, y, cell)
        y -= 26
    y -= 20
    for line in FOOTER:
        c.drawString(380, y, line)
        y -= 26
    c.save()


def truth_text() -> str:
    lines = HEADER + [' '.join(row) for row in TABLE] + FOOTER
    return '\n'.join(lines)


def render_gray(pdf_path: Path, dpi: int) -> np.ndarray:
    with pymupdf.open(pdf_path) as doc:
        pix = doc[0].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
        return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()


def degrade(gray: np.ndarray, angle: float, sigma: float) -> np.ndarray:
    # Simulate a scanner: tilt the page, blur slightly, add noise.
    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    out = cv2.warpAffine(gray, matrix, (w, h), borderValue=255)
    out = cv2.GaussianBlur(out, (3, 3), 0)
    rng = np.random.default_rng(42)   # fixed seed = reproducible fixtures
    noisy = out.astype(np.float32) + rng.normal(0, sigma, out.shape)
    return np.clip(noisy, 0, 255).astype(np.uint8)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    digital = OUT / 'invoice_digital.pdf'
    make_digital_pdf(digital)
    (OUT / 'invoice_truth.txt').write_text(truth_text() + '\n', encoding='utf-8')

    clean = render_gray(digital, dpi=200)
    cv2.imwrite(str(OUT / 'invoice_clean.png'), clean)

    skewed = degrade(clean, angle=2.5, sigma=12)
    cv2.imwrite(str(OUT / 'invoice_skewed.jpg'), skewed, [cv2.IMWRITE_JPEG_QUALITY, 70])

    lowres = cv2.resize(clean, None, fx=0.75, fy=0.75, interpolation=cv2.INTER_AREA)   # ~150 dpi
    cv2.imwrite(str(OUT / 'invoice_lowres.png'), lowres)

    # Scanned PDF = a PDF whose page is only a picture (no text layer).
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, filename=str(OUT / 'invoice_skewed.jpg'))
        doc.save(OUT / 'invoice_scanned.pdf')

    # Two-page TIFF (clean page + skewed page).
    frames = [Image.fromarray(clean), Image.fromarray(skewed)]
    frames[0].save(OUT / 'invoice_multipage.tiff', save_all=True, append_images=frames[1:])

    # Spreadsheets
    invoices = pd.DataFrame({
        'invoice_number': [f'INV-2025-{n:04d}' for n in range(40, 52)],
        'vendor': ['Café Müller GmbH', 'ACME Supplies Ltd', 'Northwind Traders'] * 4,
        'date': ['2025-03-14'] * 12,
        'amount': [f'{100 + n * 7},50' for n in range(12)],
        'currency': ['EUR'] * 12,
    })
    invoices.to_csv(OUT / 'sample.csv', index=False)
    invoices.to_csv(OUT / 'sample_latin1_semicolon.csv', index=False, sep=';', encoding='cp1252')
    line_items = pd.DataFrame(TABLE[1:], columns=TABLE[0])
    with pd.ExcelWriter(OUT / 'sample.xlsx', engine='openpyxl') as writer:
        invoices.to_excel(writer, sheet_name='Invoices', index=False)
        line_items.to_excel(writer, sheet_name='LineItems', index=False)

    print('Fixtures written to', OUT.resolve())


if __name__ == '__main__':
    main()