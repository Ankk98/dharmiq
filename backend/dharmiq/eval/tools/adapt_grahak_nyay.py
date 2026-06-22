"""Adapt Grahak-Nyay consumer Q&A into Dharmiq eval JSONL draft records.

Reads ``code/rag_qa.csv`` from a Grahak-Nyay clone (GeneralQA + SectoralQA combined).
Output is a **draft** for owner review — rename to ``v1_consumer.jsonl`` after curation.

Clone: https://github.com/ShreyGanatra/GrahakNyay.git
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from dharmiq.config.settings import REPO_ROOT

DEFAULT_GRAHAK_RELATIVE = Path("GrahakNyay")
CSV_RELATIVE = Path("code/rag_qa.csv")

# Procedural / forum-contact rows are out of product scope (TRD P3.3).
DROP_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"consumerhelpline",
        r"ncdrc\.nic\.in",
        r"cdrc\.",
        r"helpline",
        r"phone\s*number",
        r"toll[\s-]?free",
        r"format of complaint",
        r"complaint\s+format",
        r"how\s+to\s+file",
        r"where\s+(can|do)\s+i\s+(file|complain|approach)",
        r"contact\s+(the\s+)?(district|state|national)\s+commission",
        r"\b\d{10}\b",
    )
)

# Keyword → CPA 2019 citation hint (longest match wins).
SECTION_RULES: tuple[tuple[re.Pattern[str], str, list[str]], ...] = (
    (re.compile(r"e-?commerce|online\s+platform|marketplace", re.I), "Section 2(16)", ["IN-CPA-2019"]),
    (re.compile(r"product\s+liability|defective\s+product", re.I), "Section 84", ["IN-CPA-2019"]),
    (re.compile(r"misleading\s+advert", re.I), "Section 2(28)", ["IN-CPA-2019"]),
    (re.compile(r"unfair\s+trade\s+practice", re.I), "Section 2(47)", ["IN-CPA-2019"]),
    (re.compile(r"unfair\s+contract", re.I), "Section 2(46)", ["IN-CPA-2019"]),
    (re.compile(r"deficien", re.I), "Section 2(11)", ["IN-CPA-2019"]),
    (re.compile(r"\bgoods\b", re.I), "Section 2(21)", ["IN-CPA-2019"]),
    (re.compile(r"not\s+a\s+consumer", re.I), "Section 2(7)", ["IN-CPA-2019"]),
    (re.compile(r"\bconsumer\b", re.I), "Section 2(7)", ["IN-CPA-2019"]),
    (re.compile(r"mediation", re.I), "Section 74", ["IN-CPA-2019"]),
    (re.compile(r"central\s+consumer\s+protection\s+authority|\bccpa\b", re.I), "Section 10", ["IN-CPA-2019"]),
    (re.compile(r"national\s+commission", re.I), "Section 58", ["IN-CPA-2019"]),
    (re.compile(r"state\s+commission", re.I), "Section 47", ["IN-CPA-2019"]),
    (re.compile(r"district\s+commission", re.I), "Section 34", ["IN-CPA-2019"]),
    (re.compile(r"jurisdiction|pecuniary", re.I), "Section 34", ["IN-CPA-2019"]),
    (re.compile(r"right(s)?\s+(of|for)\s+consumer|consumer\s+rights", re.I), "Chapter II", ["IN-CPA-2019"]),
    (re.compile(r"food\s+safety|adulterat", re.I), "Food Safety and Standards Act 2006", ["IN-FSSA-2006"]),
    (re.compile(r"legal\s+metrology|weights?\s+and\s+measures|packag", re.I), "Legal Metrology Act 2009", ["IN-LMA-2009"]),
    (re.compile(r"competition|cartel|anti[\s-]?competitive", re.I), "Competition Act 2002", ["IN-COMPETITION-2002"]),
)

DEFAULT_SECTION = ("Consumer Protection Act 2019", ["IN-CPA-2019"])


@dataclass(frozen=True)
class GrahakQAPair:
    question: str
    answer: str
    source_file: str


def resolve_grahak_repo(explicit: Path | None = None) -> Path:
    if explicit is not None:
        repo = explicit.expanduser().resolve()
    elif env_path := os.environ.get("GRAHAK_NYAY_REPO"):
        repo = Path(env_path).expanduser().resolve()
    else:
        repo = (REPO_ROOT.parent / DEFAULT_GRAHAK_RELATIVE).resolve()

    if not repo.is_dir():
        raise FileNotFoundError(
            f"Grahak-Nyay repo not found at {repo}. "
            "Clone https://github.com/ShreyGanatra/GrahakNyay.git and set GRAHAK_NYAY_REPO "
            f"or place the clone at {REPO_ROOT.parent / DEFAULT_GRAHAK_RELATIVE}"
        )
    return repo


def resolve_csv_path(repo: Path) -> Path:
    csv_path = repo / CSV_RELATIVE
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Expected Grahak rag_qa.csv at {csv_path}. "
            "If the repo layout changed, update CSV_RELATIVE in adapt_grahak_nyay.py."
        )
    return csv_path


def load_grahak_qa_pairs(csv_path: Path) -> list[GrahakQAPair]:
    pairs: list[GrahakQAPair] = []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            question = (row.get("Question") or "").strip()
            answer = (row.get("Answer") or "").strip()
            source_file = (row.get("Filename") or "").strip()
            if question and answer:
                pairs.append(GrahakQAPair(question=question, answer=answer, source_file=source_file))
    if not pairs:
        raise ValueError(f"No Q&A rows found in {csv_path}")
    return pairs


def should_drop_row(question: str, answer: str) -> bool:
    combined = f"{question}\n{answer}"
    if len(question) < 12 or len(answer) < 60:
        return True
    return any(pattern.search(combined) for pattern in DROP_PATTERNS)


def _normalize_question(question: str) -> str:
    text = re.sub(r"\s+", " ", question).strip()
    if not text.endswith("?"):
        text = f"{text}?"
    return text


def _summarize_answer(answer: str, *, max_chars: int = 600) -> str:
    text = re.sub(r"\s+", " ", answer).strip()
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_period = truncated.rfind(". ")
    if last_period > max_chars // 2:
        return truncated[: last_period + 1]
    return truncated.rstrip() + "…"


def map_citation(question: str, answer: str) -> tuple[str, list[str]]:
    combined = f"{question}\n{answer}"
    for pattern, section, source_ids in SECTION_RULES:
        if pattern.search(combined):
            return section, source_ids
    return DEFAULT_SECTION


def adapt_pair(pair: GrahakQAPair, *, record_id: str) -> dict[str, object]:
    section, source_ids = map_citation(pair.question, pair.answer)
    return {
        "id": record_id,
        "question": _normalize_question(pair.question),
        "expected_answer": _summarize_answer(pair.answer),
        "expected_citations": [{"section": section}],
        "topic": "consumer",
        "facts": _normalize_question(pair.question),
        "min_citation_count": 1,
        "expect_blockquote": False,
        "expect_refusal": False,
        "required_source_ids": source_ids,
        "source_type": "statute",
        "locale": "en",
        "_grahak_source": pair.source_file,
    }


def adapt_grahak_pairs(
    pairs: list[GrahakQAPair],
    *,
    limit: int | None = None,
    prefer_general: bool = True,
) -> list[dict[str, object]]:
    filtered = [pair for pair in pairs if not should_drop_row(pair.question, pair.answer)]

    if prefer_general:
        general = [p for p in filtered if p.source_file == "General"]
        sectoral = [p for p in filtered if p.source_file != "General"]
        ordered = general + sectoral
    else:
        ordered = filtered

    seen_questions: set[str] = set()
    records: list[dict[str, object]] = []
    for pair in ordered:
        key = re.sub(r"\W+", " ", pair.question.lower()).strip()
        if key in seen_questions:
            continue
        seen_questions.add(key)
        record_id = f"c{len(records) + 1}"
        records.append(adapt_pair(pair, record_id=record_id))
        if limit is not None and len(records) >= limit:
            break
    return records


def write_jsonl(records: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for record in records:
        payload = {key: value for key, value in record.items() if not key.startswith("_")}
        lines.append(json.dumps(payload, ensure_ascii=False))
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Adapt Grahak-Nyay GeneralQA + SectoralQA into Dharmiq eval JSONL draft",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Path to Grahak-Nyay clone (default: $GRAHAK_NYAY_REPO or ../GrahakNyay)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "data" / "eval" / "datasets" / "v1_consumer.draft.jsonl",
        help="Output draft JSONL path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of rows to emit (default: all after filtering)",
    )
    args = parser.parse_args()

    try:
        repo = resolve_grahak_repo(args.repo)
        pairs = load_grahak_qa_pairs(resolve_csv_path(repo))
        records = adapt_grahak_pairs(pairs, limit=args.limit)
        write_jsonl(records, args.output)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Wrote {len(records)} draft rows to {args.output}")
    print("Review and rename to v1_consumer.jsonl after dropping procedural rows.")


if __name__ == "__main__":
    main()
