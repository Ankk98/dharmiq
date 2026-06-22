from __future__ import annotations


def check_must_not_cite_sections(answer: str, sections: list[str]) -> bool:
    """Return True when the answer does not cite any forbidden section label."""
    if not sections:
        return True

    lowered = answer.casefold()
    for section in sections:
        stripped = section.strip()
        if stripped and stripped.casefold() in lowered:
            return False
    return True
