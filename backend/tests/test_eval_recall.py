from __future__ import annotations

from dataclasses import dataclass

import pytest

from dharmiq.eval.recall import compute_recall_at_k
from dharmiq.llm.retrieval import RetrievedChunk


@dataclass(frozen=True)
class _RecallFixtureChunk:
    text: str
    section_label: str | None = None


@pytest.mark.timeout(30)
def test_recall_hit_on_chunk_text() -> None:
    chunks = [
        _RecallFixtureChunk(text="Article 22 protects liberty and consultation with counsel."),
        _RecallFixtureChunk(text="Unrelated consumer law text."),
    ]
    score = compute_recall_at_k(chunks, [{"section": "Article 22"}], k=5)
    assert score == 1.0


@pytest.mark.timeout(30)
def test_recall_hit_on_section_label_metadata() -> None:
    chunks = [
        _RecallFixtureChunk(text="General arrest procedure text.", section_label="Section 41"),
        _RecallFixtureChunk(text="Other material."),
    ]
    score = compute_recall_at_k(chunks, [{"section": "Section 41"}], k=5)
    assert score == 1.0


@pytest.mark.timeout(30)
def test_recall_miss_when_section_not_in_top_k() -> None:
    chunks = [
        _RecallFixtureChunk(text="Article 14 equality clause."),
        _RecallFixtureChunk(text="Article 19 speech clause."),
        _RecallFixtureChunk(text="RTI fee provisions."),
    ]
    score = compute_recall_at_k(chunks, [{"section": "Section 25F"}], k=2)
    assert score == 0.0


@pytest.mark.timeout(30)
def test_recall_respects_k_limit() -> None:
    chunks = [
        _RecallFixtureChunk(text="Irrelevant chunk one."),
        _RecallFixtureChunk(text="Irrelevant chunk two."),
        _RecallFixtureChunk(text="Section 8 RTI exemptions apply here."),
    ]
    score = compute_recall_at_k(chunks, [{"section": "Section 8"}], k=2)
    assert score == 0.0

    score_within_k = compute_recall_at_k(chunks, [{"section": "Section 8"}], k=3)
    assert score_within_k == 1.0


@pytest.mark.timeout(30)
def test_recall_case_insensitive_match() -> None:
    chunks = [_RecallFixtureChunk(text="bharatiya nyaya sanhita theft provisions.")]
    score = compute_recall_at_k(
        chunks,
        [{"section": "Bharatiya Nyaya Sanhita"}],
        k=5,
    )
    assert score == 1.0


@pytest.mark.timeout(30)
def test_recall_with_retrieved_chunk_objects() -> None:
    import uuid

    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        source_type="corpus",
        document_id=uuid.uuid4(),
        document_title="Constitution of India",
        text="Article 32 writ jurisdiction of the Supreme Court.",
        score=0.9,
        chunk_index=0,
        page_start=1,
        page_end=1,
    )
    score = compute_recall_at_k([chunk], [{"section": "Article 32"}], k=5)
    assert score == 1.0


@pytest.mark.timeout(30)
def test_recall_empty_expected_citations_returns_zero() -> None:
    chunks = [_RecallFixtureChunk(text="Any text.")]
    assert compute_recall_at_k(chunks, [], k=5) == 0.0
