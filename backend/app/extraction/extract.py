import time
from pathlib import Path
from typing import Callable

from app.extraction.errors import ExtractionError
from app.extraction.evidence import evidence_found, value_in_evidence
from app.extraction.llm import LLMClient
from app.extraction.normalise import (
    date_is_ambiguous, parse_amount, parse_currency, parse_date, parse_text,
)
from app.schemas.invoice import (
    DateField, FieldBase, InvoiceExtraction, LineItem, MoneyField, RawField, TextField,
)

PROMPT_VERSION = 'extract_invoice_v1'
PROMPT_DIR = Path(__file__).parent / 'prompts'
MAX_CHARS = 60_000     # about 15k tokens; longer documents are cut (see warnings)


def load_prompt(version: str = PROMPT_VERSION) -> str:
    return (PROMPT_DIR / f'{version}.md').read_text(encoding='utf-8')


def build_user_message(text: str) -> str:
    # A document must not be able to close our tag and "escape" into instructions.
    safe = text.replace('</document>', '</ document>')
    return f'Extract the invoice fields from this document.\n<document>\n{safe}\n</document>'


def _check(name: str, raw: RawField, source: str, parse: Callable, cls: type[FieldBase],
           warnings: list[str]) -> FieldBase:
    value_text = raw.value.strip()
    confidence = min(max(raw.confidence, 0.0), 1.0)
    if not value_text:
        return cls(status='missing')
    evidence = raw.evidence.strip()
    if not (evidence_found(evidence, source) and value_in_evidence(value_text, evidence)):
        warnings.append(f'{name}: "{value_text}" has no matching evidence in the document; dropped')
        return cls(raw=value_text, evidence=evidence or None, status='no_evidence')
    value = parse(value_text)
    if value is None:
        warnings.append(f'{name}: could not read "{value_text}"')
        return cls(raw=value_text, evidence=evidence, confidence=confidence, status='unparseable')
    return cls(value=value, raw=value_text, evidence=evidence, confidence=confidence, status='ok')


def _line_items(raw_items, source: str, warnings: list[str]) -> list[LineItem]:
    items: list[LineItem] = []
    for number, item in enumerate(raw_items, start=1):
        if not evidence_found(item.evidence, source):
            warnings.append(f'line item {number}: evidence not found in the document; dropped')
            continue
        items.append(LineItem(
            description=parse_text(item.description),
            quantity=parse_amount(item.quantity),
            unit_price=parse_amount(item.unit_price),
            amount=parse_amount(item.amount),
        ))
    return items


def extract_invoice(text: str, client: LLMClient,
                    prompt_version: str = PROMPT_VERSION) -> InvoiceExtraction:
    if not text or not text.strip():
        raise ExtractionError('No text to extract from')
    warnings: list[str] = []
    if len(text) > MAX_CHARS:
        warnings.append(f'Document text cut from {len(text)} to {MAX_CHARS} characters')
        text = text[:MAX_CHARS]

    started = time.perf_counter()
    result = client.extract(load_prompt(prompt_version), build_user_message(text))
    latency_ms = round((time.perf_counter() - started) * 1000)
    raw = result.raw

    def check(name, parse, cls):
        return _check(name, getattr(raw, name), text, parse, cls, warnings)

    invoice_date = check('invoice_date', parse_date, DateField)
    if invoice_date.status == 'ok' and date_is_ambiguous(invoice_date.raw):
        warnings.append(f'invoice_date: "{invoice_date.raw}" is ambiguous; read as day first')

    return InvoiceExtraction(
        invoice_number=check('invoice_number', parse_text, TextField),
        invoice_date=invoice_date,
        supplier_name=check('supplier_name', parse_text, TextField),
        customer_name=check('customer_name', parse_text, TextField),
        subtotal=check('subtotal', parse_amount, MoneyField),
        tax=check('tax', parse_amount, MoneyField),
        total=check('total', parse_amount, MoneyField),
        currency=check('currency', parse_currency, TextField),
        line_items=_line_items(raw.line_items, text, warnings),
        warnings=warnings,
        prompt_version=prompt_version,
        model=result.model,
        latency_ms=latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )