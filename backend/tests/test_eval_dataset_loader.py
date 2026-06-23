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
def test_load_v1_refusal_adversarial_dataset() -> None:
    records = load_dataset_records("v1_refusal_adversarial")
    assert len(records) >= 20
    refusal_rows = [record for record in records if record.expect_refusal is True]
    control_rows = [record for record in records if record.expect_refusal is False]
    assert len(refusal_rows) >= 15
    assert len(control_rows) >= 5


@pytest.mark.timeout(30)
def test_load_v1_revised_law_dataset() -> None:
    records = load_dataset_records("v1_revised_law")
    assert len(records) >= 15
    assert records[0].must_not_cite_sections
    assert all(record.must_not_cite_sections for record in records)


@pytest.mark.timeout(30)
def test_load_v1_needle_statute_dataset() -> None:
    records = load_dataset_records("v1_needle_statute")
    assert len(records) >= 30
    assert records[0].external_id == "n1"
    assert all(record.expected_citations for record in records)
    v06_topics = {record.topic for record in records if record.topic in {"property", "tax", "cyber"}}
    assert v06_topics == {"property", "tax", "cyber"}


@pytest.mark.timeout(30)
def test_load_v1_property_dataset() -> None:
    records = load_dataset_records("v1_property")
    assert len(records) >= 15
    assert records[0].external_id == "p1"
    assert records[0].required_source_ids == ["IN-RERA-2016"]
    assert all(record.min_citation_count == 1 for record in records)
    assert all(record.expected_citations for record in records)
    topics = {record.topic for record in records}
    assert "rera_registration" in topics
    assert "registration" in topics
    assert "land_acquisition" in topics


@pytest.mark.timeout(30)
def test_load_v1_tax_dataset() -> None:
    records = load_dataset_records("v1_tax")
    assert len(records) >= 15
    assert records[0].external_id == "t1"
    assert records[0].required_source_ids == ["IN-ITA-1961"]
    topics = {record.topic for record in records}
    assert "tds_salary" in topics
    assert "gst_registration" in topics
    assert "input_tax_credit" in topics


@pytest.mark.timeout(30)
def test_load_v1_cyber_dataset() -> None:
    records = load_dataset_records("v1_cyber")
    assert len(records) >= 15
    assert records[0].external_id == "y1"
    assert records[0].required_source_ids == ["IN-DPDP-2023"]
    topics = {record.topic for record in records}
    assert "dpdp_rights" in topics
    assert "cybercrime" in topics
    assert "intermediary" in topics


@pytest.mark.timeout(30)
def test_load_dataset_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_dataset_records("does_not_exist")
