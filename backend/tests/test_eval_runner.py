from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.core.errors import EvalError
from dharmiq.db.session import get_session_factory
from dharmiq.eval.runner import run_eval_dataset


@pytest.fixture(autouse=True)
async def _empty_corpus() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM document_chunks"))
        await db.execute(text("DELETE FROM document_sections"))
        await db.execute(text("DELETE FROM source_documents"))
        await db.commit()
    yield


async def test_eval_preflight_fails_without_corpus(db: AsyncSession) -> None:
    with pytest.raises(EvalError, match="no indexed corpus"):
        await run_eval_dataset(db, "v1_fundamental_rights")
