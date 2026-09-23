"""Table extraction for TenderGuard v0.2 (Phase 2).

Unified pipeline (spec §八):
  Document → Blocks → Tables → Facts

Currently a block is a single line of text from PyMuPDF. A *Table* is a list of
rows sharing a header that matches a known schema. Each table is anchored by
a header keyword (e.g. "型号 单价 数量") and a body of "|"-separated or
whitespace-separated cells.

v0.2 ships table extractors for the categories the 直投CK cares about:
  - price_rows  (分项报价表)
  - experiences (业绩)
  - certificates / qualifications (资质)
  - tender requirements (招标要求)
  - bid responses (商务/技术响应)
  - params (技术参数表)

The result of each extractor is a `Table` with a deterministic schema; downstream
rules can rely on field names without re-parsing the raw PDF.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from tenderguard.app.schemas import DocumentChunk


@dataclass
class Table:
    schema: str
    document: str
    page: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "document": self.document,
            "page": self.page,
            "rows": self.rows,
        }


# ---------------------------------------------------------------------------
# Cell parsing helpers
# ---------------------------------------------------------------------------

_NUM = re.compile(r"\d[\d,\.]*")


def _to_num(s: str) -> float | None:
    if not s:
        return None
    s = s.strip()
    mult = 1.0
    if "万" in s:
        mult = 10_000.0
    elif "亿" in s:
        mult = 100_000_000.0
    s = s.replace(",", "")
    m = _NUM.search(s)
    if not m:
        return None
    try:
        return float(m.group(0)) * mult
    except ValueError:
        return None


def _split_cells(line: str) -> list[str]:
    """Split a line into cells on whitespace runs, tabs or pipes."""

    if "|" in line:
        cells = [c.strip() for c in line.split("|") if c.strip()]
    else:
        cells = re.split(r"\s{2,}|\t", line.strip())
        cells = [c.strip() for c in cells if c.strip()]
    return cells


# ---------------------------------------------------------------------------
# Generic header detector
# ---------------------------------------------------------------------------


def _looks_like_header(cells: list[str], must_have: list[str]) -> bool:
    joined = " ".join(cells)
    return all(kw in joined for kw in must_have)


def _lines_for(chunks: list[DocumentChunk]) -> list[tuple[DocumentChunk, str]]:
    out: list[tuple[DocumentChunk, str]] = []
    for c in chunks:
        for line in c.text.splitlines():
            out.append((c, line))
    return out


# ---------------------------------------------------------------------------
# Price-table extractor
# ---------------------------------------------------------------------------


def extract_price_tables(chunks: list[DocumentChunk]) -> list[Table]:
    """Find lines whose header row matches a 报价表 schema.

    Recognised headers: 型号 / 单价 / 数量 / 小计.
    Falls back to keyword-anchored single-line extraction if no explicit header.
    """

    tables: list[Table] = []
    current: Table | None = None
    header_required = ("型号", "单价")

    for chunk, line in _lines_for(chunks):
        cells = _split_cells(line)
        if not cells:
            continue
        if _looks_like_header(cells, list(header_required)):
            if current and current.rows:
                tables.append(current)
            current = Table(schema="price_rows", document=chunk.document, page=chunk.page, raw=line)
            continue
        if current and any("型号" in c for c in cells):
            model = next((c for c in cells if re.match(r"^[A-Za-z0-9\-_/]+$", c) and not c.isdigit()), None)
            if not model:
                continue
            row: dict[str, Any] = {"model": model, "page": chunk.page, "document": chunk.document}
            numbers = [_to_num(c) for c in cells if _to_num(c) is not None]
            if numbers:
                row["unit_price"] = numbers[0]
            if len(numbers) >= 2:
                row["qty"] = int(numbers[1]) if numbers[1] == int(numbers[1]) else numbers[1]
            if len(numbers) >= 3:
                row["subtotal"] = numbers[2]
            current.rows.append(row)

    # Fallback: no header was detected, but lines with 型号 X 单价 Y are present
    if not tables:
        fallback = Table(schema="price_rows", document=chunks[0].document if chunks else "bid.pdf", page=1)
        for chunk, line in _lines_for(chunks):
            if "型号" not in line or "单价" not in line:
                continue
            m = re.search(
                r"型号\s*([A-Za-z0-9\-_/]+).*?单价\s*(\d[\d,\.]*)\s*(万|元|RMB|)?"
                r"(?:.*?数量\s*(\d+))?(?:.*?小计\s*(\d[\d,\.]*)\s*(万|元|RMB|)?)?",
                line,
                re.IGNORECASE,
            )
            if not m:
                continue
            model = m.group(1)
            try:
                unit_price = float(m.group(2).replace(",", "")) * (10000 if m.group(3) == "万" else 1)
            except ValueError:
                continue
            row: dict[str, Any] = {"model": model, "unit_price": unit_price, "page": chunk.page, "document": chunk.document}
            if m.group(4):
                try:
                    row["qty"] = int(m.group(4))
                except ValueError:
                    pass
            if m.group(5):
                try:
                    row["subtotal"] = float(m.group(5).replace(",", "")) * (10000 if m.group(6) == "万" else 1)
                except ValueError:
                    pass
            fallback.rows.append(row)
        if fallback.rows:
            tables.append(fallback)

    if current and current.rows:
        tables.append(current)
    return tables


def best_price_table(chunks: list[DocumentChunk]) -> list[dict[str, Any]]:
    """Try single-line header detection first; fall back to vertical-header multi-page."""
    tables = extract_price_tables(chunks)
    if tables:
        tables.sort(key=lambda t: len(t.rows), reverse=True)
        return tables[0].rows
    return extract_vertical_price_table(chunks)


# ---------------------------------------------------------------------------
# Experience / certificate / response extractors
# ---------------------------------------------------------------------------


def extract_experience_rows(chunks: list[DocumentChunk]) -> list[dict[str, Any]]:
    """Pick up "合同 YYYY年 AMOUNT万" lines as experiences."""

    rows: list[dict[str, Any]] = []
    for chunk, line in _lines_for(chunks):
        if "合同" not in line:
            continue
        year = re.search(r"(\d{4})\s*年", line)
        m = re.search(r"(\d[\d,\.]*)\s*(万|亿|元|RMB)", line)
        amount = None
        if m:
            v = _to_num(m.group(0))
            amount = v
        if year or amount:
            rows.append({
                "date": year.group(0) if year else None,
                "amount": amount,
                "document": chunk.document,
                "page": chunk.page,
            })
    return rows


_CERT_LABELS = ("检测报告", "节能证书", "3C", "CCC", "产品彩页", "环境标志", "环保产品", "质量管理体系", "管理体系认证")


def extract_certificate_lists(chunks: list[DocumentChunk]) -> list[str]:
    """List of certificate kinds mentioned in the document."""

    joined = "\n".join(c.text for c in chunks)
    return [label for label in _CERT_LABELS if label in joined]


def extract_response_sections(chunks: list[DocumentChunk]) -> list[dict[str, Any]]:
    """Find chapter headings that read like 商务响应 / 技术响应 / 偏离."""

    headings: list[dict[str, Any]] = []
    keywords = ("商务响应", "技术响应", "商务偏离", "技术偏离", "响应方", "应答", "响应表", "响应文件")
    for chunk, line in _lines_for(chunks):
        if not any(k in line for k in keywords):
            continue
        # Skip pure header / footer
        if len(line) > 200:
            continue
        if not re.search(r"[一二三四五六七八九十0-9]", line):
            continue
        headings.append({"section": line.strip(), "document": chunk.document, "page": chunk.page})
    return headings


def extract_all_tables(chunks: list[DocumentChunk]) -> dict[str, list[dict[str, Any]]]:
    """Top-level entry: every table schema → list of structured records."""

    rows = best_price_table(chunks)
    if not rows:
        rows = extract_vertical_price_table(chunks)
    return {
        "price_rows": rows,
        "experiences": extract_experience_rows(chunks),
        "certificates": [{"name": n} for n in extract_certificate_lists(chunks)],
        "responses": extract_response_sections(chunks),
    }


# ---------------------------------------------------------------------------
# Multi-line 分项报价表 (vertical-header + multi-page rows)
# ---------------------------------------------------------------------------
# Many real-world government tender PDFs format 分项报价表 with a vertical
# header column and rows that span multiple pages (header row printed once,
# then 1 row per page). Each row contains:
#   序号 | 分项名称 | ... | 品牌 规格型号 | 单价 | 数量 | 合价
# but because the header is vertical, header detection fails.
#
# Strategy:
#   1. Find anchor pages that contain "分项报价表" / "开标一览表".
#   2. From the anchor page onward (next N pages), parse each non-empty line.
#   3. A row is recognised by a leading "序号" digit OR a model-code fragment
#      (e.g. "TC-XXXX" / "型号 XXX").  Quantity is the last small integer
#      (<= 9999) on the line.
#
# Returns: list of {"model": "<spec>", "qty": <int>, "page": int}
# ---------------------------------------------------------------------------

_MODEL_PATTERNS = [
    re.compile(r"\bTC[-A-Z0-9]+"),
    re.compile(r"\b[A-Z]{1,4}-?\d{3,}[A-Z0-9-]*"),  # generic model code
]

_ANCHOR_KEYWORDS = ("分项报价表", "报价一览表")  # note: 开标一览表 是另一张表，不要混入


def _is_model_token(tok: str) -> bool:
    tok = tok.strip()
    if not tok or len(tok) < 4:
        return False
    return any(p.search(tok) for p in _MODEL_PATTERNS)


def extract_vertical_price_table(chunks: list[DocumentChunk], max_pages: int = 8) -> list[dict[str, Any]]:
    """Parse a multi-page 分项报价表 with vertical header.

    Each PDF row is split into 3 visual lines (PyMuPDF column extraction):
      line 1: 序号 (= n)
      line 2: 分项名称  制造商  产地  信用代码  规模  品牌  规格型号 配置:...
      line 3: 单价 (元)  数量 (= n)

    Algorithm: 5 states, distinguished by what we have seen so far for the
    CURRENT row.  When a new seq arrives we flush.

    State machine:
      INIT      -> waiting for seq
      HAVE_SEQ  -> waiting for model
      HAVE_MODEL -> waiting for qty (the qty is the next single-integer line)
      HAVE_QTY  -> row complete; the NEXT integer starts the next row's seq
      (any noise line is ignored)
    """

    out: list[dict[str, Any]] = []
    in_table = False
    anchor_page = -1
    cur_seq: int | None = None
    cur_model: str | None = None
    cur_qty: int | None = None

    def _flush():
        nonlocal cur_seq, cur_model, cur_qty
        if cur_seq is not None and cur_model is not None:
            out.append({
                "seq": cur_seq,
                "model": cur_model,
                "qty": cur_qty,
            })
        cur_seq = None
        cur_model = None
        cur_qty = None

    for chunk in chunks:
        text = chunk.text or ""
        if not in_table:
            if any(k in text for k in _ANCHOR_KEYWORDS):
                in_table = True
                anchor_page = chunk.page
                continue
            continue
        if chunk.page - anchor_page > max_pages:
            _flush()
            break
        if any(k in text for k in ("合同条款偏离表", "技术方案", "商务条款")) and chunk.page > anchor_page + 1:
            _flush()
            break
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            tokens = re.split(r"\s+", line)
            if len(tokens) == 1 and tokens[0].isdigit():
                v = int(tokens[0])
                if v >= 10000:
                    continue
                if cur_qty is not None:
                    # previous row had seq+model+qty; this int is the next row's seq
                    _flush()
                    cur_seq = v
                elif cur_model is not None:
                    # seq+model seen; this int is the qty
                    cur_qty = v
                elif cur_seq is not None:
                    # seq seen but no model (e.g. header text consumed before model);
                    # treat as next row's seq
                    _flush()
                    cur_seq = v
                else:
                    # no seq yet -> this int starts the first row
                    cur_seq = v
                continue
            m = re.search(r"TC[-A-Z0-9]+", line)
            if m:
                cur_model = m.group(0)
                continue
    _flush()
    return out