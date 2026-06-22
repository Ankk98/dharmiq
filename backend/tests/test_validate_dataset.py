from __future__ import annotations

import pytest

from dharmiq.eval.dataset_loader import EvalDatasetRecord, load_dataset_records
from dharmiq.eval.tools.validate_dataset import validate_dataset, validate_dataset_records


@pytest.mark.timeout(30)
def test_validate_v1_fundamental_rights_passes() -> None:
    issues = validate_dataset("v1_fundamental_rights")
    assert not any(issue.level == "error" for issue in issues)


@pytest.mark.timeout(30)
def test_validate_v1_consumer_passes() -> None:
    issues = validate_dataset("v1_consumer")
    assert not any(issue.level == "error" for issue in issues)


@pytest.mark.timeout(30)
def test_validate_v1_employment_passes() -> None:
    issues = validate_dataset("v1_employment")
    assert not any(issue.level == "error" for issue in issues)


@pytest.mark.timeout(30)
def test_validate_v1_refusal_adversarial_passes() -> None:
    issues = validate_dataset("v1_refusal_adversarial")
    assert not any(issue.level == "error" for issue in issues)


@pytest.mark.timeout(30)
def test_validate_v1_revised_law_passes() -> None:
    issues = validate_dataset("v1_revised_law")
    assert not any(issue.level == "error" for issue in issues)


@pytest.mark.timeout(30)
def test_validate_v1_needle_statute_passes() -> None:
    issues = validate_dataset("v1_needle_statute")
    assert not any(issue.level == "error" for issue in issues)


@pytest.mark.timeout(30)
def test_load_v1_dataset_new_fields() -> None:
    records = load_dataset_records("v1_fundamental_rights")
    assert len(records) >= 30
    assert records[0].required_source_ids == ["IN-CONSTITUTION-1949"]
    assert records[0].source_type == "statute"
    assert records[0].locale == "en"
    assert all(record.topic != "consumer" for record in records)


@pytest.mark.timeout(30)
def test_validate_rejects_consumer_topic() -> None:
    records = [
        EvalDatasetRecord(
            external_id="q1",
            question="test?",
            expected_answer="answer",
            expected_citations=[{"section": "Article 1"}],
            topic="consumer",
            facts="facts",
            min_citation_count=1,
        )
    ]
    issues = validate_dataset_records("v1_fundamental_rights", records)
    assert any("consumer" in issue.message for issue in issues)


@pytest.mark.timeout(30)
def test_validate_rejects_missing_citations() -> None:
    records = [
        EvalDatasetRecord(
            external_id="q1",
            question="What is Article 21?",
            expected_answer="Life and liberty.",
            expected_citations=[],
            topic="constitutional_rights",
            facts="facts",
            min_citation_count=1,
        )
    ]
    issues = validate_dataset_records("v1_fundamental_rights", records)
    assert any("expected_citations" in issue.message for issue in issues)
