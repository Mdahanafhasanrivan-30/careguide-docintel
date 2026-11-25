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
    discount: str = Field(default='', description='The line discount as printed (an amount or a '
                                                  'percentage such as "10%"), or "" if the row has none')
    evidence: str = Field(description='The exact line from the document this item comes from')


class RawAdjustment(BaseModel):
    label: str = Field(description='The row label as printed, e.g. "Discount (5%)", "Shipping", "SGST 9%", "Rounding"')
    amount: str = Field(description='The amount exactly as printed, including any minus sign or brackets')
    evidence: str = Field(description='The exact line from the document this row comes from')


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
    adjustments: list[RawAdjustment] = Field(
        default_factory=list,
        description='Rows between subtotal and total that change the total: discounts, shipping, '
                    'fees, extra tax lines, rounding. Not payments or balance due.')

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        """The schema sent to Gemini marks every field required, so the model always answers
        'adjustments' ([] when there are none). Python code may still leave it out (default [])."""
        schema = super().model_json_schema(*args, **kwargs)
        for part in [schema, *schema.get('$defs', {}).values()]:
            part['required'] = list(part['properties'])
        return schema


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
    discount: Decimal | None = None           # money taken off this line, e.g. 5.00
    discount_percent: Decimal | None = None   # or a percentage, e.g. 10 for "10%"


AdjustmentKind = Literal['discount', 'charge', 'tax', 'rounding']


class Adjustment(BaseModel):
    label: str | None = None
    kind: AdjustmentKind
    amount: Decimal | None = None     # signed: a discount is negative, a charge positive
    raw: str | None = None            # as printed


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
    adjustments: list[Adjustment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    prompt_version: str
    model: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0