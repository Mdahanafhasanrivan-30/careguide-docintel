import secrets

from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_api_key(x_api_key: str = Header(default="")) -> None:
    # compare_digest takes the same time whether 1 or 30 characters match,
    # which defeats timing attacks that guess a key one character at a time.
    if not secrets.compare_digest(x_api_key.encode(), settings.api_key.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
