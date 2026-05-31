from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.core.errors import EvalError
from dharmiq.eval.runner import run_eval_dataset


async def test_eval_preflight_fails_without_corpus(db: AsyncSession) -> None:
    with pytest.raises(EvalError, match="no indexed corpus"):
        await run_eval_dataset(db, "v1_fundamental_rights")
