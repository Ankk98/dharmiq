"""Add chat_requests table.

Revision ID: 005
Revises: 004
Create Date: 2026-05-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

chat_request_status = postgresql.ENUM(
    "pending",
    "running",
    "completed",
    "failed",
    name="chat_request_status",
    create_type=False,
)


def upgrade() -> None:
    chat_request_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "chat_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "running",
                "completed",
                "failed",
                name="chat_request_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("llm_model", sa.String(length=255), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_requests_session_id"), "chat_requests", ["session_id"], unique=False)
    op.create_index(op.f("ix_chat_requests_user_id"), "chat_requests", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_requests_user_id"), table_name="chat_requests")
    op.drop_index(op.f("ix_chat_requests_session_id"), table_name="chat_requests")
    op.drop_table("chat_requests")
    chat_request_status.drop(op.get_bind(), checkfirst=True)
