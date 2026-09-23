"""Deterministic rule engine for TenderGuard.

Each operator consumes a `facts` dict and returns a RuleResult:
  passed: bool | None      # None when result is indeterminate
  trace:  dict             # human-auditable trace
  reason: str              # why this result
  missing: list[str]       # fact keys that are missing
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RuleResult:
    passed: bool | None
    reason: str
    trace: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    actual_value: Any = None
    expected_value: Any = None
    rule_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "missing": list(self.missing),
            "trace": self.trace,
            "actual_value": self.actual_value,
            "expected_value": self.expected_value,
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _get_path(facts: dict[str, Any], dotted: str) -> Any:
    if dotted in facts:
        return facts[dotted]
    cur: Any = facts
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(dotted)
    return cur


def _try_get(facts: dict[str, Any], dotted: str) -> tuple[Any, bool]:
    try:
        return _get_path(facts, dotted), True
    except KeyError:
        return None, False


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    s = re.sub(r"\s+", "", s)
    s = s.replace("（", "(").replace("）", ")")
    return s


def _parse_money(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value)
    multiplier = 1.0
    if "万" in s:
        multiplier = 10_000.0
    if "亿" in s:
        multiplier = 100_000_000.0
    cleaned = re.sub(r"[^\d.\-]", "", s.replace(",", ""))
    if not cleaned or cleaned in {"-", ".", "-."}:
        return None
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None


def _parse_date(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    s = str(value)
    m = re.search(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})", s)
    if not m:
        m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})", s)
    if not m:
        y = re.search(r"(\d{4})\s*年", s)
        if y:
            return f"{int(y.group(1)):04d}-01-01"
        return None
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def normalize_model(raw: Any) -> str:
    """Spec §九: normalize model codes for same_model_same_price.

    Rules:
      - uppercase
      - collapse whitespace
      - unify separators (full-width hyphen, ideographic hyphen, em-space, etc.)
      - strip parentheticals e.g. ABC-100（含税）
      - but keep case (so 'ABC-100' and 'abc-100' collapse together)
    """

    if raw is None:
        return ""
    s = str(raw).upper()
    # unify separators
    s = s.replace("－", "-").replace("—", "-").replace("−", "-").replace(" ", "")
    # strip parentheticals
    s = re.sub(r"（[^）]*）", "", s)
    s = re.sub(r"\([^)]*\)", "", s)
    return s.strip()


def _result(passed: bool | None, reason: str, **kw: Any) -> RuleResult:
    return RuleResult(passed=passed, reason=reason, **kw)


# ---------------------------------------------------------------------------
# Spec-required operators (Spec §5)
# ---------------------------------------------------------------------------


def op_equals(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    fields = rule.get("fields", [])
    if not isinstance(fields, list) or len(fields) < 2:
        return _result(None, "equals requires >=2 fields", trace={"rule": rule})
    vals: list[Any] = []
    missing: list[str] = []
    for f in fields:
        v, ok = _try_get(facts, f)
        if not ok:
            missing.append(f)
        vals.append(v)
    trace = {"fields": fields, "values": vals}
    if missing:
        return _result(None, f"missing facts: {missing}", trace=trace, missing=missing)
    norm = [_norm_text(v) for v in vals]
    trace["normalized"] = norm
    # If any value is empty, treat as indeterminate → None
    if not all(norm):
        return _result(None, "one or more values empty", trace=trace, missing=missing)
    if len(set(norm)) == 1:
        return _result(True, "all values equal", trace=trace, actual_value=vals[0], expected_value=vals[0])
    return _result(False, "values differ", trace=trace, actual_value=vals, expected_value=vals)


def op_not_equals(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    fields = rule.get("fields", [])
    if not isinstance(fields, list) or len(fields) < 2:
        return _result(None, "not_equals requires >=2 fields", trace={"rule": rule})
    vals: list[Any] = []
    missing: list[str] = []
    for f in fields:
        v, ok = _try_get(facts, f)
        if not ok:
            missing.append(f)
        vals.append(v)
    trace = {"fields": fields, "values": vals}
    if missing:
        return _result(None, f"missing facts: {missing}", trace=trace, missing=missing)
    norm = [_norm_text(v) for v in vals]
    trace["normalized"] = norm
    if not all(norm):
        return _result(None, "one or more values empty", trace=trace, missing=missing)
    if len(set(norm)) > 1:
        return _result(True, "values differ", trace=trace)
    return _result(False, "all values identical", trace=trace)


def op_contains(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    field = rule.get("field")
    needle = rule.get("value") or rule.get("needle")
    if not (field and needle):
        return _result(None, "contains requires field and value", trace={"rule": rule})
    value, ok = _try_get(facts, field)
    if not ok:
        return _result(None, f"missing fact: {field}", trace={"rule": rule}, missing=[field])
    text = str(value) if value is not None else ""
    hit = str(needle) in text
    return _result(hit, f"{'found' if hit else 'not found'}: {needle}", trace={"field": field, "needle": needle}, actual_value=text[:120], expected_value=needle)


def op_not_contains(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    field = rule.get("field")
    needle = rule.get("value") or rule.get("needle")
    if not (field and needle):
        return _result(None, "not_contains requires field and value", trace={"rule": rule})
    value, ok = _try_get(facts, field)
    if not ok:
        return _result(None, f"missing fact: {field}", trace={"rule": rule}, missing=[field])
    text = str(value) if value is not None else ""
    hit = str(needle) in text
    return _result(not hit, f"{'absent' if not hit else 'present'}: {needle}", trace={"field": field, "needle": needle}, actual_value=text[:120], expected_value=needle)


def op_regex(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    field = rule.get("field")
    pattern = rule.get("pattern")
    if not (field and pattern):
        return _result(None, "regex requires field and pattern", trace={"rule": rule})
    value, ok = _try_get(facts, field)
    if not ok:
        return _result(None, f"missing fact: {field}", trace={"rule": rule}, missing=[field])
    text = str(value) if value is not None else ""
    hit = re.search(pattern, text) is not None
    return _result(hit, f"{'matches' if hit else 'no match'}", trace={"field": field, "pattern": pattern}, actual_value=text[:120], expected_value=pattern)


def _numeric_compare(facts: dict[str, Any], rule: dict[str, Any], op_name: str, predicate: Callable[[float, float], bool]) -> RuleResult:
    actual_key = rule.get("actual_field")
    required_key = rule.get("required_field")
    value = rule.get("value")  # optional literal compare
    if value is not None:
        actual_v, ok = _try_get(facts, actual_key) if actual_key else (value, True)
        if actual_key and not ok:
            return _result(None, f"missing fact: {actual_key}", missing=[actual_key], trace={"rule": rule})
        actual = _parse_money(actual_v)
        ref = _parse_money(value)
        if actual is None or ref is None:
            return _result(None, "unable to parse numeric values", trace={"rule": rule})
        ok2 = predicate(actual, ref)
        return _result(ok2, f"{actual} {op_name} {ref}", trace={"actual": actual, "required": ref, "operator": op_name}, actual_value=actual, expected_value=ref)
    if not (actual_key and required_key):
        return _result(None, f"{op_name} requires actual_field and required_field", trace={"rule": rule})
    actual_v, ok_a = _try_get(facts, actual_key)
    req_v, ok_b = _try_get(facts, required_key)
    if not (ok_a and ok_b):
        return _result(None, f"missing facts: {[k for k, ok in zip([actual_key, required_key], [ok_a, ok_b]) if not ok]}", trace={"rule": rule}, missing=[k for k, ok in zip([actual_key, required_key], [ok_a, ok_b]) if not ok])
    actual = _parse_money(actual_v)
    required = _parse_money(req_v)
    if actual is None or required is None:
        return _result(None, "unable to parse numeric values", trace={"rule": rule})
    ok2 = predicate(actual, required)
    return _result(ok2, f"{actual} {op_name} {required}", trace={"actual": actual, "required": required, "operator": op_name}, actual_value=actual, expected_value=required)


def op_numeric_gt(facts, rule): return _numeric_compare(facts, rule, ">", lambda a, b: a > b)
def op_numeric_gte(facts, rule): return _numeric_compare(facts, rule, ">=", lambda a, b: a >= b)
def op_numeric_lt(facts, rule): return _numeric_compare(facts, rule, "<", lambda a, b: a < b)
def op_numeric_lte(facts, rule): return _numeric_compare(facts, rule, "<=", lambda a, b: a <= b)


def _date_compare(facts: dict[str, Any], rule: dict[str, Any], op_name: str, predicate: Callable[[str, str], bool]) -> RuleResult:
    actual_key = rule.get("actual_field")
    required_key = rule.get("required_field")
    if not (actual_key and required_key):
        return _result(None, f"{op_name} requires actual_field and required_field", trace={"rule": rule})
    actual_v, ok_a = _try_get(facts, actual_key)
    req_v, ok_b = _try_get(facts, required_key)
    if not (ok_a and ok_b):
        return _result(None, f"missing facts: {[k for k, ok in zip([actual_key, required_key], [ok_a, ok_b]) if not ok]}", trace={"rule": rule}, missing=[k for k, ok in zip([actual_key, required_key], [ok_a, ok_b]) if not ok])
    actual = _parse_date(actual_v)
    required = _parse_date(req_v)
    if not actual or not required:
        return _result(None, "unable to parse dates", trace={"rule": rule})
    ok2 = predicate(actual, required)
    return _result(ok2, f"{actual} {op_name} {required}", trace={"actual": actual, "required": required, "operator": op_name}, actual_value=actual, expected_value=required)


def op_date_before(facts, rule): return _date_compare(facts, rule, "<", lambda a, b: a < b)
def op_date_after(facts, rule): return _date_compare(facts, rule, ">", lambda a, b: a > b)


def op_same_value(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    fields = rule.get("fields", [])
    if not (isinstance(fields, list) and len(fields) >= 2):
        return _result(None, "same_value requires >=2 fields", trace={"rule": rule})
    vals: list[Any] = []
    missing: list[str] = []
    for f in fields:
        v, ok = _try_get(facts, f)
        if not ok:
            missing.append(f)
        vals.append(v)
    if missing:
        return _result(None, f"missing facts: {missing}", missing=missing, trace={"rule": rule})
    norm = [_norm_text(v) for v in vals]
    if len({n for n in norm if n}) == 1:
        return _result(True, "all fields identical", trace={"fields": fields, "values": vals})
    return _result(False, "fields differ", trace={"fields": fields, "values": vals})


def op_same_model_same_price(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    """Spec §九: same model must have unique price.

    If a model appears with more than one distinct unit_price, FAIL — do NOT
    downgrade to REVIEW_REQUIRED, even if the rule caller would have otherwise.

    If unit_price is missing but qty is present (e.g. vertical 分项报价表
    where PDF extraction lost the unit price), compare qty instead.
    """

    rows_key = rule.get("rows", "bid.price_rows")
    key_col = rule.get("key", "model")
    val_col = rule.get("value", "unit_price")
    qty_col = rule.get("qty_col", "qty")
    rows, ok = _try_get(facts, rows_key)
    if not ok or not isinstance(rows, list):
        return _result(None, f"rows missing: {rows_key}", missing=[rows_key])
    by_key: dict[str, list[dict[str, Any]]] = {}
    have_any_unit_price = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        k = normalize_model(row.get(key_col))
        v = _parse_money(row.get(val_col))
        q = _parse_money(row.get(qty_col))
        if v is not None:
            have_any_unit_price = True
        if k:
            by_key.setdefault(k, []).append({"price": v, "qty": q, "row": row})
    if not by_key:
        return _result(None, f"no usable rows in {rows_key}", missing=[rows_key])
    value_field = "unit_price" if have_any_unit_price else "qty"
    conflicts: list[dict[str, Any]] = []
    for k, entries in by_key.items():
        if have_any_unit_price:
            uniq = sorted({e["price"] for e in entries if e["price"] is not None})
        else:
            uniq = sorted({e["qty"] for e in entries if e["qty"] is not None})
        if len(uniq) > 1:
            conflicts.append({
                "normalized_model": k,
                "compared_by": value_field,
                "values": uniq,
                "rows": [
                    {
                        "page": e["row"].get("page"),
                        "unit_price": e["row"].get(val_col),
                        "qty": e["row"].get(qty_col),
                    }
                    for e in entries
                ],
            })
    trace = {
        "rule": "same_model_same_price",
        "rows_examined": sum(len(v) for v in by_key.values()),
        "models": list(by_key.keys()),
        "compared_by": value_field,
        "conflicts": conflicts,
    }
    if conflicts:
        return _result(
            False,
            f"{len(conflicts)} model(s) have conflicting {value_field}",
            trace=trace,
            actual_value=conflicts,
            expected_value=f"unique {value_field} per model",
        )
    return _result(True, "all models consistent", trace=trace)


def op_sum_equals(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    """Spec §十: compute qty*price per row, sum to total, compare declared total.

    Trace includes formula + computed values for audit.
    """

    rows_key = rule.get("rows", "bid.price_rows")
    total_field = rule.get("total_field", "bid.total_price")
    subtotal_field = rule.get("subtotal_field", "subtotal")
    qty_field = rule.get("qty_field", "qty")
    price_field = rule.get("price_field", "unit_price")
    rows, ok = _try_get(facts, rows_key)
    if not ok or not isinstance(rows, list):
        return _result(None, f"rows missing: {rows_key}", missing=[rows_key])
    declared_total, total_ok = _try_get(facts, total_field)
    calculations: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    computed_total = 0.0
    any_computable = False
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        qty = _parse_money(row.get(qty_field))
        price = _parse_money(row.get(price_field))
        declared_sub = _parse_money(row.get(subtotal_field))
        if qty is None or price is None:
            issues.append({"row": i, "reason": "qty/price unparseable", "row_raw": row})
            continue
        any_computable = True
        computed_sub = qty * price
        calculations.append({
            "row": i,
            "formula": f"{qty} × {price} = {computed_sub}",
            "qty": qty,
            "unit_price": price,
            "actual_subtotal": computed_sub,
            "declared_subtotal": declared_sub,
            "subtotal_match": declared_sub is None or abs(declared_sub - computed_sub) <= 0.5,
        })
        if declared_sub is not None and abs(declared_sub - computed_sub) > 0.5:
            issues.append({"row": i, "reason": "subtotal mismatch", "declared": declared_sub, "computed": computed_sub})
        computed_total += computed_sub
    if not any_computable:
        return _result(None, "table extraction failed: no row had both qty and price",
                      trace={"rule": "sum_equals"}, missing=[rows_key])
    declared_num = _parse_money(declared_total) if total_ok else None
    total_match = declared_num is None or abs(declared_num - computed_total) <= 0.5
    if total_ok and declared_num is not None and not total_match:
        issues.append({"row": "TOTAL", "reason": "total mismatch", "declared": declared_num, "computed": computed_total})
    trace = {
        "rule": "sum_equals",
        "calculations": calculations,
        "computed_total": computed_total,
        "declared_total": declared_num,
        "total_match": total_match,
        "issues": issues,
    }
    if issues:
        return _result(False, f"{len(issues)} calculation issue(s)", trace=trace, actual_value=computed_total, expected_value=declared_num)
    return _result(True, "totals reconcile", trace=trace, actual_value=computed_total, expected_value=declared_num)


def op_count_gte(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    rows_key = rule.get("rows", "bid.experiences")
    threshold = rule.get("count_min") or rule.get("value")
    rows, ok = _try_get(facts, rows_key)
    if not ok or not isinstance(rows, list):
        return _result(None, f"rows missing: {rows_key}", missing=[rows_key])
    count = len(rows)
    if count == 0:
        # Empty rows is INSUFFICIENT_EVIDENCE, not a FAIL.
        return _result(None, "rows empty", trace={"count": 0, "threshold": threshold}, missing=[rows_key])
    if threshold is None:
        return _result(True, f"count={count}", trace={"count": count})
    passed = count >= int(threshold)
    return _result(passed, f"count={count} >= {threshold}", trace={"count": count, "threshold": threshold}, actual_value=count, expected_value=int(threshold))


def op_required(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    field = rule.get("field")
    if not field:
        return _result(None, "required requires field", trace={"rule": rule})
    v, ok = _try_get(facts, field)
    if not ok:
        return _result(False, f"required fact missing: {field}", missing=[field], trace={"rule": rule})
    empty = v is None or (isinstance(v, (str, list, dict)) and len(v) == 0)
    return _result(not empty, f"{field} {'present' if not empty else 'empty'}", trace={"field": field}, expected_value="non-empty")


def op_exists(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    target = rule.get("target")
    if not target:
        return _result(None, "exists requires target", trace={"rule": rule})
    v, ok = _try_get(facts, target)
    if not ok:
        return _result(False, f"target missing: {target}", missing=[target], trace={"rule": rule})
    if isinstance(v, (list, dict, str)) and len(v) == 0:
        return _result(False, "target empty", trace={"rule": rule})
    return _result(True, f"target present: {target}", trace={"rule": rule}, actual_value=len(v) if hasattr(v, "__len__") else v)


# ---------------------------------------------------------------------------
# Legacy operators (kept for back-compat with old config/checklists.json)
# ---------------------------------------------------------------------------


def op_equal(facts, rule): return op_equals(facts, rule)
def op_gte(facts, rule): return op_numeric_gte(facts, rule)
def op_lte(facts, rule): return op_numeric_lte(facts, rule)


def op_same_value_by_key(facts, rule): return op_same_model_same_price(facts, rule)


def op_recalculate_totals(facts, rule): return op_sum_equals(facts, rule)


def op_field_consistency(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    pairs = rule.get("pairs")
    fields = rule.get("fields")
    if isinstance(pairs, list) and pairs:
        pair_results: list[dict[str, Any]] = []
        any_missing = False
        any_conflict = False
        for pair in pairs:
            if not (isinstance(pair, list) and len(pair) == 2):
                continue
            a, ok_a = _try_get(facts, pair[0])
            b, ok_b = _try_get(facts, pair[1])
            if not (ok_a and ok_b) or not _norm_text(a) or not _norm_text(b):
                any_missing = True
                pair_results.append({"pair": pair, "ok": False, "reason": "missing or empty"})
                continue
            n_a, n_b = _norm_text(a), _norm_text(b)
            if n_a == n_b:
                pair_results.append({"pair": pair, "ok": True, "values": [a, b]})
            else:
                pair_results.append({"pair": pair, "ok": False, "values": [a, b]})
                any_conflict = True
        if any_missing:
            return _result(None, "some fields missing or empty", trace={"pairs": pair_results})
        if any_conflict:
            return _result(False, "pair(s) conflict", trace={"pairs": pair_results})
        return _result(True, "all pairs consistent", trace={"pairs": pair_results})

    if isinstance(fields, list) and len(fields) >= 2:
        missing: list[str] = []
        vals: list[Any] = []
        for f in fields:
            v, ok = _try_get(facts, f)
            if not ok or not _norm_text(v):
                missing.append(f)
            vals.append(v)
        trace = {"fields": fields, "values": vals}
        if missing:
            return _result(None, f"missing facts: {missing}", trace=trace, missing=missing)
        norm = [_norm_text(v) for v in vals]
        distinct = {n for n in norm if n}
        if len(distinct) == 1 and distinct:
            return _result(True, "all fields consistent", trace=trace)
        return _result(False, "fields conflict", trace=trace)

    return _result(None, "field_consistency requires pairs or fields", trace={"rule": rule})


def op_coverage(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    src_key = rule.get("source")
    tgt_key = rule.get("target")
    min_cov = float(rule.get("min_coverage", 1.0))
    if not src_key or not tgt_key:
        return _result(None, "coverage requires source/target", trace={"rule": rule})
    src, ok_a = _try_get(facts, src_key)
    tgt, ok_b = _try_get(facts, tgt_key)
    if not ok_a:
        return _result(None, f"source missing: {src_key}", missing=[src_key])
    src_list = src if isinstance(src, list) else [src]
    tgt_list = tgt if isinstance(tgt, list) else ([tgt] if ok_b else [])
    norm_src = [_norm_text(x) for x in src_list if _norm_text(x)]
    norm_tgt = {_norm_text(x) for x in tgt_list if _norm_text(x)}
    if not norm_src:
        return _result(None, "source empty", trace={"source_key": src_key})
    matched = [s for s in norm_src if s in norm_tgt or any(t and s in t for t in norm_tgt)]
    coverage = len(matched) / max(len(norm_src), 1)
    missing = [s for s in norm_src if s not in matched]
    trace = {
        "rule": "coverage",
        "source_key": src_key,
        "target_key": tgt_key,
        "source_count": len(norm_src),
        "matched": len(matched),
        "coverage": round(coverage, 3),
        "missing": missing[:10],
        "required": norm_src,
        "provided": sorted(norm_tgt),
        "threshold": min_cov,
    }
    if coverage >= min_cov:
        return _result(True, f"coverage={coverage:.2f} >= {min_cov}", trace=trace)
    return _result(False, f"coverage={coverage:.2f} < {min_cov}", trace=trace)


def op_parameter_compare(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    direction = rule.get("direction", "bid_meets_or_exceeds")
    tender_key = rule.get("tender_params", "tender.tech_params")
    bid_key = rule.get("bid_params", "bid.tech_params")
    tender, ok_a = _try_get(facts, tender_key)
    bid, ok_b = _try_get(facts, bid_key)
    if not (ok_a and ok_b):
        return _result(None, "missing parameter rows", missing=[k for k, ok in zip([tender_key, bid_key], [ok_a, ok_b]) if not ok])
    tender_rows = tender if isinstance(tender, list) else [tender]
    bid_rows = bid if isinstance(bid, list) else [bid]
    bid_map = {_norm_text(r.get("name") if isinstance(r, dict) else r): r for r in bid_rows if r}
    failures: list[dict[str, Any]] = []
    for t in tender_rows:
        if not isinstance(t, dict):
            continue
        name = _norm_text(t.get("name"))
        if not name:
            continue
        b = bid_map.get(name)
        if not b:
            failures.append({"param": t.get("name"), "reason": "no bid parameter"})
            continue
        t_val = t.get("value")
        b_val = (b.get("value") if isinstance(b, dict) else None)
        t_num = _parse_money(t_val)
        b_num = _parse_money(b_val)
        if t_num is not None and b_num is not None:
            if direction == "bid_meets_or_exceeds" and b_num < t_num:
                failures.append({"param": t.get("name"), "tender": t_val, "bid": b_val})
        else:
            if str(t_val).strip() and str(b_val).strip() and str(t_val) != str(b_val):
                if any(neg in str(b_val) for neg in ["无", "不", "否", "缺少"]):
                    failures.append({"param": t.get("name"), "tender": t_val, "bid": b_val})
    if failures:
        return _result(False, f"{len(failures)} parameter(s) below tender", trace={"failures": failures})
    return _result(True, "all parameters satisfied", trace={"checked": len(tender_rows)})


def op_count_and_date_window(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    rows_key = rule.get("rows", "bid.experiences")
    count_min = rule.get("count_min")
    rows, ok = _try_get(facts, rows_key)
    if not ok or not isinstance(rows, list):
        return _result(None, f"experiences missing: {rows_key}", missing=[rows_key])
    valid = 0
    for r in rows:
        if isinstance(r, dict):
            valid += 1
    if valid == 0:
        return _result(False, "no valid experiences found")
    if count_min and valid < int(count_min):
        return _result(False, f"only {valid}/{count_min} valid experiences")
    return _result(True, f"{valid} valid experiences", trace={"valid": valid})


def op_evidence_presence(facts: dict[str, Any], rule: dict[str, Any]) -> RuleResult:
    return op_exists(facts, rule)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


OPERATORS: dict[str, Callable[[dict[str, Any], dict[str, Any]], RuleResult]] = {
    # spec §5 names
    "equals": op_equals,
    "not_equals": op_not_equals,
    "contains": op_contains,
    "not_contains": op_not_contains,
    "regex": op_regex,
    "numeric_gt": op_numeric_gt,
    "numeric_gte": op_numeric_gte,
    "numeric_lt": op_numeric_lt,
    "numeric_lte": op_numeric_lte,
    "date_before": op_date_before,
    "date_after": op_date_after,
    "same_value": op_same_value,
    "same_model_same_price": op_same_model_same_price,
    "sum_equals": op_sum_equals,
    "count_gte": op_count_gte,
    "required": op_required,
    "exists": op_exists,
    # legacy aliases
    "equal": op_equal,
    "gte": op_gte,
    "lte": op_lte,
    "same_value_by_key": op_same_value_by_key,
    "recalculate_totals": op_recalculate_totals,
    "field_consistency": op_field_consistency,
    "coverage": op_coverage,
    "parameter_compare": op_parameter_compare,
    "count_and_date_window": op_count_and_date_window,
    "evidence_presence": op_evidence_presence,
}


def run_rule(rule: dict[str, Any] | None, facts: dict[str, Any]) -> RuleResult:
    if not rule:
        return RuleResult(None, "no rule defined", trace={"rule": None})
    op = rule.get("operator")
    fn = OPERATORS.get(op or "")
    if not fn:
        return RuleResult(None, f"unknown operator: {op}", trace={"rule": rule})
    return fn(facts, rule)