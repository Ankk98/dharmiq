"""BhashaBench-Legal weak indicator sampler (v0.5 P7).

Optional quarterly domain-coverage audit — never a merge gate.
v0.5 binding: count questions per MVP domain and log sample IDs only;
no automated MCQ scoring through Dharmiq RAG.

See ``docs/plans/datasets.md`` §5.3 and ``docs/plans/v0.5/manual-test-runbook.md`` §6.

External benchmark: https://huggingface.co/datasets/bharatgenai/BhashaBench-Legal
(gated — request access, then ``export HF_TOKEN=...`` before a live sample run).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dharmiq.config.settings import REPO_ROOT

HF_DATASET = "bharatgenai/BhashaBench-Legal"

# Dharmiq MVP domain keys → BhashaBench subject labels (dataset card statistics).
DOMAIN_TO_BBL_SUBJECT: dict[str, str] = {
    "constitutional": "Constitutional & Administrative Law",
    "consumer": "Consumer & Competition Law",
    "employment": "Employment & Labour Law",
}

# Reference totals from BhashaBench-Legal dataset card (``datasets.md`` §5.3).
REFERENCE_DOMAIN_COUNTS: dict[str, int] = {
    "constitutional": 3609,
    "consumer": 75,
    "employment": 175,
}

SUBJECT_FIELD_CANDIDATES: tuple[str, ...] = (
    "subject_domain",
    "Subject Domain",
    "subject",
    "domain",
    "legal_domain",
)

ID_FIELD_CANDIDATES: tuple[str, ...] = (
    "id",
    "question_id",
    "qid",
    "uuid",
)

QUESTION_FIELD_CANDIDATES: tuple[str, ...] = (
    "question",
    "Question",
    "prompt",
    "text",
)


@dataclass(frozen=True)
class DomainSample:
    domain: str
    bbl_subject: str
    total_count: int
    sample_ids: list[str]
    sample_previews: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SamplePlan:
    mode: str
    language: str
    samples_per_domain: int
    domains: list[DomainSample]
    notes: list[str] = field(default_factory=list)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _first_present(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return str(row[key]).strip()
    return None


def _row_subject(row: dict[str, Any]) -> str | None:
    return _first_present(row, SUBJECT_FIELD_CANDIDATES)


def _row_id(row: dict[str, Any], *, fallback_index: int) -> str:
    explicit = _first_present(row, ID_FIELD_CANDIDATES)
    if explicit:
        return explicit
    question = _first_present(row, QUESTION_FIELD_CANDIDATES)
    if question:
        digest = hashlib.sha256(question.encode("utf-8")).hexdigest()[:12]
        return f"q-{digest}"
    return f"row-{fallback_index}"


def _row_preview(row: dict[str, Any], *, max_len: int = 120) -> str:
    question = _first_present(row, QUESTION_FIELD_CANDIDATES)
    if not question:
        return ""
    if len(question) <= max_len:
        return question
    return question[: max_len - 3] + "..."


def _domain_for_subject(subject: str) -> str | None:
    normalized = subject.casefold()
    for domain, bbl_subject in DOMAIN_TO_BBL_SUBJECT.items():
        if bbl_subject.casefold() == normalized:
            return domain
    return None


def build_dry_run_plan(
    *,
    language: str = "English",
    samples_per_domain: int = 5,
) -> SamplePlan:
    """Build a sample plan from published BhashaBench domain statistics."""
    domains: list[DomainSample] = []
    for domain, bbl_subject in DOMAIN_TO_BBL_SUBJECT.items():
        total = REFERENCE_DOMAIN_COUNTS[domain]
        sample_ids = [
            f"{domain}-dry-run-{index + 1}"
            for index in range(min(samples_per_domain, total))
        ]
        domains.append(
            DomainSample(
                domain=domain,
                bbl_subject=bbl_subject,
                total_count=total,
                sample_ids=sample_ids,
                sample_previews=[],
            )
        )
    return SamplePlan(
        mode="dry_run",
        language=language,
        samples_per_domain=samples_per_domain,
        domains=domains,
        notes=[
            "Dry-run uses published BhashaBench domain totals; sample IDs are placeholders.",
            "For live IDs, run without --dry-run after HuggingFace access is approved.",
            "No MCQ scoring is performed — domain coverage sanity check only.",
        ],
    )


def _hf_token() -> str | None:
    return os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")


def load_hf_plan(
    *,
    language: str = "English",
    samples_per_domain: int = 5,
    seed: int = 42,
) -> SamplePlan:
    """Stream BhashaBench-Legal and reservoir-sample IDs per MVP domain."""
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError(
            "The 'datasets' package is required for live BhashaBench sampling."
        ) from exc

    token = _hf_token()
    try:
        stream = load_dataset(
            HF_DATASET,
            data_dir=language,
            split="test",
            streaming=True,
            token=token if token else None,
        )
    except Exception as exc:
        raise RuntimeError(
            "Could not load BhashaBench-Legal from Hugging Face. "
            "Request access at https://huggingface.co/datasets/bharatgenai/BhashaBench-Legal "
            "and set HF_TOKEN (or HUGGING_FACE_HUB_TOKEN). "
            "Use --dry-run for an offline sample plan."
        ) from exc

    rng = random.Random(seed)
    totals: dict[str, int] = {domain: 0 for domain in DOMAIN_TO_BBL_SUBJECT}
    reservoirs: dict[str, list[tuple[str, str]]] = {
        domain: [] for domain in DOMAIN_TO_BBL_SUBJECT
    }

    for index, row in enumerate(stream):
        row_dict = dict(row)
        subject = _row_subject(row_dict)
        if not subject:
            continue
        domain = _domain_for_subject(subject)
        if domain is None:
            continue

        totals[domain] += 1
        row_id = _row_id(row_dict, fallback_index=index)
        preview = _row_preview(row_dict)
        bucket = reservoirs[domain]
        item = (row_id, preview)
        if len(bucket) < samples_per_domain:
            bucket.append(item)
        else:
            replace_at = rng.randint(0, totals[domain] - 1)
            if replace_at < samples_per_domain:
                bucket[replace_at] = item

    domains: list[DomainSample] = []
    for domain, bbl_subject in DOMAIN_TO_BBL_SUBJECT.items():
        bucket = reservoirs[domain]
        domains.append(
            DomainSample(
                domain=domain,
                bbl_subject=bbl_subject,
                total_count=totals[domain],
                sample_ids=[item[0] for item in bucket],
                sample_previews=[item[1] for item in bucket if item[1]],
            )
        )

    notes = [
        f"Loaded from {HF_DATASET} ({language}, test split, streaming).",
        "No MCQ scoring is performed — domain coverage sanity check only.",
    ]
    if totals["constitutional"] == 0 and totals["consumer"] == 0 and totals["employment"] == 0:
        notes.append(
            "Warning: no rows matched MVP domains — verify subject field names in the dataset."
        )

    return SamplePlan(
        mode="hf",
        language=language,
        samples_per_domain=samples_per_domain,
        domains=domains,
        notes=notes,
    )


def format_plan_stdout(plan: SamplePlan) -> str:
    lines = [
        "BhashaBench-Legal weak indicator sample plan",
        f"mode={plan.mode} language={plan.language} samples_per_domain={plan.samples_per_domain}",
        "",
    ]
    for domain_sample in plan.domains:
        lines.append(
            f"- {domain_sample.domain}: total={domain_sample.total_count} "
            f"bbl_subject={domain_sample.bbl_subject!r}"
        )
        if domain_sample.sample_ids:
            lines.append(f"  sample_ids: {', '.join(domain_sample.sample_ids)}")
        for preview in domain_sample.sample_previews[:2]:
            lines.append(f"  preview: {preview}")
    if plan.notes:
        lines.append("")
        lines.append("Notes:")
        for note in plan.notes:
            lines.append(f"- {note}")
    return "\n".join(lines)


def render_log_section(plan: SamplePlan) -> str:
    timestamp = _utc_now_iso()
    lines = [
        f"## BhashaBench sample — {timestamp}",
        "",
        f"- **Mode:** `{plan.mode}`",
        f"- **Language:** {plan.language}",
        f"- **Samples per domain:** {plan.samples_per_domain}",
        f"- **Dataset:** [{HF_DATASET}](https://huggingface.co/datasets/bharatgenai/BhashaBench-Legal)",
        "",
        "| Dharmiq domain | BhashaBench subject | Total in sample | Sample IDs |",
        "|----------------|---------------------|-----------------|------------|",
    ]
    for domain_sample in plan.domains:
        ids = ", ".join(domain_sample.sample_ids) if domain_sample.sample_ids else "—"
        lines.append(
            f"| {domain_sample.domain} | {domain_sample.bbl_subject} | "
            f"{domain_sample.total_count} | {ids} |"
        )
    lines.append("")
    lines.append("**Operator notes**")
    lines.append("")
    for note in plan.notes:
        lines.append(f"- {note}")
    lines.extend(
        [
            "- Weak indicator only — does not gate merges or releases.",
            "- Compare low-domain scores with MVP corpus coverage in "
            "[`mvp-corpus-allowlist.yaml`](../../../docs/plans/v0.5/mvp-corpus-allowlist.yaml).",
            "- For full MCQ evaluation, run BhashaBench externally per the dataset README.",
            "",
        ]
    )
    return "\n".join(lines)


def ensure_log_template(path: Path) -> None:
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# BhashaBench-Legal weak indicator log",
                "",
                "Append-only quarterly domain coverage notes. **Not a merge gate.**",
                "",
                "Generate a section:",
                "",
                "```bash",
                "cd backend",
                "uv run python -m dharmiq.eval.tools.bhashabench_sample --dry-run",
                "uv run python -m dharmiq.eval.tools.bhashabench_sample "
                "--output ../data/eval/runs/bhashabench_log.md",
                "```",
                "",
                "See [`docs/plans/datasets.md`](../../../docs/plans/datasets.md) §5.3.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def append_log(path: Path, section: str) -> None:
    ensure_log_template(path)
    existing = path.read_text(encoding="utf-8")
    if existing and not existing.endswith("\n"):
        existing += "\n"
    path.write_text(existing + section, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sample BhashaBench-Legal questions for MVP domain coverage audit "
            "(weak indicator; no MCQ scoring in v0.5)"
        ),
        epilog=(
            "BhashaBench-Legal is gated on Hugging Face. For offline planning use "
            "--dry-run. For live IDs set HF_TOKEN after access is approved."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use published domain totals and placeholder sample IDs (no network)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "data" / "eval" / "runs" / "bhashabench_log.md",
        help="Append-only markdown log path",
    )
    parser.add_argument(
        "--language",
        choices=("English", "Hindi"),
        default="English",
        help="BhashaBench language folder (HF data_dir)",
    )
    parser.add_argument(
        "--samples-per-domain",
        type=int,
        default=5,
        help="Number of question IDs to sample per MVP domain",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for HF reservoir sampling",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Append rendered section to --output (default when --output is passed explicitly)",
    )
    args = parser.parse_args()

    if args.samples_per_domain < 1:
        print("Error: --samples-per-domain must be >= 1", file=sys.stderr)
        raise SystemExit(1)

    try:
        if args.dry_run:
            plan = build_dry_run_plan(
                language=args.language,
                samples_per_domain=args.samples_per_domain,
            )
        else:
            plan = load_hf_plan(
                language=args.language,
                samples_per_domain=args.samples_per_domain,
                seed=args.seed,
            )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(format_plan_stdout(plan))

    should_write = args.write or (not args.dry_run and args.output is not None)
    if should_write:
        output_path = args.output.expanduser().resolve()
        append_log(output_path, render_log_section(plan))
        print(f"\nAppended log section to {output_path}")


if __name__ == "__main__":
    main()
