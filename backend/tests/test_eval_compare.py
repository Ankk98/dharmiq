from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharmiq.eval.compare import (
    REGRESSION_DELTA_BOOLEAN,
    REGRESSION_DELTA_FLOAT,
    check_quality_targets,
    check_regressions,
    compare_exit_code,
    format_delta_table,
    load_baseline_metrics,
    resolve_baseline_path,
)


@pytest.fixture
def baseline_payload() -> dict:
    return {
        "created_at": "2026-06-22T12:00:00Z",
        "git_sha": "abc123",
        "allowlist_version": "1",
        "allowlist_sha256": "deadbeef",
        "eval_path": "run_eval_rag",
        "model": "deepseek/deepseek-v4-flash",
        "suites": {
            "mvp": {
                "aggregate_metrics": {
                    "faithfulness": 0.86,
                    "answer_correctness": 0.81,
                    "llm_citation_correctness": 0.96,
                    "recall_at_5": 0.78,
                    "blockquote_met": 0.82,
                    "refusal_correct": 0.91,
                    "question_count": 155.0,
                },
                "datasets": {},
            }
        },
    }


@pytest.fixture
def baseline_file(tmp_path: Path, baseline_payload: dict) -> Path:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline_payload), encoding="utf-8")
    return path


@pytest.mark.timeout(30)
def test_resolve_baseline_path(tmp_path: Path) -> None:
    assert resolve_baseline_path(tmp_path, "baseline") == tmp_path / "baseline.json"
    assert resolve_baseline_path(tmp_path, "custom") == tmp_path / "custom.json"


@pytest.mark.timeout(30)
def test_load_baseline_metrics(baseline_file: Path) -> None:
    metrics = load_baseline_metrics(baseline_file)
    assert metrics["faithfulness"] == 0.86
    assert metrics["question_count"] == 155.0


@pytest.mark.timeout(30)
def test_load_baseline_metrics_invalid_format(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid baseline format"):
        load_baseline_metrics(path)


@pytest.mark.timeout(30)
def test_check_regressions_float_within_tolerance() -> None:
    baseline = {"faithfulness": 0.86, "answer_correctness": 0.81}
    candidate = {
        "faithfulness": baseline["faithfulness"] - REGRESSION_DELTA_FLOAT,
        "answer_correctness": baseline["answer_correctness"] - 0.01,
    }
    assert check_regressions(candidate, baseline) == []


@pytest.mark.timeout(30)
def test_check_regressions_float_violation() -> None:
    baseline = {"faithfulness": 0.86}
    candidate = {"faithfulness": baseline["faithfulness"] - REGRESSION_DELTA_FLOAT - 0.001}
    violations = check_regressions(candidate, baseline)
    assert len(violations) == 1
    assert "faithfulness" in violations[0]


@pytest.mark.timeout(30)
def test_check_regressions_boolean_violation() -> None:
    baseline = {"refusal_correct": 0.91}
    candidate = {"refusal_correct": baseline["refusal_correct"] - REGRESSION_DELTA_BOOLEAN - 0.01}
    violations = check_regressions(candidate, baseline)
    assert len(violations) == 1
    assert "refusal_correct" in violations[0]


@pytest.mark.timeout(30)
def test_check_quality_targets_pass() -> None:
    candidate = {
        "faithfulness": 0.86,
        "answer_correctness": 0.81,
        "llm_citation_correctness": 0.96,
        "recall_at_5": 0.78,
        "blockquote_met": 0.82,
        "refusal_correct": 0.91,
    }
    assert check_quality_targets(candidate) == []


@pytest.mark.timeout(30)
def test_check_quality_targets_violation() -> None:
    candidate = {"faithfulness": 0.84, "answer_correctness": 0.81}
    violations = check_quality_targets(candidate)
    assert len(violations) == 1
    assert "faithfulness" in violations[0]


@pytest.mark.timeout(30)
def test_compare_exit_code_pass(baseline_payload: dict) -> None:
    baseline = baseline_payload["suites"]["mvp"]["aggregate_metrics"]
    exit_code = compare_exit_code(baseline, baseline)
    assert exit_code == 0


@pytest.mark.timeout(30)
def test_compare_exit_code_regression_fail(baseline_payload: dict) -> None:
    baseline = baseline_payload["suites"]["mvp"]["aggregate_metrics"]
    candidate = dict(baseline)
    candidate["faithfulness"] = baseline["faithfulness"] - 0.05
    assert compare_exit_code(candidate, baseline) == 1


@pytest.mark.timeout(30)
def test_compare_exit_code_target_fail(baseline_payload: dict) -> None:
    baseline = baseline_payload["suites"]["mvp"]["aggregate_metrics"]
    candidate = dict(baseline)
    candidate["faithfulness"] = 0.84
    assert compare_exit_code(candidate, baseline) == 1


@pytest.mark.timeout(30)
def test_format_delta_table(baseline_payload: dict) -> None:
    baseline = baseline_payload["suites"]["mvp"]["aggregate_metrics"]
    candidate = dict(baseline)
    candidate["faithfulness"] = 0.87
    table = format_delta_table(candidate, baseline)
    assert "faithfulness" in table
    assert "+0.010" in table
