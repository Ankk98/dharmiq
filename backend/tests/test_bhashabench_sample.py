from __future__ import annotations

from pathlib import Path

import pytest

import sys

from dharmiq.eval.tools.bhashabench_sample import (
    DOMAIN_TO_BBL_SUBJECT,
    REFERENCE_DOMAIN_COUNTS,
    append_log,
    build_dry_run_plan,
    format_plan_stdout,
    load_hf_plan,
    render_log_section,
)


@pytest.mark.timeout(30)
def test_build_dry_run_plan_covers_mvp_domains() -> None:
    plan = build_dry_run_plan(samples_per_domain=3)
    assert plan.mode == "dry_run"
    assert len(plan.domains) == len(DOMAIN_TO_BBL_SUBJECT)
    for domain_sample in plan.domains:
        assert domain_sample.total_count == REFERENCE_DOMAIN_COUNTS[domain_sample.domain]
        assert len(domain_sample.sample_ids) == 3
        assert domain_sample.sample_ids[0].startswith(f"{domain_sample.domain}-dry-run-")


@pytest.mark.timeout(30)
def test_format_plan_stdout_includes_domains() -> None:
    plan = build_dry_run_plan(samples_per_domain=2)
    text = format_plan_stdout(plan)
    assert "constitutional" in text
    assert "consumer" in text
    assert "employment" in text
    assert "dry-run-1" in text


@pytest.mark.timeout(30)
def test_render_log_section_markdown_table() -> None:
    plan = build_dry_run_plan(samples_per_domain=2)
    section = render_log_section(plan)
    assert "## BhashaBench sample —" in section
    assert "Constitutional & Administrative Law" in section
    assert "constitutional-dry-run-1" in section
    assert "Weak indicator only" in section


@pytest.mark.timeout(30)
def test_append_log_creates_template_and_appends(tmp_path: Path) -> None:
    log_path = tmp_path / "bhashabench_log.md"
    plan = build_dry_run_plan(samples_per_domain=1)
    section = render_log_section(plan)

    append_log(log_path, section)

    content = log_path.read_text(encoding="utf-8")
    assert "# BhashaBench-Legal weak indicator log" in content
    assert "constitutional-dry-run-1" in content

    append_log(log_path, "## second entry\n")
    updated = log_path.read_text(encoding="utf-8")
    assert updated.count("## BhashaBench sample —") == 1
    assert "## second entry" in updated


@pytest.mark.timeout(30)
def test_load_hf_plan_reservoir_sampling(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "id": "c1",
            "subject_domain": "Constitutional & Administrative Law",
            "question": "Article 14 question",
        },
        {
            "id": "c2",
            "subject_domain": "Constitutional & Administrative Law",
            "question": "Fundamental rights question",
        },
        {
            "id": "u1",
            "subject_domain": "Consumer & Competition Law",
            "question": "Consumer rights question",
        },
        {
            "id": "e1",
            "subject_domain": "Employment & Labour Law",
            "question": "Minimum wages question",
        },
        {
            "id": "x1",
            "subject_domain": "Criminal Law & Justice",
            "question": "Ignored domain",
        },
    ]

    def fake_load_dataset(*_args, **_kwargs):
        return iter(rows)

    import datasets

    monkeypatch.setattr(datasets, "load_dataset", fake_load_dataset)

    plan = load_hf_plan(language="English", samples_per_domain=2, seed=1)
    assert plan.mode == "hf"
    by_domain = {sample.domain: sample for sample in plan.domains}
    assert by_domain["constitutional"].total_count == 2
    assert len(by_domain["constitutional"].sample_ids) == 2
    assert by_domain["consumer"].total_count == 1
    assert by_domain["employment"].total_count == 1
    assert "Article 14" in " ".join(by_domain["constitutional"].sample_previews)


@pytest.mark.timeout(30)
def test_dry_run_cli_main(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dharmiq.eval.tools import bhashabench_sample

    monkeypatch.setattr(
        sys,
        "argv",
        ["bhashabench_sample", "--dry-run", "--samples-per-domain", "2"],
    )
    bhashabench_sample.main()

    captured = capsys.readouterr()
    assert "constitutional" in captured.out
    assert "dry-run-1" in captured.out
