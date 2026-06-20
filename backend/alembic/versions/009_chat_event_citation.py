"""Add citation event type for answer streaming.

Revision ID: 009
Revises: 008
Create Date: 2026-06-20
"""

from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE chat_request_event_type ADD VALUE IF NOT EXISTS 'citation'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values safely.
    pass
