from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

import yaml

from dharmiq.config.settings import REPO_ROOT
from dharmiq.eval.tools.allowlist import handle_from_canonical_url


def _default_allowlist() -> Path:
    return REPO_ROOT / "docs" / "plans" / "v0.6" / "central-corpus-allowlist.yaml"


def _significant_tokens(title: str) -> set[str]:
    stop = {
        "the",
        "of",
        "and",
        "act",
        "rules",
        "a",
        "an",
        "in",
        "to",
        "for",
        "on",
        "at",
    }
    tokens = re.findall(r"[a-z0-9]+", title.lower())
    return {token for token in tokens if len(token) > 2 and token not in stop}


def _titles_compatible(yaml_title: str, scraper_title: str) -> bool:
    yaml_tokens = _significant_tokens(yaml_title)
    scraper_tokens = _significant_tokens(scraper_title)
    if not yaml_tokens or not scraper_tokens:
        return True
    return bool(yaml_tokens & scraper_tokens)


def _load_scraper_row(
    conn: sqlite3.Connection,
    scraper_instrument_id: str,
) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        "SELECT instrument_id, short_title, canonical_url, type, "
        "enactment_date, enforcement_date "
        "FROM instruments WHERE instrument_id = ?",
        (scraper_instrument_id,),
    ).fetchone()


def enrich_allowlist(
    *,
    allowlist_path: Path,
    scraper_db: Path,
    dry_run: bool = True,
) -> list[str]:
    """Fill empty allowlist fields from scraper SQLite (TRD-103)."""
    if not scraper_db.is_file():
        raise FileNotFoundError(f"scraper DB not found: {scraper_db}")

    raw = yaml.safe_load(allowlist_path.read_text(encoding="utf-8")) or {}
    logs: list[str] = []
    conn = sqlite3.connect(scraper_db)

    domains = raw.get("domains", {})
    if not isinstance(domains, dict):
        raise ValueError("allowlist missing domains")

    for domain_name, domain_data in domains.items():
        if not isinstance(domain_data, dict):
            continue
        instruments = domain_data.get("instruments", [])
        if not isinstance(instruments, list):
            continue
        for item in instruments:
            if not isinstance(item, dict):
                continue
            scraper_id = item.get("scraper_instrument_id")
            if scraper_id is None:
                continue

            row = _load_scraper_row(conn, str(scraper_id))
            if row is None:
                logs.append(f"{item.get('id')}: scraper row {scraper_id} not found")
                continue

            scraper_title = str(row["short_title"] or "")
            yaml_title = str(item.get("title", ""))
            if not _titles_compatible(yaml_title, scraper_title):
                logs.append(
                    f"{item.get('id')}: scraper title mismatch "
                    f"({scraper_title!r} vs {yaml_title!r}) — skipped"
                )
                continue

            scraper_type = row["type"]
            yaml_doc_type = item.get("doc_type")
            if scraper_type and yaml_doc_type and scraper_type != yaml_doc_type:
                logs.append(
                    f"{item.get('id')}: scraper type {scraper_type!r} "
                    f"!= allowlist doc_type {yaml_doc_type!r}"
                )

            canonical_url = row["canonical_url"]
            handle = handle_from_canonical_url(canonical_url)
            if handle and not item.get("india_code_handle"):
                item["india_code_handle"] = handle
                logs.append(f"{item.get('id')}: set india_code_handle={handle}")

            if canonical_url and not item.get("canonical_url"):
                item["canonical_url"] = canonical_url
                logs.append(f"{item.get('id')}: set canonical_url from scraper")

            for field in ("enactment_date", "enforcement_date"):
                if not item.get(field) and row[field]:
                    item[field] = str(row[field])
                    logs.append(f"{item.get('id')}: set {field}={row[field]}")

            if not item.get("title") and scraper_title:
                item["title"] = scraper_title
                logs.append(f"{item.get('id')}: set title from scraper")

    conn.close()

    if not dry_run:
        allowlist_path.write_text(
            yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        logs.append(f"wrote {allowlist_path}")

    return logs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich v0.6 allowlist from indian-law-dataset-scraper SQLite",
    )
    parser.add_argument("--allowlist", type=Path, default=_default_allowlist())
    parser.add_argument("--scraper-db", type=Path, required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Print changes without writing YAML (default)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write enriched YAML back to --allowlist",
    )
    args = parser.parse_args()

    logs = enrich_allowlist(
        allowlist_path=args.allowlist,
        scraper_db=args.scraper_db,
        dry_run=not args.write,
    )
    for line in logs:
        print(line)
    if not logs:
        print("no changes")


if __name__ == "__main__":
    main()
