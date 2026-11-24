from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 1) What the LLM must return. Strings only, no nulls:
#    "" means "not printed in the document". Code turns strings into
#    Decimal / date later, so the model never does arithmetic or formatting.
# ---------------------------------------------------------------------------


class RawField(BaseModel):
    value: str = Field(description='The value exactly as printed, or "" if it is not in the document')
    evidence: str = Field(description='A short exact quote from the document that contains the value, or ""')
    confidence: float = Field(description='How sure you are, from 0 to 1')


class RawLineItem(BaseModel):
    description: str
    quantity: str
    unit_price: str
    amount: str
    evidence: str = Field(description='The exact line from the document this item comes from')


class RawExtraction(BaseModel):
    invoice_number: RawField
    invoice_date: RawField
    supplier_name: RawField
    customer_name: RawField
    subtotal: RawField
    tax: RawField
    total: RawField
    currency: RawField
    line_items: list[RawLineItem]


# ---------------------------------------------------------------------------
# 2) What our code returns after checking and normalising.
# ---------------------------------------------------------------------------

Status = Literal['ok', 'missing', 'no_evidence', 'unparseable']


class FieldBase(BaseModel):
    raw: str | None = None            # as printed
    evidence: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    status: Status = 'missing'


class TextField(FieldBase):
    value: str | None = None


class MoneyField(FieldBase):
    value: Decimal | None = None


class DateField(FieldBase):
    value: date | None = None


class LineItem(BaseModel):
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class InvoiceExtraction(BaseModel):
    invoice_number: TextField
    invoice_date: DateField
    supplier_name: TextField
    customer_name: TextField
    subtotal: MoneyField
    tax: MoneyField
    total: MoneyField
    currency: TextField
    line_items: list[LineItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    prompt_version: str
    model: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0