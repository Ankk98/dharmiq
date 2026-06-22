from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from litellm import completion_cost
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings
from dharmiq.core.errors import UsageLimitExceededError
from dharmiq.core.logging import get_logger
from dharmiq.db.models.chats import ChatRequest
from dharmiq.db.models.llm_usage import LlmUsageEvent

logger = get_logger(__name__)


def _decimal_cost(value: float | str | Decimal) -> Decimal:
    return Decimal(str(value))


def _compute_cost_usd(response: dict[str, Any]) -> Decimal:
    try:
        return _decimal_cost(completion_cost(completion_response=response))
    except Exception as exc:
        logger.warning("llm_cost_compute_failed", error=str(exc))
        return Decimal("0")


async def record_llm_usage(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    chat_request_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
    agent_role: str,
    model: str,
    response: dict[str, Any],
) -> Decimal:
    usage = response.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    cost_usd = _compute_cost_usd(response)

    event = LlmUsageEvent(
        user_id=user_id,
        chat_request_id=chat_request_id,
        session_id=session_id,
        agent_role=agent_role,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
    )
    db.add(event)

    if chat_request_id is not None:
        result = await db.execute(select(ChatRequest).where(ChatRequest.id == chat_request_id))
        chat_request = result.scalar_one_or_none()
        if chat_request is not None:
            chat_request.cost_usd = _decimal_cost(chat_request.cost_usd) + cost_usd

    await db.flush()
    return cost_usd


async def get_session_cost_usd(db: AsyncSession, session_id: uuid.UUID) -> Decimal:
    result = await db.execute(
        select(func.coalesce(func.sum(ChatRequest.cost_usd), 0)).where(
            ChatRequest.session_id == session_id,
        )
    )
    return _decimal_cost(result.scalar_one())


async def get_monthly_user_cost_usd(db: AsyncSession, user_id: uuid.UUID) -> Decimal:
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.coalesce(func.sum(LlmUsageEvent.cost_usd), 0)).where(
            LlmUsageEvent.user_id == user_id,
            LlmUsageEvent.created_at >= month_start,
        )
    )
    return _decimal_cost(result.scalar_one())


async def check_usage_limits(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    settings: Settings,
) -> None:
    limits = settings.cost_limits
    if not limits.enforce:
        return

    session_cap = _decimal_cost(limits.per_session_usd)
    session_cost = await get_session_cost_usd(db, session_id)
    if session_cost >= session_cap:
        raise UsageLimitExceededError(
            "Conversation usage limit reached",
            limit="conversation",
            details={"spent_usd": str(session_cost), "cap_usd": str(session_cap)},
        )

    monthly_cap = _decimal_cost(limits.per_account_monthly_usd)
    monthly_cost = await get_monthly_user_cost_usd(db, user_id)
    if monthly_cost >= monthly_cap:
        raise UsageLimitExceededError(
            "Monthly account usage limit reached",
            limit="account_monthly",
            details={"spent_usd": str(monthly_cost), "cap_usd": str(monthly_cap)},
        )
