"""PDF ingestion using PyMuPDF.

Produces page-aware DocumentChunk records with preserved page numbers.
Falls back to a lightweight TXT reader when the file is not actually a PDF.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from tenderguard.app.schemas import DocumentChunk


def _looks_like_pdf(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(4) == b"%PDF"
    except OSError:
        return False


def _read_pdf(path: Path, doc_id: str, document: str) -> list[DocumentChunk]:
    # Use the modern `pymupdf` namespace; fall back to legacy `fitz` if absent.
    try:
        import pymupdf  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - legacy fallback
        import fitz as pymupdf  # type: ignore[import-not-found, no-redef]

    chunks: list[DocumentChunk] = []
    with pymupdf.open(path) as doc:
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            text = text.strip()
            if not text:
                continue
            chunks.append(
                DocumentChunk(
                    doc_id=doc_id,
                    document=document,
                    page=index,
                    section=None,
                    text=text,
                )
            )
    return chunks


def _read_text(path: Path, doc_id: str, document: str) -> list[DocumentChunk]:
    """Treat the file as a single-page text blob. Useful for tests / TXT fallbacks."""

    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return []
    return [DocumentChunk(doc_id=doc_id, document=document, page=1, section=None, text=text)]


def ingest_pdf(path: str | os.PathLike[str], doc_id: str) -> list[DocumentChunk]:
    """Read a PDF or text-like file and return page-aware chunks."""

    p = Path(path)
    document = p.name
    if _looks_like_pdf(p):
        try:
            return _read_pdf(p, doc_id, document)
        except Exception:
            # PyMuPDF may fail on malformed PDFs; fall back to text mode.
            return _read_text(p, doc_id, document)
    return _read_text(p, doc_id, document)


def ingest_many(mapping: Iterable[tuple[str, str]]) -> list[DocumentChunk]:
    """Ingest multiple documents. mapping = [(doc_id, path), ...]"""

    out: list[DocumentChunk] = []
    for doc_id, path in mapping:
        out.extend(ingest_pdf(path, doc_id))
    return out