from __future__ import annotations

import pytest

from dharmiq.eval.revised_law import check_must_not_cite_sections


@pytest.mark.timeout(30)
def test_revised_law_passes_when_forbidden_section_absent() -> None:
    answer = "Theft is punishable under the Bharatiya Nyaya Sanhita [1]."
    assert check_must_not_cite_sections(
        answer,
        ["Indian Penal Code", "IPC", "Section 379 IPC"],
    )


@pytest.mark.timeout(30)
def test_revised_law_fails_when_ipc_cited() -> None:
    answer = "Section 379 of the Indian Penal Code applies to theft [1]."
    assert not check_must_not_cite_sections(answer, ["Indian Penal Code", "IPC"])


@pytest.mark.timeout(30)
def test_revised_law_case_insensitive() -> None:
    answer = "Under the code of criminal procedure, police may search."
    assert not check_must_not_cite_sections(answer, ["Code of Criminal Procedure"])


@pytest.mark.timeout(30)
def test_revised_law_empty_sections_always_passes() -> None:
    answer = "Any answer with IPC mentioned."
    assert check_must_not_cite_sections(answer, [])


@pytest.mark.timeout(30)
def test_revised_law_cpa_1986_forbidden() -> None:
    answer = "Remedies are under the Consumer Protection Act 2019 [1]."
    assert check_must_not_cite_sections(answer, ["Consumer Protection Act 1986", "CPA 1986"])

    bad_answer = "The old Consumer Protection Act 1986 may still apply."
    assert not check_must_not_cite_sections(
        bad_answer,
        ["Consumer Protection Act 1986", "CPA 1986"],
    )
