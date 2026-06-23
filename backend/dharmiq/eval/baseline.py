from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dharmiq.eval.suite import DatasetRunOutcome, MvpSuiteSummary

V06_SUITE_KEY = "v06"


def build_single_dataset_baseline(
    *,
    dataset_name: str,
    aggregate_metrics: dict[str, float],
    metadata: dict[str, str | int],
    model: str,
) -> dict[str, Any]:
    """Build a minimal baseline payload from one dataset run."""
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": metadata["git_sha"],
        "allowlist_version": metadata["allowlist_version"],
        "allowlist_sha256": metadata["allowlist_sha256"],
        "eval_path": metadata["eval_path"],
        "model": model,
        "suites": {
            "mvp": {
                "aggregate_metrics": dict(aggregate_metrics),
                "datasets": {
                    dataset_name: {"aggregate_metrics": dict(aggregate_metrics)},
                },
            }
        },
    }


def build_mvp_baseline(
    *,
    suite_summary: MvpSuiteSummary,
    metadata: dict[str, str | int],
) -> dict[str, Any]:
    """Build baseline.json payload from a full MVP suite run."""
    datasets_payload: dict[str, Any] = {}
    for outcome in suite_summary.outcomes:
        datasets_payload[outcome.dataset_name] = _dataset_baseline_entry(outcome)

    return {
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": metadata["git_sha"],
        "allowlist_version": metadata["allowlist_version"],
        "allowlist_sha256": metadata["allowlist_sha256"],
        "eval_path": metadata["eval_path"],
        "model": suite_summary.model,
        "suites": {
            "mvp": {
                "aggregate_metrics": dict(suite_summary.aggregate_metrics),
                "datasets": datasets_payload,
            }
        },
    }


def build_v06_baseline(
    *,
    suite_summary: MvpSuiteSummary,
    metadata: dict[str, str | int],
) -> dict[str, Any]:
    """Build baseline.json payload from a full v0.6 suite run."""
    datasets_payload: dict[str, Any] = {}
    for outcome in suite_summary.outcomes:
        datasets_payload[outcome.dataset_name] = _dataset_baseline_entry(outcome)

    return {
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": metadata["git_sha"],
        "allowlist_version": metadata["allowlist_version"],
        "allowlist_sha256": metadata["allowlist_sha256"],
        "eval_path": metadata["eval_path"],
        "model": suite_summary.model,
        "suites": {
            V06_SUITE_KEY: {
                "aggregate_metrics": dict(suite_summary.aggregate_metrics),
                "datasets": datasets_payload,
            }
        },
    }


def merge_baseline_suite(
    new_payload: dict[str, Any],
    *,
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge a new suite payload into an existing baseline without dropping other suites."""
    if existing is None:
        return new_payload

    merged = dict(new_payload)
    existing_suites = existing.get("suites") or {}
    new_suites = dict(new_payload.get("suites") or {})
    if "mvp" in existing_suites:
        new_suites["mvp"] = existing_suites["mvp"]
    merged["suites"] = new_suites
    return merged


def _dataset_baseline_entry(outcome: DatasetRunOutcome) -> dict[str, Any]:
    if outcome.summary is not None:
        return {"aggregate_metrics": dict(outcome.summary.aggregate_metrics)}
    return {"failed": True, "error": outcome.error or "unknown error"}


def write_baseline(
    payload: dict[str, Any],
    *,
    runs_dir: Path,
    yes: bool = False,
) -> Path:
    """Write baseline.json under the eval runs directory."""
    baseline_path = runs_dir / "baseline.json"
    if baseline_path.exists() and not yes:
        raise FileExistsError(
            f"Baseline already exists at {baseline_path}. "
            "Pass --yes to overwrite."
        )
    runs_dir.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return baseline_path
