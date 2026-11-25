from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.session import get_db
from app.schemas.api import DocumentSummary, SearchHit, SearchResponse
from app.search.embed import Embedder, get_embedder
from app.search.search import Filters, filter_only, hybrid_search, keyword_search, semantic_search

router = APIRouter(prefix='/api/v1/search', tags=['search'], dependencies=[Depends(require_api_key)])


def embedder_provider() -> Callable[[], Embedder]:
    """Returns a function, not the model: keyword search must work even if the model
    cannot be loaded, and tests replace this with FakeEmbedder."""
    return get_embedder


@router.get('', response_model=SearchResponse)
def search(q: str = Query('', max_length=500),
           mode: Literal['keyword', 'semantic', 'hybrid'] = 'hybrid',
           status: str | None = None, needs_review: bool | None = None,
           supplier: str | None = Query(None, max_length=200), currency: str | None = Query(None, max_length=10),
           date_from: date | None = None, date_to: date | None = None,
           min_total: Decimal | None = None, max_total: Decimal | None = None,
           limit: int = Query(20, ge=1, le=100),
           db: Session = Depends(get_db),
           make_embedder: Callable[[], Embedder] = Depends(embedder_provider)):
    f = Filters(status, needs_review, supplier, currency, date_from, date_to, min_total, max_total)
    q = q.strip()
    if not q:
        hits, used = filter_only(db, f, limit), 'filter'
    elif mode == 'keyword':
        hits, used = keyword_search(db, q, f, limit), mode
    else:
        try:
            embedder = make_embedder()
        except Exception:   # model missing or download failed: say so, do not crash
            raise HTTPException(503, 'Semantic search is unavailable right now; use mode=keyword')
        search_fn = semantic_search if mode == 'semantic' else hybrid_search
        hits, used = search_fn(db, q, f, limit, embedder), mode
    return SearchResponse(query=q, mode=used, count=len(hits), hits=[
        SearchHit(document=DocumentSummary.model_validate(h.document), score=h.score, snippet=h.snippet)
        for h in hits])