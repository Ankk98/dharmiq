from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class AllowlistInstrument:
    id: str
    title: str
    doc_type: str
    jurisdiction: str = "central"
    canonical_url: str | None = None
    enactment_date: str | None = None


def source_id_to_filename(source_id: str) -> str:
    """Map allowlist id to corpus PDF filename (TRD-59 convention)."""
    slug = source_id.removeprefix("IN-").lower().replace("-", "_")
    return f"{slug}.pdf"


def load_allowlist(path: Path) -> list[AllowlistInstrument]:
    """Parse mvp-corpus-allowlist.yaml and return all domain instruments."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    jurisdiction_default = str(raw.get("jurisdiction_default", "central"))
    domains = raw.get("domains")
    if not isinstance(domains, dict):
        raise ValueError(f"Invalid allowlist: missing 'domains' in {path}")

    instruments: list[AllowlistInstrument] = []
    for domain_data in domains.values():
        if not isinstance(domain_data, dict):
            continue
        for item in domain_data.get("instruments", []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            enactment_date = item.get("enactment_date")
            if enactment_date is not None:
                enactment_date = str(enactment_date)
            instruments.append(
                AllowlistInstrument(
                    id=str(item["id"]),
                    title=str(item["title"]),
                    doc_type=str(item.get("doc_type", "act")),
                    jurisdiction=str(item.get("jurisdiction", jurisdiction_default)),
                    canonical_url=item.get("canonical_url"),
                    enactment_date=enactment_date,
                )
            )

    if not instruments:
        raise ValueError(f"No instruments found in allowlist {path}")
    return instruments


def build_manifest_entries(
    instruments: list[AllowlistInstrument],
) -> list[dict[str, str]]:
    """Build manifest.json rows from allowlist instruments."""
    entries: list[dict[str, str]] = []
    for instrument in instruments:
        entry: dict[str, str] = {
            "file": source_id_to_filename(instrument.id),
            "source_id": instrument.id,
            "title": instrument.title,
            "doc_type": instrument.doc_type,
            "jurisdiction": instrument.jurisdiction,
        }
        if instrument.canonical_url:
            entry["canonical_url"] = instrument.canonical_url
        if instrument.enactment_date:
            entry["enactment_date"] = instrument.enactment_date
        entries.append(entry)
    return entries
