"""Fixtures for tests that need PostgreSQL. They use a separate database, docintel_test,
so a test run never touches your real data. Without that database these tests are skipped."""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api import documents as documents_api
from app.core.config import settings
from app.db import models  # noqa: F401  (registers the tables on Base.metadata)
from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_DB_URL = os.environ.get('TEST_DATABASE_URL') or settings.database_url.rsplit('/', 1)[0] + '/docintel_test'


@pytest.fixture(scope='session')
def engine():
    eng = create_engine(TEST_DB_URL)
    try:
        with eng.connect():
            pass
    except Exception:
        pytest.skip('docintel_test database not reachable (start postgres and create it, see the guide)')
    with eng.begin() as conn:
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
    Base.metadata.drop_all(eng)      # fresh tables that match the current models
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    with engine.begin() as conn:     # empty every table after each test
        conn.execute(text('TRUNCATE processing_events, extractions, documents CASCADE'))


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'storage_dir', str(tmp_path))
    return tmp_path


@pytest.fixture
def queued(monkeypatch):
    """Replaces Redis/Celery: records which document ids would have been queued."""
    jobs = []
    monkeypatch.setattr(documents_api, 'enqueue', jobs.append)
    return jobs


@pytest.fixture
def client(db, storage, queued):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, headers={'X-API-Key': settings.api_key}) as c:
        yield c
    app.dependency_overrides.clear()