"""search: tsvector column and document_chunks

Revision ID: cea72e2267bf
Revises: 25d82cae99dd
Create Date: 2026-11-25 17:52:36.803799

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# Copied from app/db/models.py on purpose: a migration must not change when the app code changes.
SEARCH_EXPR = (
    "to_tsvector('english', coalesce(filename, '') || ' ' || coalesce(invoice_number, '') || ' ' || "
    "coalesce(supplier_name, '') || ' ' || left(coalesce(text, ''), 200000))"
)
# revision identifiers, used by Alembic.
revision: str = 'cea72e2267bf'
down_revision: Union[str, Sequence[str], None] = '25d82cae99dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.add_column('documents', sa.Column(
        'search_vector', postgresql.TSVECTOR(), sa.Computed(SEARCH_EXPR, persisted=True), nullable=True))
    op.create_index('ix_documents_search_vector', 'documents', ['search_vector'], postgresql_using='gin')
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('document_id', sa.Uuid(), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(384), nullable=False),
    )
    op.create_index('ix_document_chunks_document_id', 'document_chunks', ['document_id'])
    op.create_index('ix_document_chunks_embedding_hnsw', 'document_chunks', ['embedding'],
                    postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64},
                    postgresql_ops={'embedding': 'vector_cosine_ops'})


def downgrade() -> None:
    op.drop_table('document_chunks')
    op.drop_index('ix_documents_search_vector', table_name='documents')
    op.drop_column('documents', 'search_vector')
