from sqlalchemy import create_engine

from app.core.config import settings

# pool_pre_ping tests a connection before using it, so a restarted database
# does not cause a burst of errors.
engine = create_engine(settings.database_url, pool_pre_ping=True)
