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
    expect_refusal: bool | None = None
    min_citation_count: int | None = None
    expect_blockquote: bool | None = None
    required_source_ids: list[str] | None = None
    must_not_cite_sections: list[str] | None = None
    source_type: str = "statute"
    locale: str = "en"


def _parse_string_list(
    value: Any,
    *,
    field_name: str,
    line_number: int,
    path: Path,
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(
            f"Line {line_number} in {path}: {field_name} must be a list of strings"
        )
    return [item.strip() for item in value if item.strip()]


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

        expect_refusal = payload.get("expect_refusal")
        if expect_refusal is not None and not isinstance(expect_refusal, bool):
            raise ValueError(f"Line {line_number} in {path}: expect_refusal must be a boolean")

        min_citation_count = payload.get("min_citation_count")
        if min_citation_count is not None:
            if not isinstance(min_citation_count, int) or min_citation_count < 0:
                raise ValueError(
                    f"Line {line_number} in {path}: min_citation_count must be a non-negative integer"
                )

        expect_blockquote = payload.get("expect_blockquote")
        if expect_blockquote is not None and not isinstance(expect_blockquote, bool):
            raise ValueError(f"Line {line_number} in {path}: expect_blockquote must be a boolean")

        required_source_ids = _parse_string_list(
            payload.get("required_source_ids"),
            field_name="required_source_ids",
            line_number=line_number,
            path=path,
        )
        must_not_cite_sections = _parse_string_list(
            payload.get("must_not_cite_sections"),
            field_name="must_not_cite_sections",
            line_number=line_number,
            path=path,
        )

        source_type = str(payload.get("source_type") or "statute").strip()
        if not source_type:
            raise ValueError(f"Line {line_number} in {path}: source_type must be a non-empty string")

        locale = str(payload.get("locale") or "en").strip()
        if not locale:
            raise ValueError(f"Line {line_number} in {path}: locale must be a non-empty string")

        records.append(
            EvalDatasetRecord(
                external_id=external_id,
                question=question,
                expected_answer=expected_answer,
                expected_citations=citations,
                topic=str(payload.get("topic") or "general"),
                facts=str(payload.get("facts") or question),
                expect_refusal=expect_refusal,
                min_citation_count=min_citation_count,
                expect_blockquote=expect_blockquote,
                required_source_ids=required_source_ids or None,
                must_not_cite_sections=must_not_cite_sections or None,
                source_type=source_type,
                locale=locale,
            )
        )

    if not records:
        raise ValueError(f"Dataset {path} contains no questions")
    return records
