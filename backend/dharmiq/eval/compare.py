from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FLOAT_METRICS: list[str] = [
    "faithfulness",
    "answer_correctness",
    "llm_citation_correctness",
    "recall_at_5",
]
BOOLEAN_METRICS: list[str] = [
    "blockquote_met",
    "refusal_correct",
    "revised_law_met",
]
REGRESSION_DELTA_FLOAT = 0.02
REGRESSION_DELTA_BOOLEAN = 0.05
_FLOAT_EPS = 1e-9

QUALITY_TARGETS: dict[str, float] = {
    "faithfulness": 0.85,
    "answer_correctness": 0.80,
    "llm_citation_correctness": 0.95,
    "recall_at_5": 0.77,
    "blockquote_met": 0.80,
    "refusal_correct": 0.90,
}


def resolve_baseline_path(runs_dir: Path, name: str = "baseline") -> Path:
    if name == "baseline":
        return runs_dir / "baseline.json"
    return runs_dir / f"{name}.json"


def load_baseline_metrics(path: Path, *, suite: str = "mvp") -> dict[str, float]:
    """Load aggregate metrics for a suite from baseline.json."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        metrics = payload["suites"][suite]["aggregate_metrics"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Invalid baseline format in {path}: missing suites.{suite}.aggregate_metrics") from exc
    return {key: float(value) for key, value in metrics.items()}


def check_regressions(
    candidate: dict[str, float],
    baseline: dict[str, float],
) -> list[str]:
    """Return human-readable regression violations (TRD-54)."""
    violations: list[str] = []

    for key in FLOAT_METRICS:
        if key not in candidate or key not in baseline:
            continue
        delta = baseline[key] - candidate[key]
        if delta > REGRESSION_DELTA_FLOAT + _FLOAT_EPS:
            violations.append(
                f"{key} regressed by {delta:.3f} "
                f"(baseline={baseline[key]:.3f}, candidate={candidate[key]:.3f}, "
                f"max drop={REGRESSION_DELTA_FLOAT})"
            )

    for key in BOOLEAN_METRICS:
        if key not in candidate or key not in baseline:
            continue
        delta = baseline[key] - candidate[key]
        if delta > REGRESSION_DELTA_BOOLEAN + _FLOAT_EPS:
            violations.append(
                f"{key} regressed by {delta:.3f} "
                f"(baseline={baseline[key]:.3f}, candidate={candidate[key]:.3f}, "
                f"max drop={REGRESSION_DELTA_BOOLEAN})"
            )

    return violations


def check_quality_targets(candidate: dict[str, float]) -> list[str]:
    """Return human-readable target violations (TRD quality targets)."""
    violations: list[str] = []
    for key, target in QUALITY_TARGETS.items():
        if key not in candidate:
            continue
        if candidate[key] < target:
            violations.append(
                f"{key} below target ({candidate[key]:.3f} < {target:.2f})"
            )
    return violations


def format_delta_table(
    candidate: dict[str, float],
    baseline: dict[str, float],
) -> str:
    """Format a stdout delta table for candidate vs baseline metrics."""
    keys = sorted(set(candidate) | set(baseline))
    lines = ["Metric comparison (candidate vs baseline):"]
    lines.append(f"{'metric':<28} {'candidate':>10} {'baseline':>10} {'delta':>10}")
    for key in keys:
        cand = candidate.get(key)
        base = baseline.get(key)
        if cand is None and base is None:
            continue
        cand_str = f"{cand:.3f}" if isinstance(cand, (int, float)) else "-"
        base_str = f"{base:.3f}" if isinstance(base, (int, float)) else "-"
        if isinstance(cand, (int, float)) and isinstance(base, (int, float)):
            delta_str = f"{cand - base:+.3f}"
        else:
            delta_str = "-"
        lines.append(f"{key:<28} {cand_str:>10} {base_str:>10} {delta_str:>10}")
    return "\n".join(lines)


def compare_against_baseline(
    candidate: dict[str, float],
    baseline: dict[str, float],
) -> tuple[list[str], list[str]]:
    """Return (regressions, target_violations) for candidate metrics."""
    regressions = check_regressions(candidate, baseline)
    target_violations = check_quality_targets(candidate)
    return regressions, target_violations


def compare_exit_code(
    candidate: dict[str, float],
    baseline: dict[str, float],
) -> int:
    """Exit 1 if TRD-54 regression or quality target violated; else 0."""
    regressions, target_violations = compare_against_baseline(candidate, baseline)
    return 1 if regressions or target_violations else 0


def load_baseline_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
