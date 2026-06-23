"""v0.6 corpus temporal metadata and statute relationships.

Revision ID: 012
Revises: 011
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

instrument_status = postgresql.ENUM(
    "in_force",
    "superseded",
    "repealed",
    name="instrument_status",
    create_type=False,
)


def upgrade() -> None:
    instrument_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "source_documents",
        sa.Column(
            "status",
            postgresql.ENUM(
                "in_force",
                "superseded",
                "repealed",
                name="instrument_status",
                create_type=False,
            ),
            nullable=False,
            server_default="in_force",
        ),
    )
    op.add_column(
        "source_documents",
        sa.Column("superseded_by_source_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "source_documents",
        sa.Column("enforcement_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "source_documents",
        sa.Column("canonical_url", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "source_documents",
        sa.Column(
            "instrument_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_table(
        "statute_relationships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("from_source_id", sa.String(length=255), nullable=False),
        sa.Column("to_source_id", sa.String(length=255), nullable=False),
        sa.Column("relationship", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_source_id",
            "to_source_id",
            "relationship",
            name="uq_statute_relationships_from_to_kind",
        ),
    )
    op.create_index(
        "ix_statute_relationships_from_source_id",
        "statute_relationships",
        ["from_source_id"],
    )
    op.create_index(
        "ix_statute_relationships_to_source_id",
        "statute_relationships",
        ["to_source_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_statute_relationships_to_source_id", table_name="statute_relationships")
    op.drop_index("ix_statute_relationships_from_source_id", table_name="statute_relationships")
    op.drop_table("statute_relationships")

    op.drop_column("source_documents", "instrument_metadata")
    op.drop_column("source_documents", "canonical_url")
    op.drop_column("source_documents", "enforcement_date")
    op.drop_column("source_documents", "superseded_by_source_id")
    op.drop_column("source_documents", "status")

    instrument_status.drop(op.get_bind(), checkfirst=True)
