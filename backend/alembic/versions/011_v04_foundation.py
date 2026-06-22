"""v0.4 foundation schema: upload stages, LLM usage, feedback, idempotency.

Revision ID: 011
Revises: 010
Create Date: 2026-06-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROCESSING_STAGES = ("uploaded", "parsed", "chunking", "embedding", "ready", "failed")


def upgrade() -> None:
    op.add_column(
        "user_uploads",
        sa.Column(
            "processing_stage",
            sa.String(length=32),
            server_default="uploaded",
            nullable=False,
        ),
    )
    op.add_column(
        "user_uploads",
        sa.Column("chunk_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("user_uploads", sa.Column("processing_error", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_user_uploads_processing_stage",
        "user_uploads",
        sa.text(
            "processing_stage IN ('uploaded','parsed','chunking','embedding','ready','failed')",
        ),
    )

    op.execute(
        """
        UPDATE user_uploads u
        SET processing_stage = 'ready',
            chunk_count = (
                SELECT COUNT(*) FROM user_upload_chunks c WHERE c.upload_id = u.id
            )
        WHERE EXISTS (SELECT 1 FROM user_upload_chunks c WHERE c.upload_id = u.id)
          AND u.deleted_at IS NULL
        """,
    )
    op.execute(
        """
        UPDATE user_uploads
        SET processing_stage = 'failed',
            processing_error = 'Unknown (pre-v0.4)'
        WHERE deleted_at IS NULL
          AND processing_stage = 'uploaded'
          AND created_at < NOW() - INTERVAL '1 hour'
        """,
    )

    op.add_column(
        "chat_requests",
        sa.Column(
            "cost_usd",
            sa.Numeric(precision=12, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "chat_requests",
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
    )

    op.create_table(
        "llm_usage_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("chat_request_id", sa.UUID(), nullable=True),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("agent_role", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chat_request_id"], ["chat_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_llm_usage_events_chat_request_id"),
        "llm_usage_events",
        ["chat_request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_llm_usage_events_session_id"),
        "llm_usage_events",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_llm_usage_events_user_id_created_at",
        "llm_usage_events",
        ["user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "message_feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("rating", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rating IN ('up', 'down')", name="ck_message_feedback_rating"),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "message_id", name="uq_message_feedback_user_message"),
    )
    op.create_index(
        op.f("ix_message_feedback_message_id"),
        "message_feedback",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_feedback_user_id"),
        "message_feedback",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("body_hash", sa.String(length=64), nullable=False),
        sa.Column("chat_request_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chat_request_id"], ["chat_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_idempotency_keys_user_key"),
    )
    op.create_index(
        op.f("ix_idempotency_keys_expires_at"),
        "idempotency_keys",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_idempotency_keys_user_id"),
        "idempotency_keys",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_idempotency_keys_user_id"), table_name="idempotency_keys")
    op.drop_index(op.f("ix_idempotency_keys_expires_at"), table_name="idempotency_keys")
    op.drop_table("idempotency_keys")

    op.drop_index(op.f("ix_message_feedback_user_id"), table_name="message_feedback")
    op.drop_index(op.f("ix_message_feedback_message_id"), table_name="message_feedback")
    op.drop_table("message_feedback")

    op.drop_index("ix_llm_usage_events_user_id_created_at", table_name="llm_usage_events")
    op.drop_index(op.f("ix_llm_usage_events_session_id"), table_name="llm_usage_events")
    op.drop_index(op.f("ix_llm_usage_events_chat_request_id"), table_name="llm_usage_events")
    op.drop_table("llm_usage_events")

    op.drop_column("chat_requests", "idempotency_key")
    op.drop_column("chat_requests", "cost_usd")

    op.drop_constraint("ck_user_uploads_processing_stage", "user_uploads", type_="check")
    op.drop_column("user_uploads", "processing_error")
    op.drop_column("user_uploads", "chunk_count")
    op.drop_column("user_uploads", "processing_stage")
