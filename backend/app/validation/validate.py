from datetime import date

from app.schemas.invoice import InvoiceExtraction
from app.schemas.validation import ValidationReport
from app.validation.duplicates import SeenInvoice, check_duplicates, remember
from app.validation.rules import ALL_RULES, check_date_range


def validate_invoice(inv: InvoiceExtraction, seen: list[SeenInvoice] | None = None,
                     today: date | None = None) -> ValidationReport:
    """The only entry point for one invoice. Pure: no database, no network.
    seen = earlier invoices to check for duplicates; today is a parameter so tests can fix it."""
    issues = []
    for rule in ALL_RULES:
        issues.extend(rule(inv))
    issues.extend(check_date_range(inv, today or date.today()))
    issues.extend(check_duplicates(inv, seen or []))
    return ValidationReport(issues=issues)


def validate_batch(invoices: list[tuple[str, InvoiceExtraction]],
                   today: date | None = None) -> dict[str, ValidationReport]:
    """Validate (doc_id, invoice) pairs in order. Each one is checked against the ones before it."""
    seen: list[SeenInvoice] = []
    reports: dict[str, ValidationReport] = {}
    for doc_id, inv in invoices:
        reports[doc_id] = validate_invoice(inv, seen, today)
        seen.append(remember(doc_id, inv))
    return reports