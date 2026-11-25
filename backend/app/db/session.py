from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# pool_pre_ping tests a connection before using it, so a restarted database
# does not cause a burst of errors.
engine = create_engine(settings.database_url, pool_pre_ping=True)

# expire_on_commit=False: objects keep their values after commit, so we can still
# return them from an endpoint without another query.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    """FastAPI dependency: one session per request, always closed afterwards."""
    with SessionLocal() as db:
        yield db