from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dharmiq.config.settings import Settings, get_settings


@dataclass(frozen=True)
class EvalDatasetRecord:
    external_id: str
    question: str
    expected_answer: str
    expected_citations: list[dict[str, Any]]
    topic: str
    facts: str


def resolve_dataset_path(dataset_name: str, settings: Settings | None = None) -> Path:
    cfg = settings or get_settings()
    datasets_dir = cfg.eval.resolve_datasets_dir(cfg.repo_root)
    path = datasets_dir / f"{dataset_name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Eval dataset not found: {path}")
    return path


def load_dataset_records(
    dataset_name: str,
    settings: Settings | None = None,
) -> list[EvalDatasetRecord]:
    path = resolve_dataset_path(dataset_name, settings)
    records: list[EvalDatasetRecord] = []

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number} of {path}") from exc

        external_id = str(payload.get("id", "")).strip()
        question = str(payload.get("question", "")).strip()
        expected_answer = str(payload.get("expected_answer", "")).strip()
        if not external_id or not question or not expected_answer:
            raise ValueError(
                f"Line {line_number} in {path} missing required fields: id, question, expected_answer"
            )

        citations = payload.get("expected_citations") or []
        if not isinstance(citations, list):
            raise ValueError(f"Line {line_number} in {path}: expected_citations must be a list")

        records.append(
            EvalDatasetRecord(
                external_id=external_id,
                question=question,
                expected_answer=expected_answer,
                expected_citations=citations,
                topic=str(payload.get("topic") or "general"),
                facts=str(payload.get("facts") or question),
            )
        )

    if not records:
        raise ValueError(f"Dataset {path} contains no questions")
    return records
