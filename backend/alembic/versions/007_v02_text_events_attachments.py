"""v0.2 text tiers, chat events, session uploads, context summaries.

Revision ID: 007
Revises: 006
Create Date: 2026-06-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

chat_request_event_type = postgresql.ENUM(
    "step_start",
    "step_end",
    "step_detail",
    "token",
    "error",
    "done",
    name="chat_request_event_type",
    create_type=False,
)


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("content_compressed", sa.Text(), nullable=True))
    op.add_column("chat_messages", sa.Column("compression_version", sa.Integer(), nullable=True))

    op.add_column(
        "chat_requests",
        sa.Column("clarifier_round", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "chat_requests",
        sa.Column("force_answer", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "chat_requests",
        sa.Column("stated_assumptions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("chat_requests", sa.Column("progress_view", sa.Text(), nullable=True))

    op.create_table(
        "chat_session_uploads",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("upload_id", sa.UUID(), nullable=False),
        sa.Column(
            "attached_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_id"], ["user_uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "upload_id"),
    )
    op.create_index(
        op.f("ix_chat_session_uploads_upload_id"),
        "chat_session_uploads",
        ["upload_id"],
        unique=False,
    )

    chat_request_event_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "chat_request_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chat_request_id", sa.UUID(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("visibility", sa.Text(), nullable=False),
        sa.Column(
            "event_type",
            postgresql.ENUM(
                "step_start",
                "step_end",
                "step_detail",
                "token",
                "error",
                "done",
                name="chat_request_event_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chat_request_id"], ["chat_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_request_id", "seq", name="uq_chat_request_events_request_seq"),
    )
    op.create_index(
        op.f("ix_chat_request_events_chat_request_id"),
        "chat_request_events",
        ["chat_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_request_events_request_created",
        "chat_request_events",
        ["chat_request_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "context_summaries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("covers_message_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("facts_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_context_summaries_session_id"),
        "context_summaries",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_context_summaries_session_id"), table_name="context_summaries")
    op.drop_table("context_summaries")

    op.drop_index("ix_chat_request_events_request_created", table_name="chat_request_events")
    op.drop_index(op.f("ix_chat_request_events_chat_request_id"), table_name="chat_request_events")
    op.drop_table("chat_request_events")
    chat_request_event_type.drop(op.get_bind(), checkfirst=True)

    op.drop_index(op.f("ix_chat_session_uploads_upload_id"), table_name="chat_session_uploads")
    op.drop_table("chat_session_uploads")

    op.drop_column("chat_requests", "progress_view")
    op.drop_column("chat_requests", "stated_assumptions")
    op.drop_column("chat_requests", "force_answer")
    op.drop_column("chat_requests", "clarifier_round")

    op.drop_column("chat_messages", "compression_version")
    op.drop_column("chat_messages", "content_compressed")
