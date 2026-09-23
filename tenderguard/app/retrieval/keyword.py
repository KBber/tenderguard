"""P0 keyword retrieval baseline.

Scores each DocumentChunk by:
  - token overlap with the query (BM25-lite IDF weighting)
  - exact substring match bonus
  - shorter-document length normalization

Phase 4: each returned Evidence is tagged with one of:
  DIRECT / INDIRECT / WEAK / CONFLICTING / MISSING
based on the relevance score and whether the quote contains the literal query.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

from tenderguard.app.schemas import DocumentChunk, Evidence, EvidenceQuality


_TOKEN_RE = re.compile(r"[\w一-鿿]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _bigrams(text: str) -> list[str]:
    out: list[str] = []
    for i in range(len(text) - 1):
        pair = text[i : i + 2]
        if re.search(r"[一-鿿]", pair):
            out.append(pair.lower())
    return out


def _tokenize_cjk(text: str) -> list[str]:
    return _tokenize(text) + _bigrams(text)


def _doc_freq(chunks: Iterable[DocumentChunk]) -> Counter[str]:
    df: Counter[str] = Counter()
    for c in chunks:
        for term in set(_tokenize_cjk(c.text)):
            df[term] += 1
    return df


def _classify_quality(relevance: float, has_phrase: bool = False) -> EvidenceQuality:
    if relevance <= 0:
        return EvidenceQuality.MISSING
    if has_phrase and relevance >= 0.5:
        return EvidenceQuality.DIRECT
    if relevance >= 0.4:
        return EvidenceQuality.INDIRECT
    return EvidenceQuality.INDIRECT


def retrieve(
    query: str,
    chunks: list[DocumentChunk],
    *,
    top_k: int = 5,
    doc_filter: list[str] | None = None,
) -> list[Evidence]:
    if not chunks:
        return []

    pool = [c for c in chunks if not doc_filter or c.doc_id in doc_filter]
    if not pool:
        return []

    q_tokens = _tokenize_cjk(query)
    if not q_tokens:
        return []

    df = _doc_freq(pool)
    n = len(pool)
    idf = {term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    scored: list[tuple[float, DocumentChunk]] = []
    q_counter = Counter(q_tokens)
    needle = query.strip().lower()

    for c in pool:
        toks = _tokenize_cjk(c.text)
        if not toks:
            continue
        tf = Counter(toks)
        score = 0.0
        for term, qtf in q_counter.items():
            if term not in tf:
                continue
            score += idf.get(term, 0.0) * tf[term] * (qtf) / (tf[term] + 1.0)
        has_phrase = bool(needle) and any(needle in tok for tok in toks)
        if has_phrase:
            score += 1.5
        if score <= 0:
            continue
        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return []

    max_score = scored[0][0] or 1.0
    out: list[Evidence] = []
    for score, c in scored[:top_k]:
        snippet = c.text.strip().replace("\n", " ")
        if len(snippet) > 240:
            snippet = snippet[:240] + "…"
        rel = min(1.0, score / max_score)
        quality = _classify_quality(rel, has_phrase=bool(needle) and needle in c.text.lower())
        out.append(
            Evidence(
                document=c.document,
                page=c.page,
                chunk_id=f"{c.doc_id}:p{c.page}",
                quote=snippet,
                locator=f"page:{c.page}",
                relevance=round(rel, 3),
                score=round(score, 3),
                evidence_type="direct" if quality == EvidenceQuality.DIRECT else "indirect",
                doc_id=c.doc_id,
                source_type="tender" if c.doc_id == "tender" else "bid",
                quality=quality,
            )
        )
    return out