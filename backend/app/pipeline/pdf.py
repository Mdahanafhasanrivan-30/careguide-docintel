import cv2
import numpy as np
import pymupdf

from app.pipeline.errors import CorruptFile, FileTooLarge, PasswordProtected
from app.pipeline.ocr import ocr_image
from app.schemas.parsed import PageResult

MIN_CHARS_PER_PAGE = 50   # fewer characters than this -> treat page as scanned
OCR_DPI = 300
MAX_PAGES = 1000


def parse_pdf(data: bytes) -> tuple[list[PageResult], list[str]]:
    try:
        doc = pymupdf.open(stream=data, filetype='pdf')
    except Exception as exc:
        raise CorruptFile(f'Cannot open PDF: {exc}') from exc

    pages: list[PageResult] = []
    warnings: list[str] = []
    with doc:
        if doc.needs_pass:
            raise PasswordProtected('PDF is password protected')
        if doc.page_count == 0:
            raise CorruptFile('PDF has no readable pages')
        if doc.page_count > MAX_PAGES:
            raise FileTooLarge(f'PDF has {doc.page_count} pages (limit {MAX_PAGES})')

        for index in range(doc.page_count):
            number = index + 1
            try:
                page = doc[index]
                text = page.get_text('text', sort=True).strip()
                if len(text) >= MIN_CHARS_PER_PAGE:
                    pages.append(PageResult(page_number=number, text=text, method='text_layer'))
                    continue

                pix = page.get_pixmap(dpi=OCR_DPI, colorspace=pymupdf.csRGB, alpha=False)
                rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                ocr_text, conf = ocr_image(bgr)
                pages.append(PageResult(
                    page_number=number, text=ocr_text, method='ocr', ocr_confidence=conf,
                ))
                if conf is None:
                    warnings.append(f'Page {number}: no text found (blank page?)')
                elif conf < 60:
                    warnings.append(f'Page {number}: low OCR confidence ({conf})')
            except Exception as exc:
                # One bad page must not destroy a 500-page document.
                pages.append(PageResult(page_number=number, text='', method='ocr'))
                warnings.append(f'Page {number}: failed ({exc})')
    return pages, warnings