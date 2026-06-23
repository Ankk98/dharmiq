from __future__ import annotations

from pathlib import Path

import pytest

from dharmiq.eval.tools.allowlist import (
    build_manifest_entries,
    load_allowlist,
    source_id_to_filename,
)
from dharmiq.eval.tools.build_manifest import build_manifest

FIXTURE_ALLOWLIST = Path(__file__).resolve().parent / "fixtures" / "mvp-allowlist-fixture.yaml"


@pytest.mark.timeout(30)
def test_source_id_to_filename() -> None:
    assert source_id_to_filename("IN-CPA-2019") == "cpa_2019.pdf"
    assert source_id_to_filename("IN-CONSTITUTION-1949") == "constitution_1949.pdf"
    assert source_id_to_filename("IN-BNSS-2023") == "bnss_2023.pdf"


@pytest.mark.timeout(30)
def test_build_manifest_from_fixture_yaml(tmp_path: Path) -> None:
    instruments = load_allowlist(FIXTURE_ALLOWLIST)
    assert len(instruments) == 3

    entries = build_manifest_entries(instruments)
    assert len(entries) == 3
    assert entries[0]["source_id"] == "IN-CONSTITUTION-1949"
    assert entries[0]["file"] == "constitution_1949.pdf"
    assert entries[0]["doc_type"] == "act"
    assert entries[0]["jurisdiction"] == "central"
    assert "canonical_url" in entries[0]

    corpus_dir = tmp_path / "raw"
    corpus_dir.mkdir()
    (corpus_dir / "constitution_1949.pdf").write_bytes(b"%PDF-1.4")

    written = build_manifest(
        allowlist_path=FIXTURE_ALLOWLIST,
        corpus_dir=corpus_dir,
        write=True,
    )
    assert len(written) == 3

    manifest_path = corpus_dir / "manifest.json"
    assert manifest_path.is_file()
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert '"source_id": "IN-CPA-2019"' in manifest_text
    assert '"file": "cpa_2019.pdf"' in manifest_text


@pytest.mark.timeout(30)
def test_build_manifest_includes_v06_status_fields(tmp_path: Path) -> None:
    v06_fixture = (
        Path(__file__).resolve().parent / "fixtures" / "v06-allowlist-fixture.yaml"
    )
    instruments = load_allowlist(v06_fixture)
    entries = build_manifest_entries(instruments)
    cpa = next(entry for entry in entries if entry["source_id"] == "IN-CPA-1986")

    assert cpa["status"] == "superseded"
    assert cpa["superseded_by"] == "IN-CPA-2019"
    assert "canonical_url" in cpa

    corpus_dir = tmp_path / "raw"
    corpus_dir.mkdir()
    (corpus_dir / "cpa_2019.pdf").write_bytes(b"%PDF-1.4")

    written = build_manifest(
        allowlist_path=v06_fixture,
        corpus_dir=corpus_dir,
        write=True,
    )
    assert len(written) == len(instruments)
    manifest_text = (corpus_dir / "manifest.json").read_text(encoding="utf-8")
    assert '"status": "in_force"' in manifest_text
