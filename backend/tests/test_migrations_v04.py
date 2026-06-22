from __future__ import annotations

import uuid

from fastapi_users.password import PasswordHelper
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.db.models.uploads import ProcessingStage, UserUpload


async def _table_columns(db: AsyncSession, table: str) -> set[str]:
    result = await db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :table",
        ),
        {"table": table},
    )
    return {row[0] for row in result.all()}


async def _table_exists(db: AsyncSession, table: str) -> bool:
    result = await db.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables "
            "  WHERE table_schema = 'public' AND table_name = :table"
            ")",
        ),
        {"table": table},
    )
    return bool(result.scalar_one())


async def test_v04_migration_upgrade(db: AsyncSession) -> None:
    upload_cols = await _table_columns(db, "user_uploads")
    assert {"processing_stage", "chunk_count", "processing_error"}.issubset(upload_cols)

    chat_request_cols = await _table_columns(db, "chat_requests")
    assert {"cost_usd", "idempotency_key"}.issubset(chat_request_cols)

    assert await _table_exists(db, "llm_usage_events")
    assert await _table_exists(db, "message_feedback")
    assert await _table_exists(db, "idempotency_keys")

    llm_cols = await _table_columns(db, "llm_usage_events")
    assert {
        "user_id",
        "chat_request_id",
        "session_id",
        "agent_role",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "cost_usd",
        "created_at",
    }.issubset(llm_cols)

    feedback_cols = await _table_columns(db, "message_feedback")
    assert {"user_id", "message_id", "rating", "reason", "created_at", "updated_at"}.issubset(
        feedback_cols,
    )

    idempotency_cols = await _table_columns(db, "idempotency_keys")
    assert {"user_id", "key", "body_hash", "chat_request_id", "expires_at"}.issubset(
        idempotency_cols,
    )


async def test_user_upload_processing_stage_default(db: AsyncSession) -> None:
    from dharmiq.db.models.users import User

    helper = PasswordHelper()
    user = User(
        id=uuid.uuid4(),
        email=f"v04-upload-{uuid.uuid4()}@example.com",
        hashed_password=helper.hash("securepassword123"),
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db.add(user)
    await db.flush()

    upload = UserUpload(
        id=uuid.uuid4(),
        user_id=user.id,
        original_filename="notice.pdf",
        file_path="/tmp/notice.pdf",
        mime_type="application/pdf",
        size_bytes=2048,
        content_hash="hash-v04",
    )
    db.add(upload)
    await db.commit()
    await db.refresh(upload)

    assert upload.processing_stage == ProcessingStage.UPLOADED.value
    assert upload.chunk_count == 0
    assert upload.processing_error is None


async def test_models_import() -> None:
    from dharmiq.db.models import (
        IdempotencyKey,
        LlmUsageEvent,
        MessageFeedback,
        ProcessingStage,
    )

    assert LlmUsageEvent.__tablename__ == "llm_usage_events"
    assert MessageFeedback.__tablename__ == "message_feedback"
    assert IdempotencyKey.__tablename__ == "idempotency_keys"
    assert ProcessingStage.READY.value == "ready"


async def test_settings_load_cost_limits_and_beat_schedule() -> None:
    from dharmiq.config.settings import get_settings, load_settings

    get_settings.cache_clear()
    settings = load_settings("dev")
    assert settings.cost_limits.enforce is True
    assert settings.cost_limits.per_session_usd == 1.0
    assert settings.cost_limits.per_account_monthly_usd == 10.0
    assert settings.beat_schedule.enabled is True

    get_settings.cache_clear()
    docker_settings = load_settings("docker")
    assert docker_settings.beat_schedule.enabled is False
    assert docker_settings.cost_limits.enforce is True

    get_settings.cache_clear()
