from datetime import date, timedelta
from decimal import Decimal

from app.extraction.adjustments import adjustment_kind
from app.extraction.normalise import date_is_ambiguous
from app.schemas.invoice import FieldBase, InvoiceExtraction
from app.schemas.validation import Issue
from app.validation.currencies import AMBIGUOUS_SYMBOLS, ISO_4217

TOLERANCE = Decimal('0.01')        # one cent: allowed rounding difference
MAX_ROUNDING = Decimal('1.00')     # a rounding line bigger than this is suspicious
LOW_CONFIDENCE = 0.5
MAX_AGE_YEARS = 5
ZERO = Decimal('0')

REQUIRED = ['invoice_number', 'invoice_date', 'supplier_name', 'total']
OPTIONAL = ['customer_name', 'currency', 'subtotal', 'tax']


def _differs(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) > TOLERANCE


# ---- fields -------------------------------------------------------------

def _field_problem(name: str, field: FieldBase, required: bool) -> Issue | None:
    if field.status == 'ok':
        return None
    severity = 'error' if required else 'warning'
    if field.status == 'missing':
        message = f'{name} is not printed on the invoice'
    elif field.status == 'no_evidence':
        message = f'{name}: the model\'s value "{field.raw}" was not found in the document'
    else:                                     # unparseable
        message = f'{name}: could not read "{field.raw}"'
    return Issue(code=f'{name}_{field.status}', severity=severity, field=name, message=message)


def check_fields(inv: InvoiceExtraction) -> list[Issue]:
    issues = []
    for name in REQUIRED + OPTIONAL:
        problem = _field_problem(name, getattr(inv, name), required=name in REQUIRED)
        if problem:
            issues.append(problem)
    return issues


def check_confidence(inv: InvoiceExtraction) -> list[Issue]:
    issues = []
    for name in REQUIRED + OPTIONAL:
        field = getattr(inv, name)
        if field.status == 'ok' and field.confidence < LOW_CONFIDENCE:
            issues.append(Issue(code='low_confidence', severity='warning', field=name,
                                message=f'{name}: model confidence is only {field.confidence:.2f}'))
    return issues


# ---- currency -----------------------------------------------------------

def check_currency(inv: InvoiceExtraction) -> list[Issue]:
    field = inv.currency
    if field.status != 'ok':
        return []                             # missing / unreadable: check_fields reports it
    if field.value not in ISO_4217:
        return [Issue(code='currency_unknown', severity='error', field='currency',
                      message=f'currency "{field.value}" is not an ISO 4217 code')]
    printed = (field.raw or '').strip()
    if printed in AMBIGUOUS_SYMBOLS:
        return [Issue(code='currency_assumed', severity='warning', field='currency',
                      message=f'currency is printed only as "{printed}", which can mean '
                              f'{AMBIGUOUS_SYMBOLS[printed]}; read as {field.value}')]
    return []


# ---- dates --------------------------------------------------------------

def check_date(inv: InvoiceExtraction) -> list[Issue]:
    if inv.invoice_date.status == 'ok' and date_is_ambiguous(inv.invoice_date.raw):
        return [Issue(code='ambiguous_date', severity='warning', field='invoice_date',
                      message=f'invoice_date "{inv.invoice_date.raw}" could be day-first or '
                              f'month-first; read as {inv.invoice_date.value}')]
    return []


def check_date_range(inv: InvoiceExtraction, today: date) -> list[Issue]:
    """An invoice cannot be dated in the future; a very old one is suspicious."""
    d = inv.invoice_date.value
    if inv.invoice_date.status != 'ok' or d is None:
        return []
    if d > today + timedelta(days=1):         # one day of slack for time zones
        return [Issue(code='future_date', severity='error', field='invoice_date',
                      message=f'invoice_date {d} is in the future (today is {today})')]
    if d < today - timedelta(days=365 * MAX_AGE_YEARS):
        return [Issue(code='old_date', severity='warning', field='invoice_date',
                      message=f'invoice_date {d} is more than {MAX_AGE_YEARS} years old')]
    return []


# ---- signs (negative and zero amounts) ----------------------------------

def _is_flat_discount_row(item) -> bool:
    return item.quantity is None and item.unit_price is None and \
        adjustment_kind(item.description) == 'discount'


def check_signs(inv: InvoiceExtraction) -> list[Issue]:
    total = inv.total.value
    if total is None:
        return []
    if total < 0:                             # credit note: negative lines are expected, say it once
        return [Issue(code='negative_total', severity='warning', field='total',
                      message=f'total is negative ({total}); this looks like a credit note or refund')]
    issues = []
    if total == 0:
        issues.append(Issue(code='zero_total', severity='warning', field='total',
                            message='total is 0.00; check this is a real invoice (free item, test, void)'))
    for name in ('subtotal', 'tax'):
        value = getattr(inv, name).value
        if value is not None and value < 0:
            issues.append(Issue(code='negative_amount', severity='warning', field=name,
                                message=f'{name} is negative ({value}) but the total is not'))
    for number, item in enumerate(inv.line_items, start=1):
        if _is_flat_discount_row(item):
            continue                          # 'Loyalty discount -50.00' in the table is normal
        values = [v for v in (item.quantity, item.unit_price, item.amount) if v is not None]
        if any(v < 0 for v in values):
            issues.append(Issue(code='negative_line', severity='warning', field='line_items',
                                message=f'line item {number} ({item.description}) has a negative '
                                        f'quantity, price or amount'))
    return issues


# ---- adjustments (discount, shipping, extra tax, rounding) --------------

def check_adjustments(inv: InvoiceExtraction) -> list[Issue]:
    issues = []
    for adj in inv.adjustments:
        if adj.amount is None:
            issues.append(Issue(code='adjustment_unreadable', severity='warning', field='adjustments',
                                message=f'could not read the amount of "{adj.label}" ("{adj.raw}")'))
        elif adj.kind == 'rounding' and abs(adj.amount) > MAX_ROUNDING:
            issues.append(Issue(code='large_rounding', severity='warning', field='adjustments',
                                message=f'rounding line "{adj.label}" is {adj.amount}; '
                                        f'rounding is normally under {MAX_ROUNDING}'))
    return issues


def _adjustment_sum(inv: InvoiceExtraction) -> Decimal | None:
    amounts = [adj.amount for adj in inv.adjustments]
    return None if None in amounts else sum(amounts, ZERO)


def _line_sum(inv: InvoiceExtraction) -> Decimal | None:
    amounts = [item.amount for item in inv.line_items]
    return None if not amounts or None in amounts else sum(amounts, ZERO)


# ---- totals -------------------------------------------------------------

def check_totals(inv: InvoiceExtraction) -> list[Issue]:
    """subtotal + tax + adjustments must equal total.
    A missing tax counts as 0. A missing subtotal is replaced by the sum of the line items."""
    total, tax = inv.total.value, inv.tax.value
    if total is None:
        return []                             # check_fields reports it
    if tax is None and inv.tax.status != 'missing':
        return []                             # tax printed but unreadable: do not guess 0
    adjustments = _adjustment_sum(inv)
    if adjustments is None:
        return []                             # check_adjustments reports the unreadable row
    base, base_name = inv.subtotal.value, 'subtotal'
    if base is None:
        if inv.subtotal.status != 'missing':
            return []                         # subtotal printed but unreadable: do not guess
        base, base_name = _line_sum(inv), 'line items'
        if base is None:
            return []                         # nothing to add up
    tax = tax if tax is not None else ZERO
    expected = base + tax + adjustments
    if not _differs(expected, total):
        return []
    if tax != 0 and not _differs(base + adjustments, total):
        return [Issue(code='tax_included', severity='warning', field='tax',
                      message=f'total {total} equals the {base_name} without tax; the tax {tax} '
                              f'seems to be included in the prices (check the invoice says so)')]
    names = f'{base_name} + tax' + (' + adjustments' if inv.adjustments else '')
    return [Issue(code='total_mismatch', severity='error', field='total',
                  message=f'{names} = {expected} but the invoice prints total {total} '
                          f'(difference {total - expected})',
                  expected=expected, found=total)]


# ---- line items ---------------------------------------------------------

def _line_expected(item) -> tuple[Decimal, str]:
    """quantity x unit price, minus a line discount (percentage or amount) if one is printed."""
    expected = item.quantity * item.unit_price
    how = f'{item.quantity} x {item.unit_price}'
    if item.discount_percent is not None:
        expected -= (expected * item.discount_percent / 100).quantize(TOLERANCE)
        how += f' - {item.discount_percent}%'
    if item.discount is not None:
        expected -= item.discount
        how += f' - {item.discount}'
    return expected, how


def check_line_items(inv: InvoiceExtraction) -> list[Issue]:
    if not inv.line_items:
        return [Issue(code='no_line_items', severity='warning', field='line_items',
                      message='no line items were extracted')]
    issues = []
    for number, item in enumerate(inv.line_items, start=1):
        if item.amount is None:
            issues.append(Issue(code='line_item_incomplete', severity='warning', field='line_items',
                                message=f'line item {number} ({item.description}) has no amount'))
            continue
        if item.quantity is None and item.unit_price is None:
            continue                          # flat row such as 'Delivery fee 15.00': nothing to multiply
        if item.quantity is None or item.unit_price is None:
            issues.append(Issue(code='line_item_incomplete', severity='warning', field='line_items',
                                message=f'line item {number} ({item.description}): quantity or '
                                        f'unit price is missing'))
            continue
        expected, how = _line_expected(item)
        if _differs(expected, item.amount):
            issues.append(Issue(code='line_amount_mismatch', severity='error', field='line_items',
                                message=f'line item {number}: {how} = {expected} but the invoice '
                                        f'prints {item.amount}',
                                expected=expected, found=item.amount))
    line_sum, subtotal = _line_sum(inv), inv.subtotal.value
    if line_sum is not None and subtotal is not None and _differs(line_sum, subtotal):
        issues.append(Issue(code='line_items_sum_mismatch', severity='error', field='subtotal',
                            message=f'line items add up to {line_sum} but the invoice prints '
                                    f'subtotal {subtotal}',
                            expected=line_sum, found=subtotal))
    return issues


# Every rule takes the invoice and returns a list of issues. check_date_range also needs today.
ALL_RULES = [check_fields, check_confidence, check_currency, check_date, check_signs,
             check_adjustments, check_totals, check_line_items]