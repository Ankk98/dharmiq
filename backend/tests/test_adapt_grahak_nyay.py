from __future__ import annotations

from pathlib import Path

import pytest

from dharmiq.eval.tools.adapt_grahak_nyay import (
    adapt_grahak_pairs,
    load_grahak_qa_pairs,
    map_citation,
    should_drop_row,
)

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "grahak_sample.csv"


@pytest.mark.timeout(30)
def test_should_drop_helpline_row() -> None:
    assert should_drop_row(
        "How do I contact the helpline?",
        "Call consumerhelpline.gov.in at 1800114000 for assistance.",
    )


@pytest.mark.timeout(30)
def test_should_keep_substantive_row() -> None:
    assert not should_drop_row(
        "What is product liability?",
        "Product liability means responsibility for harm from defective products under the Act.",
    )


@pytest.mark.timeout(30)
def test_map_citation_ecommerce() -> None:
    section, sources = map_citation("Is online shopping covered?", "E-commerce entities are regulated.")
    assert section == "Section 2(16)"
    assert sources == ["IN-CPA-2019"]


@pytest.mark.timeout(30)
def test_adapt_grahak_pairs_from_fixture() -> None:
    pairs = load_grahak_qa_pairs(FIXTURE_CSV)
    records = adapt_grahak_pairs(pairs, limit=10)
    assert len(records) == 3
    assert records[0]["topic"] == "consumer"
    assert records[0]["min_citation_count"] == 1
    assert records[0]["expected_citations"]
    questions = {str(record["question"]).lower() for record in records}
    assert not any("helpline" in question for question in questions)
