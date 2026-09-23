"""Checklist loader for v0.3 (ChecklistItem V3)."""

from __future__ import annotations

import json
from pathlib import Path

from tenderguard.app.schemas import ChecklistItem


def load_checklist(path: str | Path) -> list[ChecklistItem]:
    """Load a checklist JSON file (V3 schema or legacy v0.2 schema)."""

    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "checks" in raw:
        raw = raw["checks"]
    if not isinstance(raw, list):
        raise ValueError("checklist must be a list of items (or a dict with 'checks')")
    return [_coerce(o) for o in raw]


def _coerce(obj: dict) -> ChecklistItem:
    """V3 loader with backward-compat for v0.2 items."""

    if "review_type" in obj:
        return ChecklistItem.model_validate(obj)

    # Legacy v0.2 mapping
    method_map = {
        "DETERMINISTIC": "DETERMINISTIC",
        "SEMANTIC": "SEMANTIC",
        "HYBRID": "HYBRID",
        "HUMAN_REVIEW": "HUMAN_REVIEW",
    }
    return ChecklistItem(
        check_id=obj["check_id"],
        title=obj.get("name") or obj.get("original_requirement") or obj["check_id"],
        source_text=obj.get("original_text") or obj.get("description") or "",
        category=obj.get("category", "未分类"),
        severity=obj.get("severity", "MEDIUM"),
        review_type=obj.get("review_type", "PROCESS_HUMAN"),
        classification_reason=obj.get("classification_reason", "(legacy import)"),
        atomic_requirements=obj.get("atomic_requirements", []),
        required_evidence=obj.get("required_evidence", []) or [],
        rule=obj.get("rule"),
        verification_method=method_map.get(obj.get("verification_method", "DETERMINISTIC"), "DETERMINISTIC"),
        source_sheet=obj.get("source_sheet"),
        source_row=obj.get("source_row"),
        original_requirement=obj.get("original_requirement"),
        notes=obj.get("notes"),
    )