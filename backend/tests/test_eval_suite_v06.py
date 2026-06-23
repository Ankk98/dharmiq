from __future__ import annotations

import json
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
from dharmiq.eval.baseline import (
    build_v06_baseline,
    merge_baseline_suite,
    write_baseline,
)
from dharmiq.eval.runner import EvalRunSummary
from dharmiq.eval.suite import (
    MVP_DATASETS,
    V06_DATASETS,
    V06_SUITE_ORDER,
    DatasetRunOutcome,
    MvpSuiteSummary,
    run_v06_suite,
    v06_suite_datasets,
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
def test_v06_datasets_order_and_count() -> None:
    assert len(V06_DATASETS) == 3
    assert V06_DATASETS == ["v1_property", "v1_tax", "v1_cyber"]
    assert len(V06_SUITE_ORDER) == 9
    assert V06_SUITE_ORDER[:6] == MVP_DATASETS
    assert V06_SUITE_ORDER[6:] == V06_DATASETS
    assert v06_suite_datasets() == V06_SUITE_ORDER


@pytest.mark.timeout(30)
def test_build_v06_baseline_includes_all_datasets() -> None:
    summary = MvpSuiteSummary(
        outcomes=[
            DatasetRunOutcome(
                dataset_name="v1_property",
                summary=EvalRunSummary(
                    run_id=uuid.uuid4(),
                    dataset_name="v1_property",
                    model="deepseek/deepseek-v4-flash",
                    question_count=15,
                    aggregate_metrics={"faithfulness": 0.88},
                    output_path=Path("property.json"),
                ),
            ),
            DatasetRunOutcome(
                dataset_name="v1_tax",
                summary=None,
                error="simulated failure",
            ),
        ],
        aggregate_metrics={"faithfulness": 0.88, "question_count": 15.0},
        model="deepseek/deepseek-v4-flash",
        total_questions=15,
    )
    metadata = {
        "git_sha": "abc",
        "allowlist_version": "0.6",
        "allowlist_sha256": "hash",
        "eval_path": "run_eval_rag",
    }
    payload = build_v06_baseline(suite_summary=summary, metadata=metadata)
    assert payload["allowlist_version"] == "0.6"
    assert payload["suites"]["v06"]["aggregate_metrics"]["faithfulness"] == 0.88
    assert payload["suites"]["v06"]["datasets"]["v1_tax"]["failed"] is True
    assert "mvp" not in payload["suites"]


@pytest.mark.timeout(30)
def test_merge_baseline_suite_preserves_mvp(tmp_path: Path) -> None:
    existing = {
        "created_at": "2026-06-22T12:00:00Z",
        "suites": {
            "mvp": {
                "aggregate_metrics": {"faithfulness": 0.86},
                "datasets": {"v1_fundamental_rights": {"aggregate_metrics": {"faithfulness": 0.9}}},
            }
        },
    }
    new_payload = {
        "created_at": "2026-06-23T12:00:00Z",
        "suites": {
            "v06": {
                "aggregate_metrics": {"faithfulness": 0.87},
                "datasets": {"v1_property": {"aggregate_metrics": {"faithfulness": 0.87}}},
            }
        },
    }
    merged = merge_baseline_suite(new_payload, existing=existing)
    assert merged["suites"]["mvp"]["aggregate_metrics"]["faithfulness"] == 0.86
    assert merged["suites"]["v06"]["aggregate_metrics"]["faithfulness"] == 0.87


@pytest.mark.timeout(30)
def test_merge_baseline_suite_without_existing() -> None:
    payload = {"suites": {"v06": {"aggregate_metrics": {"faithfulness": 0.87}}}}
    assert merge_baseline_suite(payload, existing=None) == payload


@pytest.mark.timeout(30)
def test_write_v06_baseline_merges_existing_mvp(tmp_path: Path) -> None:
    existing_path = tmp_path / "baseline.json"
    existing_path.write_text(
        json.dumps(
            {
                "suites": {
                    "mvp": {
                        "aggregate_metrics": {"faithfulness": 0.86},
                        "datasets": {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    summary = MvpSuiteSummary(
        outcomes=[],
        aggregate_metrics={"faithfulness": 0.87, "question_count": 0.0},
        model="model",
        total_questions=0,
    )
    metadata = {
        "git_sha": "abc",
        "allowlist_version": "0.6",
        "allowlist_sha256": "hash",
        "eval_path": "run_eval_rag",
    }
    payload = build_v06_baseline(suite_summary=summary, metadata=metadata)
    existing = json.loads(existing_path.read_text(encoding="utf-8"))
    merged = merge_baseline_suite(payload, existing=existing)
    path = write_baseline(merged, runs_dir=tmp_path, yes=True)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["suites"]["mvp"]["aggregate_metrics"]["faithfulness"] == 0.86
    assert written["suites"]["v06"]["aggregate_metrics"]["faithfulness"] == 0.87


@pytest.mark.timeout(30)
async def test_run_v06_suite_continues_on_failure(
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
        if dataset_name == "v1_property":
            raise EvalError("simulated property failure")
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

    suite_summary = await run_v06_suite(db, settings=settings, limit=1)

    assert call_count["n"] == len(V06_SUITE_ORDER)
    assert len(suite_summary.outcomes) == len(V06_SUITE_ORDER)
    failed = [o for o in suite_summary.outcomes if o.error]
    assert len(failed) == 1
    assert failed[0].dataset_name == "v1_property"
    assert suite_summary.total_questions == len(V06_SUITE_ORDER) - 1
