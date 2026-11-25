"""Cut a document into pieces for semantic search. Pure: no database."""
from datetime import date
from decimal import Decimal

CHUNK_CHARS = 800      # about 150-200 words: small enough that one chunk is about one thing
OVERLAP_CHARS = 100    # words repeated at the start of the next chunk, so a sentence cut in two is still found
MAX_CHUNKS = 500       # about 400,000 characters; a 1000-page PDF is cut here (noted in the limits)


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Split on whitespace into chunks of at most `size` characters (a longer single word
    becomes its own chunk). Each chunk starts with the last ~`overlap` characters of the one before."""
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for word in text.split():
        if current and length + len(word) + 1 > size:
            chunks.append(' '.join(current))
            tail: list[str] = []
            tail_length = 0
            for previous in reversed(current):
                if tail_length + len(previous) + 1 > overlap:
                    break
                tail.insert(0, previous)
                tail_length += len(previous) + 1
            current, length = tail, tail_length
            if length + len(word) + 1 > size:   # overlap + this word would not fit: start clean
                current, length = [], 0
        current.append(word)
        length += len(word) + 1
    if current:
        chunks.append(' '.join(current))
    return chunks


def header_text(filename: str, invoice_number: str | None, supplier_name: str | None,
                invoice_date: date | None, total: Decimal | None, currency: str | None) -> str:
    """One short sentence with the key values. It becomes chunk 0, so a question like
    'invoices from Padma Medical' can match even when the OCR text is messy."""
    parts = [f'Invoice {invoice_number}' if invoice_number else 'Invoice']
    if supplier_name:
        parts.append(f'from {supplier_name}')
    if invoice_date:
        parts.append(f'dated {invoice_date.isoformat()}')
    if total is not None:
        parts.append(f'total {total} {currency or ""}'.strip())
    return ' '.join(parts) + f'. File {filename}.'