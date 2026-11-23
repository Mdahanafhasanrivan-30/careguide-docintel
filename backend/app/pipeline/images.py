import io

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.pipeline.errors import CorruptFile, FileTooLarge
from app.pipeline.ocr import ocr_image
from app.schemas.parsed import PageResult

Image.MAX_IMAGE_PIXELS = 100_000_000   # decompression-bomb guard
MAX_FRAMES = 1000


def parse_image(data: bytes) -> tuple[list[PageResult], list[str]]:
    pages: list[PageResult] = []
    warnings: list[str] = []
    try:
        with Image.open(io.BytesIO(data)) as im:
            frames = getattr(im, 'n_frames', 1)
            if frames > MAX_FRAMES:
                raise FileTooLarge(f'Image has {frames} frames (limit {MAX_FRAMES})')
            for i in range(frames):
                im.seek(i)
                frame = ImageOps.exif_transpose(im.copy()).convert('RGB')
                bgr = np.ascontiguousarray(np.array(frame)[:, :, ::-1])
                text, conf = ocr_image(bgr)
                pages.append(PageResult(
                    page_number=i + 1, text=text, method='ocr', ocr_confidence=conf,
                ))
                if conf is None:
                    warnings.append(f'Frame {i + 1}: no text found')
                elif conf < 60:
                    warnings.append(f'Frame {i + 1}: low OCR confidence ({conf})')
    except Image.DecompressionBombError as exc:
        raise FileTooLarge('Image is too large to process safely') from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise CorruptFile(f'Cannot read image: {exc}') from exc
    return pages, warnings