from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, computed_field

Severity = Literal['error', 'warning']


class Issue(BaseModel):
    code: str                         # stable name, e.g. 'total_mismatch'
    severity: Severity                # error = a number is wrong; warning = a person should look
    field: str | None = None          # which field, if one
    message: str                      # plain English for the reviewer
    expected: Decimal | None = None   # what the arithmetic says
    found: Decimal | None = None      # what the invoice prints


class ValidationReport(BaseModel):
    issues: list[Issue] = Field(default_factory=list)

    @computed_field
    @property
    def needs_review(self) -> bool:
        return bool(self.issues)

    @computed_field
    @property
    def review_reasons(self) -> list[str]:
        return [issue.message for issue in self.issues]