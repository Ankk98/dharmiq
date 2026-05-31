from __future__ import annotations

import pytest

from dharmiq.eval.dataset_loader import load_dataset_records


def test_load_v1_dataset() -> None:
    records = load_dataset_records("v1_fundamental_rights")
    assert len(records) == 8
    assert records[0].external_id == "q1"
    assert "police" in records[0].question.lower()
    assert records[0].expected_citations
    assert records[0].topic == "police_arrest"


def test_load_dataset_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_dataset_records("does_not_exist")
