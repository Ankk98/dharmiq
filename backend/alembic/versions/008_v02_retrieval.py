"""v0.2 retrieval columns: context_text, parent chunks, metadata, search_vector.

Revision ID: 008
Revises: 007
Create Date: 2026-06-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_retrieval_columns(table: str) -> None:
    op.add_column(table, sa.Column("context_text", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("parent_chunk_id", sa.UUID(), nullable=True))
    op.add_column(
        table,
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        table,
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', coalesce(text, ''))", persisted=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        f"fk_{table}_parent_chunk_id",
        table,
        table,
        ["parent_chunk_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        f"ix_{table}_parent_chunk_id",
        table,
        ["parent_chunk_id"],
        unique=False,
    )
    op.create_index(
        f"ix_{table}_search_vector",
        table,
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )


def _drop_retrieval_columns(table: str) -> None:
    op.drop_index(f"ix_{table}_search_vector", table_name=table)
    op.drop_index(f"ix_{table}_parent_chunk_id", table_name=table)
    op.drop_constraint(f"fk_{table}_parent_chunk_id", table, type_="foreignkey")
    op.drop_column(table, "search_vector")
    op.drop_column(table, "metadata")
    op.drop_column(table, "parent_chunk_id")
    op.drop_column(table, "context_text")


def upgrade() -> None:
    _add_retrieval_columns("document_chunks")
    _add_retrieval_columns("user_upload_chunks")


def downgrade() -> None:
    _drop_retrieval_columns("user_upload_chunks")
    _drop_retrieval_columns("document_chunks")
