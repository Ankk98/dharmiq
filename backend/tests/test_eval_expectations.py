from __future__ import annotations

from dharmiq.eval.expectations import (
    count_citation_markers,
    evaluate_answer_expectations,
    has_blockquote,
    is_refusal_answer,
)


def test_count_citation_markers() -> None:
    assert count_citation_markers("Rights under Article 22 [1] and Article 21 [2].") == 2
    assert count_citation_markers("No citations here.") == 0


def test_has_blockquote() -> None:
    assert has_blockquote("Summary\n\n> Article 22 protects liberty.\n\nEnd.")
    assert not has_blockquote("Plain answer without quotes.")


def test_is_refusal_answer() -> None:
    assert is_refusal_answer(
        "I could not find sufficient sources in the corpus or your attached documents to answer reliably."
    )
    assert not is_refusal_answer("Article 22 protects against arbitrary arrest [1].")


def test_evaluate_answer_expectations_citation_and_blockquote() -> None:
    answer = "The law says [1].\n\n> Article 22 protects liberty.\n\nDisclaimer."
    metrics = evaluate_answer_expectations(
        answer=answer,
        expect_refusal=False,
        min_citation_count=1,
        expect_blockquote=True,
    )
    assert metrics["citation_count"] == 1
    assert metrics["citation_count_met"] == 1.0
    assert metrics["blockquote_met"] == 1.0
    assert metrics["refusal_correct"] == 1.0


def test_evaluate_answer_expectations_refusal_mismatch() -> None:
    metrics = evaluate_answer_expectations(
        answer="Article 22 applies [1].",
        expect_refusal=True,
        min_citation_count=None,
        expect_blockquote=None,
    )
    assert metrics["refusal_correct"] == 0.0


def test_load_dataset_v02_expectation_fields() -> None:
    from dharmiq.eval.dataset_loader import load_dataset_records

    records = load_dataset_records("v1_fundamental_rights")
    refusal_questions = [record for record in records if record.expect_refusal]
    cited_questions = [record for record in records if record.min_citation_count and record.min_citation_count >= 1]

    assert len(records) == 8
    assert len(refusal_questions) >= 1
    assert len(cited_questions) >= 5
    assert records[0].expect_blockquote is True
