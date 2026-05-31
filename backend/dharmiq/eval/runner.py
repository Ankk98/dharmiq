from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import EvalError
from dharmiq.core.logging import get_logger
from dharmiq.db.models.documents import DocumentChunk, SourceDocument
from dharmiq.db.models.evals import EvalDataset, EvalQuestion, EvalResult, EvalRun
from dharmiq.eval.dataset_loader import EvalDatasetRecord, load_dataset_records
from dharmiq.eval.judge import run_llm_judge
from dharmiq.llm.agents.answerer import run_answerer
from dharmiq.llm.agents.query_rewriter import run_query_rewriter
from dharmiq.llm.openrouter_client import OpenRouterClient, get_openrouter_client
from dharmiq.llm.retrieval import RetrievedChunk, retrieve_multi_query
from dharmiq.observability.metrics import record_eval_run

logger = get_logger(__name__)

_EVAL_USER_ID = uuid.UUID(int=0)


@dataclass(frozen=True)
class EvalRunSummary:
    run_id: uuid.UUID
    dataset_name: str
    model: str
    question_count: int
    aggregate_metrics: dict[str, float]
    output_path: Path


@dataclass(frozen=True)
class _QuestionEvalResult:
    answer: str
    contexts: list[str]
    metrics: dict[str, Any]
    tokens_used: int


async def run_eval_rag(
    db: AsyncSession,
    record: EvalDatasetRecord,
    *,
    client: OpenRouterClient | None = None,
    settings: Settings | None = None,
) -> tuple[str, list[RetrievedChunk], int]:
    """Run query rewriter, retrieval, and answerer for one eval question."""
    cfg = settings or get_settings()
    llm = client or get_openrouter_client()
    tokens = 0

    rewriter = await run_query_rewriter(
        llm,
        user_question=record.question,
        topic=record.topic,
        facts=record.facts,
    )
    tokens += rewriter.tokens_used

    retrieved = await retrieve_multi_query(
        db,
        rewriter.queries,
        _EVAL_USER_ID,
        top_k=cfg.retrieval.multi_query_top_k,
        settings=cfg,
    )

    answer = await run_answerer(
        llm,
        user_question=record.question,
        facts=record.facts,
        retrieved_chunks=retrieved,
    )
    tokens += answer.tokens_used

    return answer.answer, retrieved, tokens


def _compute_ragas_metrics(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    reference: str,
    settings: Settings,
) -> dict[str, float]:
    if not contexts:
        return {"faithfulness": 0.0, "answer_correctness": 0.0}

    from datasets import Dataset
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_openai import ChatOpenAI
    from ragas import evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import answer_correctness, faithfulness

    dataset = Dataset.from_dict(
        {
            "question": [question],
            "answer": [answer],
            "contexts": [contexts],
            "ground_truth": [reference],
        }
    )
    llm = ChatOpenAI(
        model=settings.openrouter.default_model,
        openai_api_base=settings.openrouter.base_url.rstrip("/"),
        openai_api_key=settings.openrouter.api_key.get_secret_value(),
        temperature=0.0,
        max_retries=settings.openrouter.max_retries,
        timeout=settings.openrouter.timeout_seconds,
    )
    embeddings = HuggingFaceEmbeddings(model_name=settings.embeddings.local_model_name)
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_correctness],
        llm=LangchainLLMWrapper(llm),
        embeddings=LangchainEmbeddingsWrapper(embeddings),
    )
    df = result.to_pandas()
    row = df.iloc[0]
    return {
        "faithfulness": float(row.get("faithfulness") or 0.0),
        "answer_correctness": float(row.get("answer_correctness") or 0.0),
    }


async def _evaluate_question(
    db: AsyncSession,
    record: EvalDatasetRecord,
    *,
    client: OpenRouterClient,
    settings: Settings,
) -> _QuestionEvalResult:
    answer, retrieved, pipeline_tokens = await run_eval_rag(
        db,
        record,
        client=client,
        settings=settings,
    )
    contexts = [chunk.text for chunk in retrieved]

    ragas_scores = _compute_ragas_metrics(
        question=record.question,
        answer=answer,
        contexts=contexts,
        reference=record.expected_answer,
        settings=settings,
    )

    judge_scores, judge_tokens = await run_llm_judge(
        client,
        question=record.question,
        generated_answer=answer,
        reference_answer=record.expected_answer,
        expected_citations=record.expected_citations,
        model=settings.openrouter.default_model,
    )

    metrics: dict[str, Any] = {
        **ragas_scores,
        "llm_answer_correctness": judge_scores.answer_correctness,
        "llm_citation_correctness": judge_scores.citation_correctness,
        "llm_judge_reason": judge_scores.reason,
        "retrieved_context_count": len(contexts),
    }

    return _QuestionEvalResult(
        answer=answer,
        contexts=contexts,
        metrics=metrics,
        tokens_used=pipeline_tokens + judge_tokens,
    )


def _aggregate_metrics(results: list[_QuestionEvalResult]) -> dict[str, float]:
    if not results:
        return {}

    keys = [
        "faithfulness",
        "answer_correctness",
        "llm_answer_correctness",
        "llm_citation_correctness",
    ]
    aggregate: dict[str, float] = {}
    for key in keys:
        values = [float(result.metrics.get(key, 0.0)) for result in results]
        aggregate[key] = sum(values) / len(values)
    aggregate["question_count"] = float(len(results))
    return aggregate


async def _ensure_dataset_in_db(
    db: AsyncSession,
    dataset_name: str,
    records: list[EvalDatasetRecord],
) -> EvalDataset:
    result = await db.execute(select(EvalDataset).where(EvalDataset.name == dataset_name))
    dataset = result.scalar_one_or_none()
    if dataset is None:
        dataset = EvalDataset(
            name=dataset_name,
            description=f"Imported from {dataset_name}.jsonl",
        )
        db.add(dataset)
        await db.flush()

    existing = await db.execute(
        select(EvalQuestion.external_id).where(EvalQuestion.dataset_id == dataset.id)
    )
    known_ids = set(existing.scalars().all())

    for record in records:
        if record.external_id in known_ids:
            continue
        db.add(
            EvalQuestion(
                dataset_id=dataset.id,
                external_id=record.external_id,
                question=record.question,
                expected_answer=record.expected_answer,
                expected_citations=record.expected_citations or None,
            )
        )

    await db.flush()
    return dataset


async def _question_rows(db: AsyncSession, dataset_id: uuid.UUID) -> list[EvalQuestion]:
    result = await db.execute(
        select(EvalQuestion)
        .where(EvalQuestion.dataset_id == dataset_id)
        .order_by(EvalQuestion.created_at.asc())
    )
    return list(result.scalars().all())


async def _preflight_corpus(db: AsyncSession, settings: Settings) -> None:
    """Ensure indexed corpus exists before spending LLM tokens on eval."""
    doc_count = await db.scalar(select(func.count()).select_from(SourceDocument))
    chunk_count = await db.scalar(select(func.count()).select_from(DocumentChunk))

    if doc_count and chunk_count:
        return

    corpus_dir = settings.ingestion.resolve_corpus_dir(settings.repo_root)
    raise EvalError(
        "Cannot run eval: no indexed corpus in the database. "
        f"Found {doc_count or 0} source_documents and {chunk_count or 0} document_chunks.",
        details={
            "corpus_dir": str(corpus_dir),
            "hint": (
                "Place IndiaCode PDFs under the corpus directory, then run "
                "`uv run celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs` "
                "and wait for processing to finish before re-running eval."
            ),
        },
    )


async def run_eval_dataset(
    db: AsyncSession,
    dataset_name: str,
    *,
    settings: Settings | None = None,
    client: OpenRouterClient | None = None,
    write_summary: bool = True,
) -> EvalRunSummary:
    cfg = settings or get_settings()
    llm = client or get_openrouter_client()
    records = load_dataset_records(dataset_name, cfg)
    await _preflight_corpus(db, cfg)
    dataset = await _ensure_dataset_in_db(db, dataset_name, records)

    questions = await _question_rows(db, dataset.id)
    record_by_id = {record.external_id: record for record in records}

    eval_run = EvalRun(
        dataset_id=dataset.id,
        model=cfg.openrouter.default_model,
    )
    db.add(eval_run)
    await db.flush()

    evaluated_rows: list[tuple[EvalQuestion, _QuestionEvalResult]] = []
    for question_row in questions:
        record = record_by_id.get(question_row.external_id)
        if record is None:
            logger.warning(
                "eval_question_missing_record",
                external_id=question_row.external_id,
                dataset=dataset_name,
            )
            continue

        logger.info(
            "eval_question_started",
            dataset=dataset_name,
            question_id=question_row.external_id,
        )
        result = await _evaluate_question(db, record, client=llm, settings=cfg)
        evaluated_rows.append((question_row, result))

        db.add(
            EvalResult(
                run_id=eval_run.id,
                question_id=question_row.id,
                answer=result.answer,
                metrics=result.metrics,
            )
        )
        await db.flush()

    per_question = [item[1] for item in evaluated_rows]

    aggregate = _aggregate_metrics(per_question)
    eval_run.metrics = aggregate
    await db.commit()

    output_path = cfg.eval.resolve_runs_dir(cfg.repo_root)
    output_path.mkdir(parents=True, exist_ok=True)
    summary_file = output_path / f"{dataset_name}_{eval_run.id}.json"

    summary_payload = {
        "run_id": str(eval_run.id),
        "dataset": dataset_name,
        "model": cfg.openrouter.default_model,
        "run_at": datetime.now(UTC).isoformat(),
        "aggregate_metrics": aggregate,
        "questions": [
            {
                "external_id": question_row.external_id,
                "question": question_row.question,
                "answer": result.answer,
                "metrics": result.metrics,
            }
            for question_row, result in evaluated_rows
        ],
    }

    if write_summary:
        summary_file.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    record_eval_run(
        dataset=dataset_name,
        question_count=len(per_question),
        metrics=aggregate,
    )

    logger.info(
        "eval_run_complete",
        run_id=str(eval_run.id),
        dataset=dataset_name,
        aggregate=aggregate,
    )

    return EvalRunSummary(
        run_id=eval_run.id,
        dataset_name=dataset_name,
        model=cfg.openrouter.default_model,
        question_count=len(per_question),
        aggregate_metrics=aggregate,
        output_path=summary_file,
    )
