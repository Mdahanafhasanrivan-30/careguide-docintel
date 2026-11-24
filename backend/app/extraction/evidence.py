import re


def _squash(text: str) -> str:
    # OCR and LLMs change spacing and case; compare without them.
    return re.sub(r'\s+', ' ', text).strip().lower()


def evidence_found(evidence: str, source: str) -> bool:
    quote = _squash(evidence or '')
    return bool(quote) and quote in _squash(source)


def value_in_evidence(value: str, evidence: str) -> bool:
    v = _squash(value or '')
    return bool(v) and v in _squash(evidence or '')