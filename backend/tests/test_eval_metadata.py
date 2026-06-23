from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import get_settings
from dharmiq.db.models.documents import DocType, DocumentChunk, SourceDocument
from dharmiq.db.session import get_session_factory
from dharmiq.eval.baseline import build_single_dataset_baseline, write_baseline
from dharmiq.eval.metadata import (
    collect_run_metadata,
    default_v06_allowlist_path,
    hash_allowlist_file,
    read_allowlist_version,
    resolve_git_sha,
)
from dharmiq.eval.runner import _QuestionEvalResult, run_eval_dataset

FIXTURE_ALLOWLIST = Path(__file__).resolve().parent / "fixtures" / "mvp-allowlist-fixture.yaml"


@pytest.fixture(autouse=True)
async def _clean_corpus() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM document_chunks"))
        await db.execute(text("DELETE FROM document_sections"))
        await db.execute(text("DELETE FROM source_documents"))
        await db.commit()
    yield


V06_FIXTURE_ALLOWLIST = Path(__file__).resolve().parent / "fixtures" / "v06-allowlist-fixture.yaml"


@pytest.mark.timeout(30)
def test_default_v06_allowlist_path_points_to_central_yaml() -> None:
    settings = get_settings()
    path = default_v06_allowlist_path(settings.repo_root)
    assert path.name == "central-corpus-allowlist.yaml"
    assert path.parent.name == "v0.6"


@pytest.mark.timeout(30)
async def test_collect_run_metadata_uses_v06_allowlist(db: AsyncSession) -> None:
    settings = get_settings()
    metadata = await collect_run_metadata(
        db,
        settings=settings,
        allowlist_path=V06_FIXTURE_ALLOWLIST,
    )
    assert metadata["allowlist_version"] == "test"
    assert metadata["allowlist_sha256"] == hash_allowlist_file(V06_FIXTURE_ALLOWLIST)


@pytest.mark.timeout(30)
def test_resolve_git_sha_returns_string() -> None:
    settings = get_settings()
    sha = resolve_git_sha(settings.repo_root)
    assert isinstance(sha, str)
    assert len(sha) > 0


@pytest.mark.timeout(30)
def test_allowlist_version_and_hash_from_fixture() -> None:
    assert read_allowlist_version(FIXTURE_ALLOWLIST) == "test"
    digest = hash_allowlist_file(FIXTURE_ALLOWLIST)
    assert len(digest) == 64
    assert digest != "unknown"


@pytest.mark.timeout(30)
async def test_collect_run_metadata_keys(db: AsyncSession) -> None:
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

    settings = get_settings()
    metadata = await collect_run_metadata(
        db,
        settings=settings,
        allowlist_path=FIXTURE_ALLOWLIST,
    )

    assert metadata["git_sha"]
    assert metadata["allowlist_version"] == "test"
    assert metadata["allowlist_sha256"] == hash_allowlist_file(FIXTURE_ALLOWLIST)
    assert metadata["corpus_document_count"] == 1
    assert metadata["corpus_chunk_count"] == 1
    assert metadata["dharmiq_version"] == "0.5.0"
    assert metadata["eval_path"] == "run_eval_rag"


@pytest.mark.timeout(30)
async def test_run_eval_summary_includes_metadata(
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

    async def _fake_evaluate(
        _db: AsyncSession,
        record: Any,
        *,
        client: Any,
        settings: Any,
    ) -> _QuestionEvalResult:
        return _QuestionEvalResult(
            answer=f"Answer for {record.external_id}",
            contexts=["context"],
            metrics={
                "faithfulness": 0.9,
                "answer_correctness": 0.85,
                "llm_answer_correctness": 0.85,
                "llm_citation_correctness": 0.95,
                "citation_count_met": 1.0,
                "blockquote_met": 1.0,
                "refusal_correct": 1.0,
            },
            tokens_used=10,
        )

    monkeypatch.setattr("dharmiq.eval.runner._evaluate_question", _fake_evaluate)

    settings = get_settings()
    settings = settings.model_copy(
        update={"eval": settings.eval.model_copy(update={"runs_dir": str(tmp_path)})}
    )

    summary = await run_eval_dataset(
        db,
        "v1_fundamental_rights",
        settings=settings,
        limit=1,
    )
    payload = json.loads(summary.output_path.read_text(encoding="utf-8"))

    assert "metadata" in payload
    assert payload["metadata"]["eval_path"] == "run_eval_rag"
    assert payload["metadata"]["corpus_document_count"] == 1
    assert summary.question_count == 1


@pytest.mark.timeout(30)
def test_write_baseline_stub(tmp_path: Path) -> None:
    metadata = {
        "git_sha": "abc123",
        "allowlist_version": "1",
        "allowlist_sha256": "deadbeef",
        "eval_path": "run_eval_rag",
        "corpus_document_count": 26,
        "corpus_chunk_count": 1000,
        "dharmiq_version": "0.4.0",
    }
    metrics = {"faithfulness": 0.86, "question_count": 8.0}
    payload = build_single_dataset_baseline(
        dataset_name="v1_fundamental_rights",
        aggregate_metrics=metrics,
        metadata=metadata,
        model="deepseek/deepseek-v4-flash",
    )

    baseline_path = write_baseline(payload, runs_dir=tmp_path, yes=True)
    written = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert written["git_sha"] == "abc123"
    assert written["suites"]["mvp"]["datasets"]["v1_fundamental_rights"]["aggregate_metrics"] == metrics


@pytest.mark.timeout(30)
def test_write_baseline_refuses_overwrite_without_yes(tmp_path: Path) -> None:
    runs_dir = tmp_path
    (runs_dir / "baseline.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="Baseline already exists"):
        write_baseline({"created_at": "now"}, runs_dir=runs_dir, yes=False)
