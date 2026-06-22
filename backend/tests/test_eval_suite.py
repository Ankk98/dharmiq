from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import get_settings
from dharmiq.core.errors import EvalError
from dharmiq.db.models.documents import DocType, DocumentChunk, SourceDocument
from dharmiq.db.session import get_session_factory
from dharmiq.eval.baseline import build_mvp_baseline, write_baseline
from dharmiq.eval.runner import EvalRunSummary
from dharmiq.eval.suite import (
    MVP_DATASETS,
    DatasetRunOutcome,
    MvpSuiteSummary,
    rollup_aggregate_metrics,
    run_mvp_suite,
)


@pytest.fixture(autouse=True)
async def _clean_corpus() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM document_chunks"))
        await db.execute(text("DELETE FROM document_sections"))
        await db.execute(text("DELETE FROM source_documents"))
        await db.commit()
    yield


@pytest.mark.timeout(30)
def test_mvp_datasets_order_and_count() -> None:
    assert len(MVP_DATASETS) == 6
    assert MVP_DATASETS[0] == "v1_fundamental_rights"
    assert MVP_DATASETS[-1] == "v1_needle_statute"


@pytest.mark.timeout(30)
def test_rollup_aggregate_metrics_weighted() -> None:
    summaries = [
        EvalRunSummary(
            run_id=uuid.uuid4(),
            dataset_name="a",
            model="model",
            question_count=10,
            aggregate_metrics={"faithfulness": 0.8, "question_count": 10.0},
            output_path=Path("a.json"),
        ),
        EvalRunSummary(
            run_id=uuid.uuid4(),
            dataset_name="b",
            model="model",
            question_count=20,
            aggregate_metrics={"faithfulness": 0.9, "question_count": 20.0},
            output_path=Path("b.json"),
        ),
    ]
    rolled = rollup_aggregate_metrics(summaries)
    assert rolled["faithfulness"] == pytest.approx((0.8 * 10 + 0.9 * 20) / 30)
    assert rolled["question_count"] == 30.0


@pytest.mark.timeout(30)
def test_rollup_aggregate_metrics_empty() -> None:
    assert rollup_aggregate_metrics([]) == {}


@pytest.mark.timeout(30)
def test_build_mvp_baseline_includes_failed_datasets() -> None:
    summary = MvpSuiteSummary(
        outcomes=[
            DatasetRunOutcome(
                dataset_name="v1_fundamental_rights",
                summary=EvalRunSummary(
                    run_id=uuid.uuid4(),
                    dataset_name="v1_fundamental_rights",
                    model="deepseek/deepseek-v4-flash",
                    question_count=2,
                    aggregate_metrics={"faithfulness": 0.9},
                    output_path=Path("run.json"),
                ),
            ),
            DatasetRunOutcome(
                dataset_name="v1_consumer",
                summary=None,
                error="no indexed corpus",
            ),
        ],
        aggregate_metrics={"faithfulness": 0.9, "question_count": 2.0},
        model="deepseek/deepseek-v4-flash",
        total_questions=2,
    )
    metadata = {
        "git_sha": "abc",
        "allowlist_version": "1",
        "allowlist_sha256": "hash",
        "eval_path": "run_eval_rag",
    }
    payload = build_mvp_baseline(suite_summary=summary, metadata=metadata)
    assert payload["suites"]["mvp"]["aggregate_metrics"]["faithfulness"] == 0.9
    assert payload["suites"]["mvp"]["datasets"]["v1_consumer"]["failed"] is True


@pytest.mark.timeout(30)
def test_write_mvp_baseline(tmp_path: Path) -> None:
    summary = MvpSuiteSummary(
        outcomes=[],
        aggregate_metrics={"question_count": 0.0},
        model="model",
        total_questions=0,
    )
    metadata = {
        "git_sha": "abc",
        "allowlist_version": "1",
        "allowlist_sha256": "hash",
        "eval_path": "run_eval_rag",
    }
    payload = build_mvp_baseline(suite_summary=summary, metadata=metadata)
    path = write_baseline(payload, runs_dir=tmp_path, yes=True)
    assert path.name == "baseline.json"
    assert path.is_file()


@pytest.mark.timeout(30)
async def test_run_mvp_suite_continues_on_failure(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    document = SourceDocument(
        source_id="IN-CONSTITUTION-1949",
        title="The Constitution of India",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash="hash-constitution",
        file_path="/tmp/constitution.pdf",
    )
    db.add(document)
    await db.flush()
    db.add(
        DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            text="Article 21 protects life and personal liberty.",
        )
    )
    await db.commit()

    call_count = {"n": 0}

    async def _fake_run_eval_dataset(
        _db: AsyncSession,
        dataset_name: str,
        *,
        settings: Any = None,
        client: Any = None,
        write_summary: bool = True,
        limit: int | None = None,
    ) -> EvalRunSummary:
        call_count["n"] += 1
        if dataset_name == "v1_consumer":
            raise EvalError("simulated consumer failure")
        return EvalRunSummary(
            run_id=uuid.uuid4(),
            dataset_name=dataset_name,
            model="deepseek/deepseek-v4-flash",
            question_count=1,
            aggregate_metrics={
                "faithfulness": 0.9,
                "answer_correctness": 0.85,
                "question_count": 1.0,
            },
            output_path=tmp_path / f"{dataset_name}.json",
        )

    monkeypatch.setattr("dharmiq.eval.suite.run_eval_dataset", _fake_run_eval_dataset)

    settings = get_settings()
    settings = settings.model_copy(
        update={"eval": settings.eval.model_copy(update={"runs_dir": str(tmp_path)})}
    )

    suite_summary = await run_mvp_suite(db, settings=settings, limit=1)

    assert call_count["n"] == len(MVP_DATASETS)
    assert len(suite_summary.outcomes) == len(MVP_DATASETS)
    failed = [o for o in suite_summary.outcomes if o.error]
    assert len(failed) == 1
    assert failed[0].dataset_name == "v1_consumer"
    assert suite_summary.total_questions == len(MVP_DATASETS) - 1
    assert suite_summary.aggregate_metrics["faithfulness"] == pytest.approx(0.9)
