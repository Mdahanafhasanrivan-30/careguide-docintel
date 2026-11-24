import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

CURRENCY_SYMBOLS = {
    'US$': 'USD', '$': 'USD', '€': 'EUR', '£': 'GBP',
    '৳': 'BDT', 'Tk': 'BDT', 'TK': 'BDT', '₹': 'INR', '¥': 'JPY',
}

# Day-first formats come before month-first ones on purpose (Bangladesh/Europe).
DATE_FORMATS = [
    '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y',
    '%d %B %Y', '%d %b %Y', '%B %d, %Y', '%b %d, %Y', '%B %d %Y', '%b %d %Y',
    '%m/%d/%Y',
]


def parse_amount(text: str) -> Decimal | None:
    """'1,234.56', '1.234,56', '$ 245.00', '(12.50)' -> Decimal. None if not a number."""
    if not text or not text.strip():
        return None
    s = text.strip()
    negative = s.startswith('-') or (s.startswith('(') and s.endswith(')'))
    s = re.sub(r'[^\d.,]', '', s)          # drop symbols, spaces, letters
    if not any(ch.isdigit() for ch in s):
        return None
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):     # 1.234,56 -> European
            s = s.replace('.', '').replace(',', '.')
        else:                               # 1,234.56 -> English
            s = s.replace(',', '')
    elif ',' in s:
        head, _, tail = s.rpartition(',')
        if len(tail) in (1, 2):             # 100,50 -> decimal comma
            s = head.replace(',', '') + '.' + tail
        else:                               # 1,234 -> thousands
            s = s.replace(',', '')
    elif s.count('.') > 1:                  # 1.234.567 -> thousands dots
        s = s.replace('.', '')
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative else value


def _clean_date_text(text: str) -> str:
    s = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', text.strip())   # 14th -> 14
    return re.sub(r'\s+', ' ', s)


def _all_date_readings(text: str) -> list[date]:
    s = _clean_date_text(text)
    found: list[date] = []
    for fmt in DATE_FORMATS:
        try:
            d = datetime.strptime(s, fmt).date()
        except ValueError:
            continue
        if d not in found:
            found.append(d)
    return found


def parse_date(text: str) -> date | None:
    readings = _all_date_readings(text) if text else []
    return readings[0] if readings else None


def date_is_ambiguous(text: str) -> bool:
    """True for 03/04/2025: 3 April or March 4 are both valid."""
    return len(_all_date_readings(text)) > 1 if text else False


def parse_currency(text: str) -> str | None:
    if not text or not text.strip():
        return None
    s = text.strip()
    if re.fullmatch(r'[A-Za-z]{3}', s):
        return s.upper()
    for symbol in sorted(CURRENCY_SYMBOLS, key=len, reverse=True):   # 'US$' before '$'
        if symbol in s:
            return CURRENCY_SYMBOLS[symbol]
    return None


def parse_text(text: str) -> str | None:
    s = re.sub(r'\s+', ' ', text).strip() if text else ''
    return s or None