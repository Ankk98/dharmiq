from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from dharmiq.eval.tools.allowlist import (
    build_manifest_entries,
    handle_from_canonical_url,
    load_allowlist,
)
from dharmiq.eval.tools.audit_allowlist import audit_allowlist_yaml
from dharmiq.eval.tools.download_indiacode_pdfs import download_pdfs
from dharmiq.eval.tools.indiacode_http import (
    fetch_pdf_with_fallback,
    iter_pdf_url_candidates,
    pick_bitstream_url,
)

FIXTURE_ALLOWLIST = (
    Path(__file__).resolve().parent / "fixtures" / "v06-allowlist-fixture.yaml"
)
CENTRAL_ALLOWLIST = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "plans"
    / "v0.6"
    / "central-corpus-allowlist.yaml"
)
MVP_ALLOWLIST = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "plans"
    / "v0.5"
    / "mvp-corpus-allowlist.yaml"
)


@pytest.mark.timeout(30)
def test_load_v06_allowlist_status_fields() -> None:
    instruments = load_allowlist(FIXTURE_ALLOWLIST)
    by_id = {item.id: item for item in instruments}

    assert by_id["IN-CPA-2019"].status == "in_force"
    assert by_id["IN-CPA-1986"].status == "superseded"
    assert by_id["IN-CPA-1986"].superseded_by == "IN-CPA-2019"
    assert by_id["IN-DPDP-RULES"].pdf_source == "parent_view_file"
    assert by_id["IN-DPDP-RULES"].parent_act_id == "IN-DPDP-2023"


@pytest.mark.timeout(30)
def test_build_manifest_includes_temporal_fields() -> None:
    instruments = load_allowlist(FIXTURE_ALLOWLIST)
    entries = build_manifest_entries(instruments)
    cpa = next(entry for entry in entries if entry["source_id"] == "IN-CPA-1986")

    assert cpa["status"] == "superseded"
    assert cpa["superseded_by"] == "IN-CPA-2019"
    assert "canonical_url" in cpa
    assert entries[0]["file"].endswith(".pdf")


@pytest.mark.timeout(30)
def test_audit_allowlist_rejects_non_central_url() -> None:
    errors = audit_allowlist_yaml(
        FIXTURE_ALLOWLIST,
        expected_count=None,
        mvp_allowlist_path=None,
    )
    assert any("IN-STATE-RENT-EXAMPLE" in err for err in errors)
    assert any("non-central canonical_url" in err for err in errors)


@pytest.mark.timeout(30)
def test_mvp_ids_preserved_in_v06_allowlist() -> None:
    mvp_ids = {item.id for item in load_allowlist(MVP_ALLOWLIST)}
    v06_ids = {item.id for item in load_allowlist(CENTRAL_ALLOWLIST)}
    missing = sorted(mvp_ids - v06_ids)
    assert missing == []


@pytest.mark.timeout(30)
def test_handle_from_canonical_url_not_instrument_id() -> None:
    handle = handle_from_canonical_url(
        "https://www.indiacode.nic.in/handle/123456789/22037"
    )
    assert handle == "22037"
    assert handle != "350"


@pytest.mark.timeout(30)
def test_download_indiacode_pdfs_probe_cpa(tmp_path: Path) -> None:
    instruments = load_allowlist(FIXTURE_ALLOWLIST)
    cpa = next(item for item in instruments if item.id == "IN-CPA-2019")
    pdf_url = "https://www.indiacode.nic.in/bitstream/123456789/15256/1/eng201935.pdf"
    page_html = (
        '<a href="/bitstream/123456789/15256/1/eng201935.pdf">PDF</a>'
    )

    mock_client = MagicMock()
    mock_client.get.side_effect = [
        httpx.Response(200, text=page_html, request=httpx.Request("GET", cpa.canonical_url)),
        httpx.Response(
            200,
            content=b"%PDF-" + b"x" * 6000,
            request=httpx.Request("GET", pdf_url),
        ),
    ]
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None

    with patch("dharmiq.eval.tools.download_indiacode_pdfs.httpx.Client", return_value=mock_client):
        exit_code = download_pdfs(
            allowlist_path=FIXTURE_ALLOWLIST,
            corpus_dir=tmp_path,
            probe=True,
            source_ids=["IN-CPA-2019"],
            delay_s=0.0,
        )
    assert exit_code == 0


@pytest.mark.timeout(30)
def test_download_indiacode_pdfs_parent_view_file(tmp_path: Path) -> None:
    instruments = load_allowlist(FIXTURE_ALLOWLIST)
    rules = next(item for item in instruments if item.id == "IN-DPDP-RULES")
    assert rules.pdf_url is not None

    mock_client = MagicMock()
    mock_client.get.return_value = httpx.Response(
        200,
        content=b"%PDF-" + b"y" * 6000,
        request=httpx.Request("GET", rules.pdf_url),
    )
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None

    with patch("dharmiq.eval.tools.download_indiacode_pdfs.httpx.Client", return_value=mock_client):
        exit_code = download_pdfs(
            allowlist_path=FIXTURE_ALLOWLIST,
            corpus_dir=tmp_path,
            write=True,
            source_ids=["IN-DPDP-RULES"],
            delay_s=0.0,
        )
    assert exit_code == 0
    assert (tmp_path / "dpdp_rules.pdf").is_file()


@pytest.mark.timeout(30)
def test_pick_bitstream_prefers_eng_filename() -> None:
    html = """
    <a href="/bitstream/123456789/20062/1/a202345.pdf">Hindi</a>
    <a href="/bitstream/123456789/20062/1/eng202345.pdf">English</a>
    """
    url = pick_bitstream_url(html, "20062")
    assert url is not None
    assert "eng202345.pdf" in url


@pytest.mark.timeout(30)
def test_audit_verify_pdf_sources_subset(tmp_path: Path) -> None:
    from dharmiq.eval.tools.audit_allowlist import verify_pdf_sources

    fixture = tmp_path / "subset-fixture.yaml"
    shared_url = (
        "https://www.indiacode.nic.in/ViewFileUploaded?path=test/"
        "&file=cgst_rules.pdf"
    )
    fixture.write_text(
        f"""
version: test
jurisdiction_default: central
domains:
  tax:
    instruments:
      - id: IN-CGST-RULES-2017
        title: CGST Rules
        doc_type: rule
        status: in_force
        pdf_source: parent_view_file
        canonical_url: https://www.indiacode.nic.in/handle/123456789/15689
        pdf_url: {shared_url}
      - id: IN-GST-INVOICE-RULES-2017
        title: GST Invoice Rules
        doc_type: rule
        status: in_force
        pdf_source: subset
        shared_pdf_with: IN-CGST-RULES-2017
        canonical_url: https://www.indiacode.nic.in/handle/123456789/15689
        pdf_url: {shared_url}
""",
        encoding="utf-8",
    )

    mock_client = MagicMock()
    mock_client.get.return_value = httpx.Response(
        200,
        content=b"%PDF-" + b"z" * 6000,
        request=httpx.Request("GET", shared_url),
    )
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None

    with patch("dharmiq.eval.tools.audit_allowlist.httpx.Client", return_value=mock_client):
        errors = verify_pdf_sources(fixture, timeout=10.0)
    assert errors == []


@pytest.mark.timeout(30)
def test_load_v06_allowlist_pdf_url_alt() -> None:
    instruments = load_allowlist(CENTRAL_ALLOWLIST)
    mta = next(item for item in instruments if item.id == "IN-MODEL-TENANCY-ACT-2021")
    assert mta.pdf_url is not None
    assert len(mta.pdf_url_alt) == 1
    assert "livelaw.in" in mta.pdf_url_alt[0]


@pytest.mark.timeout(30)
def test_pdf_url_alt_fallback_when_primary_fails(tmp_path: Path) -> None:
    fixture = tmp_path / "alt-fixture.yaml"
    primary = "https://blocked.example/primary.pdf"
    alt = "https://mirror.example/alt.pdf"
    fixture.write_text(
        f"""
version: test
jurisdiction_default: central
domains:
  property:
    instruments:
      - id: IN-MODEL-TENANCY-ACT-2021
        title: The Model Tenancy Act, 2021
        doc_type: act
        status: in_force
        pdf_source: external
        pdf_url: {primary}
        pdf_url_alt:
          - {alt}
""",
        encoding="utf-8",
    )

    instruments = load_allowlist(fixture)
    instrument = instruments[0]
    candidates = iter_pdf_url_candidates(MagicMock(), instrument)
    assert [url for _, url in candidates] == [primary, alt]

    mock_client = MagicMock()

    def fake_get(url: str, *_args, **_kwargs):
        if url == primary:
            return httpx.Response(0, content=b"", request=httpx.Request("GET", url))
        if url == alt:
            return httpx.Response(
                200,
                content=b"%PDF-" + b"a" * 6000,
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"unexpected url {url}")

    mock_client.get.side_effect = fake_get
    fetched = fetch_pdf_with_fallback(mock_client, instrument)
    assert fetched is not None
    content, url_used, label = fetched
    assert url_used == alt
    assert label == "alt-1"
    assert content.startswith(b"%PDF")


@pytest.mark.timeout(30)
def test_download_uses_pdf_url_alt_probe(tmp_path: Path) -> None:
    fixture = tmp_path / "alt-probe.yaml"
    primary = "https://blocked.example/primary.pdf"
    alt = "https://mirror.example/alt.pdf"
    fixture.write_text(
        f"""
version: test
jurisdiction_default: central
domains:
  property:
    instruments:
      - id: IN-MODEL-TENANCY-ACT-2021
        title: The Model Tenancy Act, 2021
        doc_type: act
        status: in_force
        pdf_source: external
        pdf_url: {primary}
        pdf_url_alt:
          - {alt}
""",
        encoding="utf-8",
    )

    mock_client = MagicMock()

    def fake_get(url: str, *_args, **_kwargs):
        if url == primary:
            return httpx.Response(503, content=b"down", request=httpx.Request("GET", url))
        if url == alt:
            return httpx.Response(
                200,
                content=b"%PDF-" + b"b" * 6000,
                request=httpx.Request("GET", url),
            )
        raise AssertionError(f"unexpected url {url}")

    mock_client.get.side_effect = fake_get
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None

    with patch("dharmiq.eval.tools.download_indiacode_pdfs.httpx.Client", return_value=mock_client):
        exit_code = download_pdfs(
            allowlist_path=fixture,
            corpus_dir=tmp_path,
            probe=True,
            source_ids=["IN-MODEL-TENANCY-ACT-2021"],
            delay_s=0.0,
        )
    assert exit_code == 0


@pytest.mark.timeout(30)
def test_build_manifest_includes_pdf_url_alt() -> None:
    instruments = load_allowlist(CENTRAL_ALLOWLIST)
    mta = next(item for item in instruments if item.id == "IN-MODEL-TENANCY-ACT-2021")
    entries = build_manifest_entries([mta])
    assert entries[0]["pdf_url_alt"] == [
        "https://www.livelaw.in/pdf_upload/model-tenancy-act-394449.pdf"
    ]


@pytest.mark.timeout(60)
def test_central_allowlist_yaml_audit_passes() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dharmiq.eval.tools.audit_allowlist",
            "--allowlist",
            str(CENTRAL_ALLOWLIST),
            "--mvp-allowlist",
            str(MVP_ALLOWLIST),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
