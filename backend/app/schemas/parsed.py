from typing import Literal

from pydantic import BaseModel, Field

FileKind = Literal['pdf', 'image', 'xlsx', 'xls', 'csv']
Method = Literal['text_layer', 'ocr', 'table']


class PageResult(BaseModel):
    page_number: int = Field(ge=1)
    text: str
    method: Method
    ocr_confidence: float | None = Field(default=None, ge=0, le=100)
    sheet_name: str | None = None


class ParsedDocument(BaseModel):
    filename: str
    mime_type: str
    file_kind: FileKind
    page_count: int
    pages: list[PageResult]
    warnings: list[str] = Field(default_factory=list)
    processing_ms: int

    def full_text(self) -> str:
        return '\n\n'.join(p.text for p in self.pages)