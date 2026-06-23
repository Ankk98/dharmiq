#!/usr/bin/env python3
"""Probe IndiaCode PDF sources for v0.6 Appendix A rule rows. One-off validation sprint."""

from __future__ import annotations

import html as html_lib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

SCRAPER_SRC = Path.home() / "repos/indian-law-dataset-scraper/src"
if SCRAPER_SRC.exists():
    sys.path.insert(0, str(SCRAPER_SRC))
    from indiacode.discovery import extract_related_document_links_from_page  # noqa: E402
else:
    extract_related_document_links_from_page = None  # type: ignore

BASE = "https://www.indiacode.nic.in"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Referer": f"{BASE}/",
}

# Appendix A rule/notification rows with parent act and search tokens.
RULES: list[dict[str, Any]] = [
    {
        "id": "IN-CPA-RULES-ECOMMERCE-2020",
        "parent": "IN-CPA-2019",
        "parent_handle": "15256",
        "tokens": ["e-commerce", "ecommerce", "commerce rules", "2020"],
    },
    {
        "id": "IN-CPA-RULES-2020",
        "parent": "IN-CPA-2019",
        "parent_handle": "15256",
        "tokens": ["consumer protection rules", "rules 2020", "cp rules"],
    },
    {
        "id": "IN-POSH-RULES-2013",
        "parent": "IN-POSH-2013",
        "parent_handle": "2104",
        "alt_handles": ["9178"],
        "tokens": ["sexual harassment", "workplace rules", "rules 2013"],
    },
    {
        "id": "IN-CLRA-RULES-1971",
        "parent": "IN-CLRA-1970",
        "parent_handle": "18997",
        "tokens": ["central rules", "contract labour", "1971"],
        "exclude": ["arunachal", "bihar", "goa", "islands", "state"],
    },
    {
        "id": "IN-EPF-SCHEME-1952",
        "parent": "IN-EPF-1952",
        "parent_handle": "2152",
        "tokens": ["scheme", "provident fund", "1952"],
    },
    {
        "id": "IN-MTP-RULES-2003",
        "parent": "IN-MTP-1971",
        "parent_handle": None,
        "tokens": ["medical termination", "rules 2003", "mtp rules"],
    },
    {
        "id": "IN-BNSS-RULES-2024",
        "parent": "IN-BNSS-2023",
        "parent_handle": "20099",
        "tokens": ["bnss rules", "nagarik suraksha", "rules 2024", "rules 2023"],
    },
    {
        "id": "IN-DPDP-RULES",
        "parent": "IN-DPDP-2023",
        "parent_handle": "22037",
        "tokens": ["digital personal data", "dpdp rules", "data protection rules"],
    },
    {
        "id": "IN-IT-RULES-INTERMEDIARY-2021",
        "parent": "IN-IT-2000",
        "parent_handle": "1999",
        "tokens": ["intermediary", "digital media ethics", "2021"],
    },
    {
        "id": "IN-IT-RULES-SPDI-2011",
        "parent": "IN-IT-2000",
        "parent_handle": "1999",
        "tokens": ["sensitive personal", "spdi", "reasonable security", "2011"],
    },
    {
        "id": "IN-IT-RULES-CERTIN-2022",
        "parent": "IN-IT-2000",
        "parent_handle": "1999",
        "tokens": ["cert-in", "cert in", "cyber security", "2022", "direction"],
    },
    {
        "id": "IN-RERA-RULES-2016",
        "parent": "IN-RERA-2016",
        "parent_handle": "2158",
        "tokens": ["rera rules", "real estate rules", "2016"],
        "exclude": ["daman", "dadra", "lakshwadeep", "andaman", "delhi", "agreement for sale"],
    },
    {
        "id": "IN-RERA-GENERAL-RULES-2017",
        "parent": "IN-RERA-2016",
        "parent_handle": "2158",
        "tokens": ["general rules", "rera", "2017"],
        "exclude": ["daman", "dadra", "lakshwadeep", "andaman", "delhi"],
    },
    {
        "id": "IN-REGISTRATION-RULES-1961",
        "parent": "IN-REGISTRATION-1908",
        "parent_handle": "2190",
        "tokens": ["registration rules", "1961"],
    },
    {
        "id": "IN-STAMP-RULES-1958",
        "parent": "IN-STAMP-1899",
        "parent_handle": "15510",
        "tokens": ["stamp rules", "1958", "indian stamp"],
    },
    {
        "id": "IN-LARR-RULES-2014",
        "parent": "IN-LARR-2013",
        "parent_handle": "2121",
        "tokens": ["land acquisition rules", "2014", "larr"],
    },
    {
        "id": "IN-CGST-RULES-2017",
        "parent": "IN-CGST-2017",
        "parent_handle": "15689",
        "tokens": ["cgst rules", "part-a", "central goods"],
    },
    {
        "id": "IN-IGST-RULES-2017",
        "parent": "IN-IGST-2017",
        "parent_handle": "2251",
        "tokens": ["igst rules", "integrated goods"],
    },
    {
        "id": "IN-GST-INVOICE-RULES-2017",
        "parent": "IN-CGST-2017",
        "parent_handle": "15689",
        "tokens": ["invoice rules", "invoice"],
    },
    {
        "id": "IN-GST-RETURN-RULES-2017",
        "parent": "IN-CGST-2017",
        "parent_handle": "15689",
        "tokens": ["return rules", "returns"],
    },
    {
        "id": "IN-ITR-RULES-1962",
        "parent": "IN-ITA-1961",
        "parent_handle": "2435",
        "tokens": ["income-tax rules", "income tax rules", "itr rules", "1962"],
    },
    {
        "id": "IN-TDS-RULES-1962",
        "parent": "IN-ITA-1961",
        "parent_handle": "2435",
        "tokens": ["tds", "tax deducted at source", "deduction at source"],
    },
    {
        "id": "IN-GST-REFUND-RULES-2017",
        "parent": "IN-CGST-2017",
        "parent_handle": "15689",
        "tokens": ["refund rules", "refund"],
    },
    {
        "id": "IN-GST-ASSESSMENT-RULES-2017",
        "parent": "IN-CGST-2017",
        "parent_handle": "15689",
        "tokens": ["assessment", "audit rules"],
    },
    {
        "id": "IN-IT-ELECTRONIC-SIGNATURES-2015",
        "parent": "IN-IT-2000",
        "parent_handle": "1999",
        "tokens": ["electronic signature", "e-sign", "2015"],
    },
    {
        "id": "IN-IT-DATA-RETENTION-2022",
        "parent": "IN-IT-2000",
        "parent_handle": "1999",
        "tokens": ["data retention", "retention rules", "2022"],
    },
    {
        "id": "IN-IT-CYBER-APPELLATE-RULES",
        "parent": "IN-IT-2000",
        "parent_handle": "1999",
        "tokens": ["appellate tribunal", "chairperson", "qualification"],
    },
    {
        "id": "IN-MINIMUM-WAGES-RULES-1950",
        "parent": "IN-MWA-1948",
        "parent_handle": "20357",
        "tokens": ["minimum wages", "central rules", "1950"],
        "exclude": ["state", "bihar", "goa"],
    },
    {
        "id": "IN-BONUS-RULES-1975",
        "parent": "IN-POBA-1965",
        "parent_handle": "20358",
        "tokens": ["bonus rules", "payment of bonus", "1975"],
    },
    {
        "id": "IN-EQUAL-REMUNERATION-RULES-1976",
        "parent": "IN-ERA-1976",
        "parent_handle": "20350",
        "tokens": ["equal remuneration", "1976"],
    },
]


@dataclass
class Candidate:
    url: str
    label: str
    source: str  # bitstream | view_file_uploaded | bundle_handle
    score: int = 0


@dataclass
class ProbeResult:
    id: str
    parent: str
    parent_handle: str | None
    pdf_source: str  # bitstream | parent_view_file | bundle | not_found | off_indiacode
    status: str  # VERIFIED | PARENT_PDF | BUNDLE | NOT_ON_INDIACODE | UT_ONLY | TBD
    canonical_url: str | None = None
    pdf_url: str | None = None
    pdf_bytes: int | None = None
    notes: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)


def abs_url(href: str) -> str:
    href = html_lib.unescape(href)
    if href.startswith("http"):
        return href
    return urljoin(BASE, href)


def score_label(label: str, url: str, tokens: list[str], exclude: list[str]) -> int:
    text = f"{label} {url}".lower()
    if any(ex in text for ex in exclude):
        return -100
    score = 0
    for tok in tokens:
        if tok.lower() in text:
            score += 10
    if ".pdf" in url.lower() or "viewfileuploaded" in url.lower():
        score += 1
    return score


def extract_links_from_html(html: str, handle: str) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[str] = set()

    def add(url: str, label: str, source: str) -> None:
        url = abs_url(url)
        if url in seen:
            return
        seen.add(url)
        out.append(Candidate(url=url, label=label, source=source))

    if extract_related_document_links_from_page:
        for item in extract_related_document_links_from_page(html):
            src = "view_file_uploaded" if "ViewFileUploaded" in item["url"] else "bitstream"
            add(item["url"], item.get("label", ""), src)

    for m in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        if "ViewFileUploaded" in m or "/bitstream/" in m:
            add(m, Path(m).name, "view_file_uploaded" if "ViewFileUploaded" in m else "bitstream")

    for m in re.findall(
        rf"/bitstream/123456789/{handle}/\d+/[^\"']+\.pdf", html, re.I
    ):
        add(m if m.startswith("http") else BASE + m, Path(m).name, "bitstream")

    return out


def probe_pdf(client: httpx.Client, url: str) -> tuple[bool, int, int]:
    try:
        r = client.get(url)
    except httpx.HTTPError:
        return False, 0, 0
    is_pdf = r.content[:4] == b"%PDF"
    return is_pdf, r.status_code, len(r.content)


def resolve_parent_handle(rule: dict[str, Any], client: httpx.Client) -> str | None:
    h = rule.get("parent_handle")
    if h:
        return str(h)
    return None


def probe_rule(client: httpx.Client, rule: dict[str, Any]) -> ProbeResult:
    rid = rule["id"]
    parent = rule["parent"]
    tokens = rule["tokens"]
    exclude = rule.get("exclude", [])
    parent_handle = resolve_parent_handle(rule, client)

    handles = []
    if parent_handle:
        handles.append(parent_handle)
    handles.extend(rule.get("alt_handles", []))

    all_candidates: list[Candidate] = []
    for handle in handles:
        page_url = f"{BASE}/handle/123456789/{handle}"
        try:
            r = client.get(page_url)
        except httpx.HTTPError as exc:
            return ProbeResult(
                id=rid,
                parent=parent,
                parent_handle=parent_handle,
                pdf_source="not_found",
                status="TBD",
                notes=f"parent page fetch failed: {exc}",
            )
        if r.status_code != 200:
            continue
        for cand in extract_links_from_html(r.text, handle):
            cand.score = score_label(cand.label, cand.url, tokens, exclude)
            all_candidates.append(cand)

    all_candidates.sort(key=lambda c: c.score, reverse=True)
    top = [c for c in all_candidates if c.score > 0][:8]

    for cand in top:
        ok, status, nbytes = probe_pdf(client, cand.url)
        if ok and nbytes >= 5000:
            pdf_source = (
                "bundle"
                if cand.source == "bitstream" and "rules" in cand.label.lower()
                else cand.source
            )
            st = "VERIFIED"
            if pdf_source == "view_file_uploaded":
                st = "PARENT_PDF"
            elif pdf_source == "bundle":
                st = "BUNDLE"
            canon = (
                f"{BASE}/handle/123456789/{parent_handle}"
                if parent_handle
                else None
            )
            return ProbeResult(
                id=rid,
                parent=parent,
                parent_handle=parent_handle,
                pdf_source=pdf_source,
                status=st,
                canonical_url=canon,
                pdf_url=cand.url,
                pdf_bytes=nbytes,
                notes=cand.label[:200],
                candidates=[asdict(c) for c in top[:5]],
            )

    # Check if best candidates are UT/state only
    if all_candidates and all(c.score < 0 for c in all_candidates[:5]):
        return ProbeResult(
            id=rid,
            parent=parent,
            parent_handle=parent_handle,
            pdf_source="not_found",
            status="UT_ONLY",
            notes="Only UT/state rule PDFs found on parent page",
            candidates=[asdict(c) for c in all_candidates[:5]],
        )

    # No positive match
    best = all_candidates[:5]
    note = "No matching PDF on IndiaCode parent page"
    if not handles:
        note = "Parent handle unknown"
    elif not all_candidates:
        note = "Parent page has no PDF links"

    return ProbeResult(
        id=rid,
        parent=parent,
        parent_handle=parent_handle,
        pdf_source="not_found",
        status="NOT_ON_INDIACODE",
        canonical_url=f"{BASE}/handle/123456789/{parent_handle}" if parent_handle else None,
        notes=note,
        candidates=[asdict(c) for c in best],
    )


def lookup_sqlite_handles() -> dict[str, str]:
    import sqlite3

    db = Path.home() / "repos/indian-law-dataset-scraper/data/indiacode.sqlite3"
    if not db.exists():
        return {}
    conn = sqlite3.connect(db)
    patterns = {
        "IN-MTP-1971": "%Medical Termination of Pregnancy Act, 1971%",
        "IN-IT-AMENDMENT-ACT-2008": "%Information Technology (Amendment) Act, 2008%",
        "IN-FACTORIES-1948": "%Factories Act, 1948%",
        "IN-ESIC-1948": "%Employees%State Insurance Act, 1948%",
        "IN-PAYMENT-GRATUITY-1972": "%Payment of Gratuity Act, 1972%",
        "IN-DOWRY-1961": "%Dowry Prohibition Act, 1961%",
        "IN-DOMESTIC-VIOLENCE-2005": "%Domestic Violence Act, 2005%",
        "IN-SC-ST-PREVENTION-1989": "%Scheduled Castes%Prevention of Atrocities%",
        "IN-MODEL-TENANCY-ACT-2021": "%Model Tenancy Act%",
    }
    out: dict[str, str] = {}
    for kid, pat in patterns.items():
        row = conn.execute(
            "SELECT canonical_url FROM instruments WHERE short_title LIKE ? AND canonical_url LIKE '%123456789%' LIMIT 1",
            (pat,),
        ).fetchone()
        if row and row[0]:
            m = re.search(r"/(\d+)(?:\?|$)", row[0])
            if m:
                out[kid] = m.group(1)
    conn.close()
    return out


def main() -> None:
    sqlite_handles = lookup_sqlite_handles()
    if sqlite_handles.get("IN-MTP-1971"):
        for rule in RULES:
            if rule["id"] == "IN-MTP-RULES-2003":
                rule["parent_handle"] = sqlite_handles["IN-MTP-1971"]

    results: list[ProbeResult] = []
    with httpx.Client(timeout=90, follow_redirects=True, headers=HEADERS) as client:
        for i, rule in enumerate(RULES):
            if i:
                time.sleep(0.4)
            results.append(probe_rule(client, rule))

    summary = {
        "probed_at": time.strftime("%Y-%m-%d"),
        "total": len(results),
        "verified": sum(1 for r in results if r.status in ("VERIFIED", "PARENT_PDF", "BUNDLE")),
        "not_on_indiacode": sum(1 for r in results if r.status == "NOT_ON_INDIACODE"),
        "ut_only": sum(1 for r in results if r.status == "UT_ONLY"),
        "sqlite_parent_handles": sqlite_handles,
        "results": [asdict(r) for r in results],
    }
    out_path = Path(__file__).resolve().parent.parent / "docs/plans/v0.6/rule-probe-results.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
