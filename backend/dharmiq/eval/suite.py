from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings
from dharmiq.core.errors import EvalError
from dharmiq.core.logging import get_logger
from dharmiq.eval.runner import EvalRunSummary, run_eval_dataset
from dharmiq.llm.openrouter_client import OpenRouterClient

logger = get_logger(__name__)

MVP_DATASETS: list[str] = [
    "v1_fundamental_rights",
    "v1_consumer",
    "v1_employment",
    "v1_refusal_adversarial",
    "v1_revised_law",
    "v1_needle_statute",
]

ROLLUP_METRIC_KEYS: list[str] = [
    "faithfulness",
    "answer_correctness",
    "llm_answer_correctness",
    "llm_citation_correctness",
    "citation_count_met",
    "blockquote_met",
    "refusal_correct",
    "recall_at_5",
    "revised_law_met",
]


@dataclass(frozen=True)
class DatasetRunOutcome:
    dataset_name: str
    summary: EvalRunSummary | None
    error: str | None = None


@dataclass(frozen=True)
class MvpSuiteSummary:
    outcomes: list[DatasetRunOutcome]
    aggregate_metrics: dict[str, float]
    model: str
    total_questions: int


def rollup_aggregate_metrics(summaries: list[EvalRunSummary]) -> dict[str, float]:
    """Weighted aggregate across dataset runs (weight = question_count per dataset)."""
    if not summaries:
        return {}

    aggregate: dict[str, float] = {}
    for key in ROLLUP_METRIC_KEYS:
        weighted_sum = 0.0
        weight_total = 0.0
        for summary in summaries:
            value = summary.aggregate_metrics.get(key)
            if value is None:
                continue
            weight = float(summary.question_count)
            weighted_sum += float(value) * weight
            weight_total += weight
        if weight_total > 0:
            aggregate[key] = weighted_sum / weight_total

    aggregate["question_count"] = float(sum(summary.question_count for summary in summaries))
    return aggregate


async def run_mvp_suite(
    db: AsyncSession,
    *,
    settings: Settings,
    client: OpenRouterClient | None = None,
    limit: int | None = None,
) -> MvpSuiteSummary:
    """Run all MVP gating datasets sequentially; continue after per-dataset failures."""
    outcomes: list[DatasetRunOutcome] = []
    successful: list[EvalRunSummary] = []

    for dataset_name in MVP_DATASETS:
        try:
            summary = await run_eval_dataset(
                db,
                dataset_name,
                settings=settings,
                client=client,
                limit=limit,
            )
            outcomes.append(DatasetRunOutcome(dataset_name=dataset_name, summary=summary))
            successful.append(summary)
            logger.info(
                "mvp_suite_dataset_complete",
                dataset=dataset_name,
                question_count=summary.question_count,
            )
        except EvalError as exc:
            message = exc.message
            outcomes.append(
                DatasetRunOutcome(dataset_name=dataset_name, summary=None, error=message)
            )
            logger.warning("mvp_suite_dataset_failed", dataset=dataset_name, error=message)
        except Exception as exc:  # noqa: BLE001 — continue suite on unexpected errors
            message = str(exc)
            outcomes.append(
                DatasetRunOutcome(dataset_name=dataset_name, summary=None, error=message)
            )
            logger.exception("mvp_suite_dataset_error", dataset=dataset_name)

    model = successful[0].model if successful else settings.openrouter.default_model
    return MvpSuiteSummary(
        outcomes=outcomes,
        aggregate_metrics=rollup_aggregate_metrics(successful),
        model=model,
        total_questions=sum(summary.question_count for summary in successful),
    )
