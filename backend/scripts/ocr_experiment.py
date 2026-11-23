import itertools
import time
from pathlib import Path

import cv2

from app.pipeline.ocr import ocr_image

FIX = Path('tests/fixtures')


def norm(text: str) -> str:
    return ' '.join(text.split())


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(hypothesis: str, truth: str) -> float:
    return edit_distance(hypothesis, truth) / max(len(truth), 1)


def main() -> None:
    truth = norm((FIX / 'invoice_truth.txt').read_text(encoding='utf-8'))
    files = ['invoice_clean.png', 'invoice_skewed.jpg', 'invoice_lowres.png']
    print(f'{"file":22} {"preprocess":10} {"psm":3} {"CER":>6} {"conf":>5} {"sec":>5}')
    for name, use_pre, psm in itertools.product(files, [False, True], [3, 4, 6]):
        img = cv2.imread(str(FIX / name))
        start = time.perf_counter()
        text, conf = ocr_image(img, use_preprocess=use_pre, psm=psm)
        seconds = time.perf_counter() - start
        conf_txt = '-' if conf is None else f'{conf:.0f}'
        print(f'{name:22} {use_pre!s:10} {psm:<3} {cer(norm(text), truth):6.3f} {conf_txt:>5} {seconds:5.1f}')


if __name__ == '__main__':
    main()