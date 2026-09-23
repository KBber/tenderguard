"""Heuristic fact extraction for TenderGuard v0.2.

v0.2 improvements vs v0.1:
- bidder_name: 支持 投标人/供应商/投标单位 等同义词与中文公司名（股份/有限/科技/集团等）
- responses: 章节标题识别 + "响应/应答/满足/偏离" 关键词
- deviation.test_report_name: 字段级拆分，避免把多个字段拼在一起
- 每个 fact 增加 confidence + page 字段

Extraction Layer (Spec §二): 负责"文件里到底写了什么"，**不**判断合规。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from tenderguard.app.schemas import DocumentChunk


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_MONEY_RE = re.compile(
    r"(?P<num>\d[\d,\.]*)\s*(?P<unit>万|亿|元|圆|RMB|rmb)?", re.IGNORECASE
)
_DATE_RE = re.compile(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})")
_YEAR_RE = re.compile(r"(\d{4})\s*年")
_YEAR_ONLY_RE = re.compile(r"(?<![0-9.])(19\d{2}|20\d{2})(?![0-9.])")

# Chinese company-name detector: ends with 股份 / 有限 / 科技 / 公司 / 集团 / 中心 / 厂 / 学院 / 学校 / 医院 / 局 / 部 / 处
_COMPANY_END = (
    "股份有限公司", "有限责任公司", "有限公司", "股份公司", "集团公司", "集团有限公司",
    "科技公司", "科技有限公司", "技术公司", "技术有限公司",
    "公司", "集团", "中心", "厂", "学院", "学校", "医院", "局", "部", "处",
    "事务所", "研究院", "研究所",
)
_COMPANY_RE = re.compile(
    r"([一-鿿]{2,30}(?:" + "|".join(_COMPANY_END) + r"))"
)


def _looks_like_year_token(token: str) -> bool:
    return bool(token) and len(token) == 4 and token.isdigit() and 1900 <= int(token) <= 2100


# ---------------------------------------------------------------------------
# Fact data class
# ---------------------------------------------------------------------------


@dataclass
class Fact:
    field: str
    value: Any
    document: str
    page: int
    evidence: str = ""
    confidence: float = 1.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "field": self.field,
            "value": self.value,
            "document": self.document,
            "page": self.page,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 3),
        }
        out.update(self.extra)
        return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunks_by_doc(chunks: list[DocumentChunk]) -> dict[str, list[DocumentChunk]]:
    out: dict[str, list[DocumentChunk]] = {}
    for c in chunks:
        out.setdefault(c.doc_id, []).append(c)
    return out


def _join_text(chunks: list[DocumentChunk]) -> str:
    return "\n".join(c.text for c in chunks)


def _chunks_pages(chunks: list[DocumentChunk]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for c in chunks:
        out.setdefault(c.document, []).append(c.page)
    return out


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    if m.lastindex:
        v = m.group(1) or ""
    else:
        v = m.group(0) or ""
    v = v.strip()
    return v or None


def _near(text: str, anchor: str, window: int = 80) -> str:
    idx = text.find(anchor)
    if idx == -1:
        return ""
    return text[idx : idx + len(anchor) + window]


def _segment(text: str, anchor: str, stop_anchors: list[str] | None = None, max_len: int = 60) -> str:
    idx = text.find(anchor)
    if idx == -1:
        return ""
    start = idx
    end = min(len(text), start + max_len)
    if stop_anchors:
        candidates = []
        for s in stop_anchors:
            j = text.find(s, start + len(anchor))
            if j != -1:
                candidates.append(j)
        if candidates:
            end = min(end, min(candidates))
    return text[start:end]


def _money_from_match(m: re.Match[str]) -> float | None:
    raw = m.group("num")
    unit = (m.group("unit") or "").lower()
    cleaned = raw.replace(",", "")
    try:
        n = float(cleaned)
    except ValueError:
        return None
    if unit == "" and _looks_like_year_token(cleaned):
        return None
    if unit == "万":
        n *= 10_000
    elif unit == "亿":
        n *= 100_000_000
    return n


def _extract_money(text: str) -> float | None:
    for m in _MONEY_RE.finditer(text):
        val = _money_from_match(m)
        if val and val > 1:
            return val
    return None


def _first_amount_with_unit(text: str) -> float | None:
    m = re.search(r"(\d[\d,\.]*)\s*(万|亿|元|RMB|rmb)", text)
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = m.group(2).lower()
    if unit == "万":
        v *= 10_000
    elif unit == "亿":
        v *= 100_000_000
    return v


# ---------------------------------------------------------------------------
# Bidder-name extractor (Phase 1.1)
# ---------------------------------------------------------------------------

_BIDDER_LABELS = (
    "投标人名称", "投标人", "供应商", "投标单位", "投标方", "投标主体",
    "乙方", "竞买人", "供应商名称", "申报单位名称",
)


def _extract_bidder_name(text: str) -> tuple[str | None, float]:
    """Try label-anchored patterns first, then company-name regex."""

    # 1. Label-anchored: "投标人：北京智教科技股份有限公司"
    for label in _BIDDER_LABELS:
        m = re.search(label + r"[:：]?\s*([^\n\r]+?)(?=\s{2,}|项目名称|法人|$)", text)
        if m:
            raw = m.group(1).strip()
            # Try to clip to the longest Chinese company name inside
            cm = _COMPANY_RE.search(raw)
            if cm:
                return cm.group(1), 0.95
            # Otherwise keep raw if it looks like a name
            cleaned = re.sub(r"\s+", "", raw)
            if 4 <= len(cleaned) <= 60:
                return raw.strip(), 0.7
    # 2. Company-name regex anywhere (lower confidence)
    cm = _COMPANY_RE.search(text)
    if cm:
        return cm.group(1), 0.6
    return None, 0.0


def _extract_bidder_name_pages(text: str) -> tuple[str | None, float, int]:
    """Same as _extract_bidder_name but returns the page the match was on."""

    chunks = []
    for chunk_text in text.split("\f"):
        chunks.append(chunk_text)
    if len(chunks) == 1:
        # fall back: no form-feed, treat as one page
        return (*_extract_bidder_name(text), 1)
    for page_no, page_text in enumerate(chunks, start=1):
        name, conf = _extract_bidder_name(page_text)
        if name:
            return name, conf, page_no
    return *_extract_bidder_name(text), 1


# ---------------------------------------------------------------------------
# Section/response extractor (Phase 1.2)
# ---------------------------------------------------------------------------

_RESPONSE_KEYWORDS = (
    "响应", "应答", "满足", "偏离", "承诺", "应答文件", "应答内容",
    "答复", "回复",
)

_RESPONSE_HEADERS = (
    "响应方", "商务响应", "技术响应", "商务偏离表", "技术偏离表",
    "响应表", "响应文件", "应答表", "应答文件", "应答说明",
    "应答方案", "应答情况",
)


def _extract_response_sections(text: str) -> list[str]:
    """Find chapter / heading-like responses.

    Returns list of section names that look like explicit responses.
    """

    out: list[str] = []
    seen: set[str] = set()
    # 1. 章节标题 like "1.2.3 商务响应" / "第三章 商务响应"
    for m in re.finditer(
        r"(?:^|\n)\s*(?:[\d一二三四五六七八九十]+[.\s、章]+){1,3}"
        r"([一-鿿A-Za-z]{2,20}(?:" + "|".join(_RESPONSE_HEADERS) + r")[一-鿿A-Za-z]*)",
        text,
    ):
        v = m.group(1).strip()
        if v and v not in seen:
            out.append(v)
            seen.add(v)
    # 2. Generic keywords
    for kw in _RESPONSE_KEYWORDS:
        if kw in text and kw not in seen:
            out.append(kw)
            seen.add(kw)
    return out


# ---------------------------------------------------------------------------
# Deviation / report fields (Phase 1.3)
# ---------------------------------------------------------------------------


def _extract_report_field_value(text: str, field_label: str) -> str | None:
    """Pull a labelled value that ENDS at the next field-label or punctuation."""

    m = re.search(field_label + r"[:：]?\s*([^\n\r]+)", text)
    if not m:
        return None
    raw = m.group(1).strip()
    # If raw contains another known field label, cut at it
    for stop in ("报告编号", "名称", "编号", "型号", "规格", "数量", "金额", "日期", "厂家"):
        idx = raw.find(stop, 1)
        if idx > 0 and idx < len(raw):
            raw = raw[:idx].strip()
            break
    # Drop trailing ":" / "：" / punctuation
    raw = re.sub(r"[\s:：]+$", "", raw)
    return raw or None


# ---------------------------------------------------------------------------
# Per-doc extraction
# ---------------------------------------------------------------------------


def _extract_company(text: str) -> tuple[str | None, float, int]:
    chunks = text.split("\f")
    if len(chunks) <= 1:
        return (*_extract_bidder_name(text), 1)
    for i, page_text in enumerate(chunks, start=1):
        name, conf = _extract_bidder_name(page_text)
        if name:
            return name, conf, i
    return *_extract_bidder_name(text), 1


def extract_facts(chunks: list[DocumentChunk]) -> dict[str, Any]:
    by_doc = _chunks_by_doc(chunks)
    tender_text = _join_text(by_doc.get("tender", []))
    bid_text = _join_text(by_doc.get("bid", []))
    facts: dict[str, Any] = {}

    # ---- Phase 2: structured tables ----
    from tenderguard.app.extraction.tables import (
        extract_certificate_lists,
        extract_experience_rows,
        extract_response_sections,
        best_price_table,
    )
    bid_chunks = by_doc.get("bid", [])
    tender_chunks = by_doc.get("tender", [])

    price_rows = best_price_table(bid_chunks) if bid_chunks else _extract_price_rows(bid_text)
    if price_rows:
        facts["bid.price_rows"] = price_rows
    experiences = extract_experience_rows(bid_chunks) if bid_chunks else _extract_experiences(bid_text)
    if experiences:
        facts["bid.experiences"] = experiences
    facts["bid.product_certificates"] = (
        extract_certificate_lists(bid_chunks) if bid_chunks else []
    ) or _extract_list(bid_text, ["检测报告", "节能证书", "3C", "产品彩页", "CCC", "环境标志", "环保产品"])
    facts["bid.responses"] = (
        [h["section"] for h in extract_response_sections(bid_chunks)] if bid_chunks else []
    ) or _extract_response_sections(bid_text)
    facts["tender.product_cert_requirements"] = (
        extract_certificate_lists(tender_chunks) if tender_chunks else []
    ) or _extract_list(tender_text, ["检测报告", "节能证书", "3C", "产品彩页", "CCC", "环境标志"])

    # ---------------- tender metadata ----------------
    facts["tender.project_name"] = _first_match(
        re.compile(r"项目名称[:：]\s*([^\n\r]+?)\s*项目编号"), tender_text
    )
    facts["tender.project_id"] = _first_match(
        re.compile(r"项目编号[:：]\s*([A-Za-z0-9\-_/]+)"), tender_text
    )
    facts["tender.package_id"] = _first_match(
        re.compile(r"包号[:：]\s*([A-Za-z0-9\-_/]+)"), tender_text
    )

    ceiling_seg = _segment(tender_text, "限价", stop_anchors=["保证金", "收款", "商务", "业绩"])
    facts["tender.price_ceiling"] = _first_amount_with_unit(ceiling_seg)
    if facts["tender.price_ceiling"] is None:
        seg2 = _segment(tender_text, "拦标价", stop_anchors=["保证金", "收款", "商务", "业绩"])
        facts["tender.price_ceiling"] = _first_amount_with_unit(seg2)
    if facts["tender.price_ceiling"] is None:
        # Real government PDFs often say "项目预算金额" / "预算金额" / "最高限价"
        seg3 = _segment(tender_text, "预算金额", stop_anchors=["保证金", "采购需求", "技术需求", "商务条款"])
        facts["tender.price_ceiling"] = _first_amount_with_unit(seg3)
    if facts["tender.price_ceiling"] is None:
        seg4 = _segment(tender_text, "最高限价", stop_anchors=["保证金", "采购需求"])
        facts["tender.price_ceiling"] = _first_amount_with_unit(seg4)

    # ---------------- bid metadata ----------------
    facts["bid.project_name"] = _first_match(
        re.compile(r"项目名称[:：]\s*(.+?)(?=\s*项目编号|\n|$)"), bid_text
    )
    facts["bid.project_id"] = _first_match(
        re.compile(r"项目编号[:：]\s*([A-Za-z0-9\-_/]+)"), bid_text
    )
    facts["bid.package_id"] = _first_match(
        re.compile(r"包号[:：]\s*([A-Za-z0-9\-_/]+)"), bid_text
    )

    # bidder_name (Phase 1.1)
    name, conf, _page = _extract_company(bid_text)
    if name:
        facts["bid.bidder_name"] = name
        facts.setdefault("_confidence", {})["bid.bidder_name"] = conf

    facts["bid.legal_representative"] = _first_match(
        re.compile(r"法人代表(?:姓名)?[:：]\s*(\S[^\n\r]*?)(?=\s{2,}|授权书|被授权|\n)"),
        bid_text,
    )

    # ---------------- authorization ----------------
    auth_block = _segment(bid_text, "授权书", stop_anchors=["商务", "型号", "合同", "偏离"])
    facts["authorization.legal_representative"] = (
        _first_match(re.compile(r"法人代表[:：]?\s*(\S[^\n\r]*?)(?=\s{2,}|被授权|$)"), auth_block)
        or facts["bid.legal_representative"]
    )
    facts["authorization.authorized_person"] = _first_match(
        re.compile(r"被授权人[:：]?\s*([^\n\r]+)"), auth_block
    )

    # ---------------- bond ----------------
    bond_block = _segment(bid_text, "保证金", stop_anchors=["商务", "型号", "合同", "偏离表"])
    bond_amount = _first_amount_with_unit(bond_block)
    if bond_amount:
        facts["bond.amount"] = bond_amount
    facts["bond.payee"] = _first_match(
        re.compile(r"收款(?:方|单位|人)[:：]?\s*([^\n\r]+)"), bond_block
    )

    req_bond_block = _segment(tender_text, "保证金", stop_anchors=["商务", "业绩", "检测报告"])
    req_bond = _first_amount_with_unit(req_bond_block)
    if req_bond:
        facts["requirement.bond_amount"] = req_bond
    facts["requirement.bond_payee"] = _first_match(
        re.compile(r"收款(?:方|单位|人)[:：]?\s*([^\n\r]+)"),
        req_bond_block,
    )

    # ---------------- pricing ----------------
    if "bid.price_rows" not in facts:
        facts["bid.price_rows"] = _extract_price_rows(bid_text)
    seg = _segment(bid_text, "合计", stop_anchors=["合同", "业绩", "偏离表", "检测报告"])
    total = _first_amount_with_unit(seg)
    if total is None:
        m = re.search(r"(\d[\d,\.]+)", seg)
        if m:
            try:
                total = float(m.group(1).replace(",", ""))
            except ValueError:
                total = None
    if total:
        facts["bid.total_price"] = total
    if facts.get("bid.total_price") is None:
        # Fallback: real government bid2 has "开标一览表" / "投标报价:" / "总报价"
        for kw in ("投标报价", "总报价", "报价合计", "投标总报价"):
            m = re.search(kw + r"[:：]?\s*([\d,\.]+)\s*(万|亿|元)?", bid_text)
            if m:
                v = _first_amount_with_unit(m.group(0))
                if v:
                    facts["bid.total_price"] = v
                    break
    if facts.get("bid.total_price") is None and facts.get("bid.price_rows"):
        # Last resort: sum qty × unit_price from rows; but unit_price may be missing
        # in vertical tables. Try computing only if at least one row has unit_price.
        rows = facts["bid.price_rows"]
        if any(r.get("unit_price") for r in rows):
            facts["bid.total_price"] = sum(
                (r.get("unit_price") or 0) * (r.get("qty") or 0) for r in rows
            )

    # ---------------- experiences ----------------
    if "bid.experiences" not in facts:
        facts["bid.experiences"] = _extract_experiences(bid_text)
    exp_block = _segment(tender_text, "业绩", stop_anchors=["检测", "废标"])
    m = re.search(r"(\d[\d,\.]*)\s*(万|亿|元)", exp_block)
    if m:
        try:
            v = float(m.group(1).replace(",", ""))
            unit = m.group(2)
            if unit == "万":
                v *= 10_000
            elif unit == "亿":
                v *= 100_000_000
            facts["requirement.experience_contract_amount"] = v
        except ValueError:
            pass

    # ---------------- responses (Phase 1.2) ----------------
    if "bid.responses" not in facts:
        facts["bid.responses"] = _extract_response_sections(bid_text)

    # ---------------- certs ----------------
    if "bid.product_certificates" not in facts:
        facts["bid.product_certificates"] = _extract_list(
            bid_text, ["检测报告", "节能证书", "3C", "产品彩页", "CCC", "环境标志", "环保产品"]
        )
    if "tender.product_cert_requirements" not in facts:
        facts["tender.product_cert_requirements"] = _extract_list(
            tender_text, ["检测报告", "节能证书", "3C", "产品彩页", "CCC", "环境标志"]
        )

    # ---------------- deviation / report fields (Phase 1.3) ----------------
    dev_block = _segment(bid_text, "偏离表", stop_anchors=["授权书", "合同", "商务条款"])
    facts["deviation.test_report_name"] = _extract_report_field_value(dev_block, "检测报告(?:名称|全称)?")
    facts["deviation.test_report_no"] = _extract_report_field_value(dev_block, "报告编号")
    rep_block = _segment(bid_text, "检测报告", stop_anchors=["型号", "授权书", "合同"])
    facts["report.name"] = _extract_report_field_value(rep_block, "检测报告(?:名称)?")
    facts["report.number"] = _extract_report_field_value(rep_block, "报告编号")

    return facts


# ---------------------------------------------------------------------------
# Structural helpers (price rows, experiences, etc.)
# ---------------------------------------------------------------------------


def _extract_list(text: str, anchors: list[str]) -> list[str]:
    return [a for a in anchors if a in text]


def _extract_price_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if "型号" not in line and "model" not in line.lower():
            continue
        strict = re.search(
            r"型号\s*([A-Za-z0-9\-_/]+).*?单价\s*(\d[\d,\.]*)\s*(万|元|RMB|)?"
            r"(?:.*?数量\s*(\d+))?(?:.*?小计\s*(\d[\d,\.]*)\s*(万|元|RMB|)?)?",
            line,
            re.IGNORECASE,
        )
        if not strict:
            continue
        model = strict.group(1)
        try:
            unit_price = float(strict.group(2).replace(",", "")) * (
                10000 if strict.group(3) == "万" else 1
            )
        except ValueError:
            continue
        row: dict[str, Any] = {"model": model, "unit_price": unit_price}
        if strict.group(4):
            try:
                row["qty"] = int(strict.group(4))
            except ValueError:
                pass
        if strict.group(5):
            try:
                sub_val = float(strict.group(5).replace(",", "")) * (
                    10000 if strict.group(6) == "万" else 1
                )
                row["subtotal"] = sub_val
            except ValueError:
                pass
        rows.append(row)
    return rows


def _extract_experiences(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if "合同" not in line:
            continue
        year = _YEAR_RE.search(line)
        amount: float | None = None
        m = re.search(r"(\d[\d,\.]*)\s*(万|亿|元|RMB)", line)
        if m:
            try:
                v = float(m.group(1).replace(",", ""))
                unit = m.group(2)
                if unit == "万":
                    v *= 10_000
                elif unit == "亿":
                    v *= 100_000_000
                amount = v
            except ValueError:
                amount = None
        if year or amount:
            rows.append({"date": year.group(0) if year else None, "amount": amount})
    return rows