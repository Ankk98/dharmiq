from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def build_single_dataset_baseline(
    *,
    dataset_name: str,
    aggregate_metrics: dict[str, float],
    metadata: dict[str, str | int],
    model: str,
) -> dict[str, Any]:
    """Build a minimal baseline payload from one dataset run (P1 stub; P5 extends)."""
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
            "Pass --yes to overwrite (full compare harness ships in P5)."
        )
    runs_dir.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return baseline_path
