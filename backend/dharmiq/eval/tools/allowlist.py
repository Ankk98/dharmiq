from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CENTRAL_HANDLE_RE = re.compile(
    r"^https://www\.indiacode\.nic\.in/handle/123456789/(\d+)(?:\?.*)?$"
)
VALID_STATUSES = frozenset({"in_force", "superseded", "repealed"})
VALID_PDF_SOURCES = frozenset(
    {"bitstream", "parent_view_file", "bundle", "subset", "external"}
)
V06_DOMAINS = frozenset(
    {"fundamental_rights", "consumer", "employment", "property", "tax", "cyber"}
)


@dataclass(frozen=True)
class AllowlistInstrument:
    id: str
    title: str
    doc_type: str
    jurisdiction: str = "central"
    status: str = "in_force"
    canonical_url: str | None = None
    enactment_date: str | None = None
    enforcement_date: str | None = None
    india_code_handle: str | None = None
    scraper_instrument_id: str | None = None
    superseded_by: str | None = None
    supersedes: tuple[str, ...] = ()
    parent_act_id: str | None = None
    pdf_source: str | None = None
    pdf_url: str | None = None
    pdf_url_alt: tuple[str, ...] = ()
    shared_pdf_with: str | None = None
    notes: str | None = None
    eval_topics: tuple[str, ...] = ()


def source_id_to_filename(source_id: str) -> str:
    """Map allowlist id to corpus PDF filename (TRD-59 / TRD-81 convention)."""
    slug = source_id.removeprefix("IN-").lower().replace("-", "_")
    return f"{slug}.pdf"


def handle_from_canonical_url(canonical_url: str | None) -> str | None:
    """Extract IndiaCode numeric handle from a central repository URL (TRD-99)."""
    if not canonical_url:
        return None
    match = CENTRAL_HANDLE_RE.match(canonical_url.strip())
    return match.group(1) if match else None


def resolve_pdf_source(instrument: AllowlistInstrument) -> str:
    """Return effective PDF acquisition mode for an instrument."""
    if instrument.pdf_source:
        return instrument.pdf_source
    if instrument.doc_type in {"rule", "notification"}:
        raise ValueError(
            f"{instrument.id}: doc_type={instrument.doc_type} requires pdf_source"
        )
    return "bitstream"


def _parse_string_list(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return (str(value),)


def _parse_instrument(
    item: dict[str, Any],
    *,
    jurisdiction_default: str,
) -> AllowlistInstrument:
    enactment_date = item.get("enactment_date")
    enforcement_date = item.get("enforcement_date")
    scraper_id = item.get("scraper_instrument_id")
    return AllowlistInstrument(
        id=str(item["id"]),
        title=str(item["title"]),
        doc_type=str(item.get("doc_type", "act")),
        jurisdiction=str(item.get("jurisdiction", jurisdiction_default)),
        status=str(item.get("status", "in_force")),
        canonical_url=item.get("canonical_url"),
        enactment_date=str(enactment_date) if enactment_date is not None else None,
        enforcement_date=str(enforcement_date) if enforcement_date is not None else None,
        india_code_handle=(
            str(item["india_code_handle"])
            if item.get("india_code_handle") is not None
            else None
        ),
        scraper_instrument_id=str(scraper_id) if scraper_id is not None else None,
        superseded_by=item.get("superseded_by"),
        supersedes=_parse_string_list(item.get("supersedes")),
        parent_act_id=item.get("parent_act_id"),
        pdf_source=item.get("pdf_source"),
        pdf_url=item.get("pdf_url"),
        pdf_url_alt=_parse_string_list(item.get("pdf_url_alt")),
        shared_pdf_with=item.get("shared_pdf_with"),
        notes=item.get("notes"),
        eval_topics=_parse_string_list(item.get("eval_topics")),
    )


def load_allowlist(path: Path) -> list[AllowlistInstrument]:
    """Parse corpus allowlist YAML and return all domain instruments."""
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
            instruments.append(
                _parse_instrument(item, jurisdiction_default=jurisdiction_default)
            )

    if not instruments:
        raise ValueError(f"No instruments found in allowlist {path}")
    return instruments


def load_allowlist_domains(path: Path) -> dict[str, list[AllowlistInstrument]]:
    """Parse allowlist YAML grouped by domain key."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    jurisdiction_default = str(raw.get("jurisdiction_default", "central"))
    domains = raw.get("domains")
    if not isinstance(domains, dict):
        raise ValueError(f"Invalid allowlist: missing 'domains' in {path}")

    grouped: dict[str, list[AllowlistInstrument]] = {}
    for domain_name, domain_data in domains.items():
        if not isinstance(domain_data, dict):
            continue
        items: list[AllowlistInstrument] = []
        for item in domain_data.get("instruments", []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            items.append(
                _parse_instrument(item, jurisdiction_default=jurisdiction_default)
            )
        if items:
            grouped[str(domain_name)] = items
    return grouped


def build_manifest_entries(
    instruments: list[AllowlistInstrument],
) -> list[dict[str, Any]]:
    """Build manifest.json rows from allowlist instruments (TRD-80)."""
    entries: list[dict[str, Any]] = []
    for instrument in instruments:
        entry: dict[str, Any] = {
            "file": source_id_to_filename(instrument.id),
            "source_id": instrument.id,
            "title": instrument.title,
            "doc_type": instrument.doc_type,
            "jurisdiction": instrument.jurisdiction,
            "status": instrument.status,
        }
        if instrument.canonical_url:
            entry["canonical_url"] = instrument.canonical_url
        if instrument.enactment_date:
            entry["enactment_date"] = instrument.enactment_date
        if instrument.enforcement_date:
            entry["enforcement_date"] = instrument.enforcement_date
        if instrument.superseded_by:
            entry["superseded_by"] = instrument.superseded_by
        if instrument.supersedes:
            entry["supersedes"] = list(instrument.supersedes)
        if instrument.scraper_instrument_id:
            entry["scraper_instrument_id"] = instrument.scraper_instrument_id
        if instrument.india_code_handle:
            entry["india_code_handle"] = instrument.india_code_handle
        if instrument.parent_act_id:
            entry["parent_act_id"] = instrument.parent_act_id
        if instrument.pdf_source:
            entry["pdf_source"] = instrument.pdf_source
        if instrument.pdf_url:
            entry["pdf_url"] = instrument.pdf_url
        if instrument.pdf_url_alt:
            entry["pdf_url_alt"] = list(instrument.pdf_url_alt)
        if instrument.shared_pdf_with:
            entry["shared_pdf_with"] = instrument.shared_pdf_with
        entries.append(entry)
    return entries


def default_v06_allowlist_path(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[4]
    return root / "docs" / "plans" / "v0.6" / "central-corpus-allowlist.yaml"


def default_mvp_allowlist_path(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[4]
    return root / "docs" / "plans" / "v0.5" / "mvp-corpus-allowlist.yaml"
