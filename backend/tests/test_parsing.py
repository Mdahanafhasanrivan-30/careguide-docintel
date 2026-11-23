import pymupdf
import pytest

from app.pipeline import parser
from app.pipeline.detect import detect_type
from app.pipeline.errors import (
    CorruptFile, FileTooLarge, PasswordProtected, UnsupportedFileType,
)
from app.pipeline.parser import parse_document


@pytest.mark.parametrize('name, kind', [
    ('invoice_digital.pdf', 'pdf'),
    ('invoice_scanned.pdf', 'pdf'),
    ('invoice_clean.png', 'image'),
    ('invoice_skewed.jpg', 'image'),
    ('invoice_multipage.tiff', 'image'),
    ('sample.xlsx', 'xlsx'),
    ('sample.csv', 'csv'),
    ('sample_latin1_semicolon.csv', 'csv'),
])
def test_detect_type(fx, name, kind):
    assert detect_type(fx(name), name).kind == kind


def test_content_beats_extension(fx):
    assert detect_type(fx('invoice_clean.png'), 'renamed.pdf').kind == 'image'


def test_digital_pdf_uses_text_layer(fx):
    doc = parse_document(fx('invoice_digital.pdf'), 'invoice_digital.pdf')
    assert doc.page_count == 1
    assert doc.pages[0].method == 'text_layer'
    assert doc.pages[0].ocr_confidence is None
    assert 'INV-2025-0042' in doc.full_text()
    assert '269.50' in doc.full_text()


def test_scanned_pdf_falls_back_to_ocr(fx):
    doc = parse_document(fx('invoice_scanned.pdf'), 'invoice_scanned.pdf')
    page = doc.pages[0]
    assert page.method == 'ocr'
    assert page.ocr_confidence is not None and page.ocr_confidence > 60
    text = doc.full_text().replace(' ', '')
    assert 'INV-2025-0042' in text
    assert '269.50' in text


@pytest.mark.parametrize('name', ['invoice_clean.png', 'invoice_skewed.jpg', 'invoice_lowres.png'])
def test_images_are_ocrd(fx, name):
    doc = parse_document(fx(name), name)
    assert doc.file_kind == 'image'
    assert doc.pages[0].method == 'ocr'
    assert 'Northwind' in doc.full_text()


def test_multipage_tiff(fx):
    doc = parse_document(fx('invoice_multipage.tiff'), 'invoice_multipage.tiff')
    assert doc.page_count == 2
    assert [p.page_number for p in doc.pages] == [1, 2]


def test_csv_utf8(fx):
    doc = parse_document(fx('sample.csv'), 'sample.csv')
    assert doc.file_kind == 'csv'
    assert 'invoice_number' in doc.full_text()
    assert 'Café Müller GmbH' in doc.full_text()


def test_csv_latin1_with_semicolons(fx):
    doc = parse_document(fx('sample_latin1_semicolon.csv'), 'sample_latin1_semicolon.csv')
    first_row = doc.full_text().splitlines()[0].split('\t')
    assert len(first_row) == 5            # delimiter was detected
    assert 'Café Müller GmbH' in doc.full_text()   # encoding was detected


def test_xlsx_has_one_page_per_sheet(fx):
    doc = parse_document(fx('sample.xlsx'), 'sample.xlsx')
    assert doc.page_count == 2
    assert [p.sheet_name for p in doc.pages] == ['Invoices', 'LineItems']
    assert all(p.method == 'table' for p in doc.pages)
    assert 'Widget A' in doc.pages[1].text


def test_filename_is_sanitised(fx):
    doc = parse_document(fx('sample.csv'), '../../etc/passwd.csv')
    assert doc.filename == 'passwd.csv'


# ---- failure paths -------------------------------------------------------

def test_empty_file():
    with pytest.raises(CorruptFile):
        parse_document(b'', 'x.pdf')


def test_corrupt_pdf():
    with pytest.raises(CorruptFile):
        parse_document(b'%PDF-1.4\nthis is not really a pdf', 'broken.pdf')


def test_unsupported_binary():
    with pytest.raises(UnsupportedFileType):
        parse_document(b'MZ\x90\x00\x03\x00\x00\x00' + bytes(300), 'virus.pdf')


def test_password_protected_pdf(fx):
    src = pymupdf.open(stream=fx('invoice_digital.pdf'), filetype='pdf')
    locked = src.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw='secret', owner_pw='owner')
    with pytest.raises(PasswordProtected):
        parse_document(locked, 'locked.pdf')


def test_file_too_large(fx, monkeypatch):
    monkeypatch.setattr(parser, 'MAX_FILE_BYTES', 10)
    with pytest.raises(FileTooLarge):
        parse_document(fx('sample.csv'), 'sample.csv')