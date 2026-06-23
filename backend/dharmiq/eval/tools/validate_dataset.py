from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from dharmiq.eval.dataset_loader import EvalDatasetRecord, load_dataset_records

GATING_MINIMUM_COUNTS: dict[str, int] = {
    "v1_fundamental_rights": 30,
    "v1_consumer": 30,
    "v1_employment": 30,
    "v1_refusal_adversarial": 20,
    "v1_revised_law": 15,
    "v1_needle_statute": 30,
    "v1_property": 15,
    "v1_tax": 15,
    "v1_cyber": 15,
}

FORBIDDEN_TOPICS: dict[str, set[str]] = {
    "v1_fundamental_rights": {"consumer"},
    "v1_property": {"case_law", "state_law"},
    "v1_tax": {"case_law", "state_law"},
    "v1_cyber": {"case_law", "state_law"},
}

REQUIRED_MUST_NOT_CITE: set[str] = {"v1_revised_law"}


@dataclass(frozen=True)
class ValidationIssue:
    level: str
    message: str


def _citation_sections(record: EvalDatasetRecord) -> list[str]:
    sections: list[str] = []
    for citation in record.expected_citations:
        if not isinstance(citation, dict):
            continue
        section = str(citation.get("section", "")).strip()
        if section:
            sections.append(section)
    return sections


def validate_dataset_records(
    dataset_name: str,
    records: list[EvalDatasetRecord],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()

    minimum_count = GATING_MINIMUM_COUNTS.get(dataset_name)
    if minimum_count is not None and len(records) < minimum_count:
        issues.append(
            ValidationIssue(
                "error",
                f"{dataset_name}: expected at least {minimum_count} rows, found {len(records)}",
            )
        )

    forbidden_topics = FORBIDDEN_TOPICS.get(dataset_name, set())

    for record in records:
        if record.external_id in seen_ids:
            issues.append(
                ValidationIssue("error", f"Duplicate id '{record.external_id}'")
            )
        seen_ids.add(record.external_id)

        if record.topic in forbidden_topics:
            issues.append(
                ValidationIssue(
                    "error",
                    f"{record.external_id}: topic '{record.topic}' is not allowed in {dataset_name}",
                )
            )

        refusal_expected = record.expect_refusal is True
        sections = _citation_sections(record)

        if refusal_expected:
            if record.min_citation_count not in (None, 0):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"{record.external_id}: refusal rows should set min_citation_count to 0",
                    )
                )
            continue

        if not sections:
            issues.append(
                ValidationIssue(
                    "error",
                    f"{record.external_id}: expected_citations must include at least one section",
                )
            )

        if dataset_name in REQUIRED_MUST_NOT_CITE and not record.must_not_cite_sections:
            issues.append(
                ValidationIssue(
                    "error",
                    f"{record.external_id}: must_not_cite_sections is required in {dataset_name}",
                )
            )

        if record.min_citation_count is None or record.min_citation_count < 1:
            issues.append(
                ValidationIssue(
                    "error",
                    f"{record.external_id}: statutory rows require min_citation_count >= 1",
                )
            )

    return issues


def validate_dataset(dataset_name: str) -> list[ValidationIssue]:
    records = load_dataset_records(dataset_name)
    return validate_dataset_records(dataset_name, records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a Dharmiq eval dataset JSONL file for schema and gating rules",
    )
    parser.add_argument(
        "--dataset",
        required=True,
        help="Dataset name (filename stem under data/eval/datasets/)",
    )
    args = parser.parse_args()

    try:
        issues = validate_dataset(args.dataset)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    errors = [issue for issue in issues if issue.level == "error"]
    for issue in issues:
        stream = sys.stderr if issue.level == "error" else sys.stdout
        print(f"{issue.level}: {issue.message}", file=stream)

    if errors:
        print(f"\nValidation failed for {args.dataset} ({len(errors)} error(s))", file=sys.stderr)
        raise SystemExit(1)

    print(f"Validation passed for {args.dataset} ({len(issues)} warning(s))")


if __name__ == "__main__":
    main()
