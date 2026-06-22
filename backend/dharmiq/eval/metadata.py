from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq import __version__
from dharmiq.config.settings import Settings

EVAL_PATH = "run_eval_rag"


def default_allowlist_path(repo_root: Path) -> Path:
    return repo_root / "docs" / "plans" / "v0.5" / "mvp-corpus-allowlist.yaml"


def resolve_git_sha(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        sha = result.stdout.strip()
        return sha or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def read_allowlist_version(allowlist_path: Path) -> str:
    if not allowlist_path.is_file():
        return "unknown"
    raw = yaml.safe_load(allowlist_path.read_text(encoding="utf-8")) or {}
    version = raw.get("version")
    return str(version) if version is not None else "unknown"


def hash_allowlist_file(allowlist_path: Path) -> str:
    if not allowlist_path.is_file():
        return "unknown"
    return hashlib.sha256(allowlist_path.read_bytes()).hexdigest()


async def collect_run_metadata(
    db: AsyncSession,
    *,
    settings: Settings,
    allowlist_path: Path | None = None,
) -> dict[str, str | int]:
    """Return reproducibility metadata for eval run summaries (TRD-67)."""
    from dharmiq.db.models.documents import DocumentChunk, SourceDocument

    allowlist = allowlist_path or default_allowlist_path(settings.repo_root)
    doc_count = await db.scalar(select(func.count()).select_from(SourceDocument)) or 0
    chunk_count = await db.scalar(select(func.count()).select_from(DocumentChunk)) or 0

    return {
        "git_sha": resolve_git_sha(settings.repo_root),
        "allowlist_version": read_allowlist_version(allowlist),
        "allowlist_sha256": hash_allowlist_file(allowlist),
        "corpus_document_count": int(doc_count),
        "corpus_chunk_count": int(chunk_count),
        "dharmiq_version": __version__,
        "eval_path": EVAL_PATH,
    }
