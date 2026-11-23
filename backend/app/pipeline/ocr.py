import cv2
import numpy as np
import pytesseract
from pytesseract import Output

from app.pipeline.errors import OcrFailed

OCR_TIMEOUT_S = 60
MIN_WIDTH_PX = 1500  # below this we upscale: Tesseract needs big enough letters


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def rotate(gray: np.ndarray, angle: float) -> np.ndarray:
    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        gray, matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,  # fill new corners with white paper
    )


def estimate_skew(gray: np.ndarray, max_angle: float = 5.0, step: float = 0.5) -> float:
    # Try small rotations; the correct one makes text rows line up, which
    # makes the row-by-row ink totals vary the most (high variance).
    scale = 1000 / max(gray.shape)
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    _, ink = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = ink.shape
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + step, step):
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), float(angle), 1.0)
        rotated = cv2.warpAffine(ink, matrix, (w, h), flags=cv2.INTER_NEAREST)
        score = float(np.var(rotated.sum(axis=1)))
        if score > best_score:
            best_angle, best_score = float(angle), score
    return best_angle


def preprocess(img: np.ndarray) -> np.ndarray:
    gray = to_gray(img)
    h, w = gray.shape
    if w < MIN_WIDTH_PX:
        factor = MIN_WIDTH_PX / w
        gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    angle = estimate_skew(gray)
    if abs(angle) >= 0.5:
        gray = rotate(gray, angle)
    return cv2.medianBlur(gray, 3)  # remove salt-and-pepper speckle


def ocr_image(
    img: np.ndarray,
    *,
    lang: str = 'eng',
    psm: int = 6,
    use_preprocess: bool = True,
) -> tuple[str, float | None]:
    # Returns (text, mean word confidence 0-100 or None if no words found).
    prepared = preprocess(img) if use_preprocess else to_gray(img)
    try:
        data = pytesseract.image_to_data(
            prepared,
            lang=lang,
            config=f'--oem 1 --psm {psm}',
            output_type=Output.DICT,
            timeout=OCR_TIMEOUT_S,
        )
    except (pytesseract.TesseractError, RuntimeError) as exc:
        raise OcrFailed(f'OCR failed: {exc}') from exc

    lines: dict[tuple[int, int, int], list[str]] = {}
    confidences: list[float] = []
    for i, word in enumerate(data['text']):
        word = word.strip()
        conf = float(data['conf'][i])
        if not word or conf < 0:
            continue
        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
        lines.setdefault(key, []).append(word)
        confidences.append(conf)

    text = '\n'.join(' '.join(words) for words in lines.values())
    mean_conf = round(sum(confidences) / len(confidences), 1) if confidences else None
    return text, mean_conf