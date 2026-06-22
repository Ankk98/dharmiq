from __future__ import annotations

import pytest

from dharmiq.eval.dataset_loader import load_dataset_records


@pytest.mark.timeout(30)
def test_load_v1_dataset() -> None:
    records = load_dataset_records("v1_fundamental_rights")
    assert len(records) == 30
    assert records[0].external_id == "q1"
    assert "police" in records[0].question.lower()
    assert records[0].expected_citations
    assert records[0].topic == "police_arrest"
    assert records[0].min_citation_count == 1
    assert records[0].expect_blockquote is True
    assert records[0].required_source_ids == ["IN-CONSTITUTION-1949"]
    assert records[0].source_type == "statute"
    assert records[0].locale == "en"
    assert all(record.topic != "consumer" for record in records)


@pytest.mark.timeout(30)
def test_load_v1_consumer_dataset() -> None:
    records = load_dataset_records("v1_consumer")
    assert len(records) >= 30
    assert records[0].external_id == "c1"
    assert records[0].topic == "consumer"
    assert records[0].min_citation_count == 1
    assert records[0].expected_citations
    assert records[0].required_source_ids == ["IN-CPA-2019"]
    assert all(record.topic == "consumer" for record in records)


@pytest.mark.timeout(30)
def test_load_v1_employment_dataset() -> None:
    records = load_dataset_records("v1_employment")
    assert len(records) >= 30
    assert records[0].external_id == "e1"
    assert records[0].min_citation_count == 1
    assert records[0].expected_citations
    assert records[0].required_source_ids == ["IN-IDA-1947"]
    topics = {record.topic for record in records}
    assert "termination" in topics
    assert "wages" in topics
    assert "harassment" in topics


@pytest.mark.timeout(30)
def test_load_dataset_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_dataset_records("does_not_exist")
