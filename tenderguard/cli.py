"""CLI entry point: `python -m tenderguard.cli review ...`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tenderguard.app.checklists.excel_parser import parse_to_file
from tenderguard.app.checklists.loader import load_checklist
from tenderguard.app.ingestion.pdf import ingest_pdf
from tenderguard.app.reporting.report import build_report, render_markdown
from tenderguard.app.verification.verifier import verify_all


def _print_progress(msg: str) -> None:
    print(f"[{_now()}] {msg}", flush=True)


def _now() -> str:
    import datetime as _dt
    return _dt.datetime.now().strftime("%H:%M:%S")


def cmd_review(args: argparse.Namespace) -> int:
    # ---- resolve checklist ------------------------------------------------
    checklist_path = Path(args.checklist)
    if not checklist_path.exists() and args.excel:
        # Build normalized checklist from Excel on demand
        _print_progress(f"解析 Excel: {args.excel}")
        n = parse_to_file(args.excel, args.checklist)
        _print_progress(f"已生成 {n} 条 CK: {args.checklist}")

    _print_progress(f"加载 checklist: {checklist_path}")
    items = load_checklist(checklist_path)
    _print_progress(f"共 {len(items)} 条检查项")

    # ---- ingestion -------------------------------------------------------
    _print_progress(f"摄入招标文件: {args.tender}")
    tender_chunks = ingest_pdf(args.tender, doc_id="tender")
    _print_progress(f"  → {len(tender_chunks)} chunks")
    _print_progress(f"摄入投标文件: {args.bid}")
    bid_chunks = ingest_pdf(args.bid, doc_id="bid")
    _print_progress(f"  → {len(bid_chunks)} chunks")
    chunks = tender_chunks + bid_chunks

    # ---- verify -----------------------------------------------------------
    _print_progress("开始验证…")
    results, facts = verify_all(items, chunks)
    summary = {
        "total": len(results),
        "PASS": sum(1 for r in results if r.status.value == "PASS"),
        "FAIL": sum(1 for r in results if r.status.value == "FAIL"),
        "REVIEW_REQUIRED": sum(1 for r in results if r.status.value == "REVIEW_REQUIRED"),
        "NOT_APPLICABLE": sum(1 for r in results if r.status.value == "NOT_APPLICABLE"),
    }
    _print_progress(f"验证完成：PASS={summary['PASS']} FAIL={summary['FAIL']} REVIEW_REQUIRED={summary['REVIEW_REQUIRED']} N/A={summary['NOT_APPLICABLE']}")

    # ---- report -----------------------------------------------------------
    report = build_report(
        items,
        results,
        tender_document=Path(args.tender).name,
        bid_document=Path(args.bid).name,
        project=args.project or "",
        checklist_version=args.version,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    if args.include_facts:
        payload["facts"] = facts
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = out_path.with_suffix(".md")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print("")
    print("=" * 60)
    print(f"[OK] 审核报告已写入: {out_path}")
    print(f"[OK] Markdown 报告:    {md_path}")
    print("-" * 60)
    print(f"  检查项总数:     {summary['total']}")
    print(f"  PASS:           {summary['PASS']}")
    print(f"  FAIL:           {summary['FAIL']}")
    print(f"  REVIEW_REQUIRED:{summary['REVIEW_REQUIRED']}")
    print(f"  NOT_APPLICABLE: {summary['NOT_APPLICABLE']}")
    print(f"  CRITICAL FAIL:  {report.summary['critical_fail']}")
    print(f"  CRITICAL REVIEW:{report.summary['critical_review']}")
    print(f"  HIGH FAIL:      {report.summary['high_fail']}")
    print("-" * 60)
    print("  自动化等级分布:")
    for k, v in report.automation_breakdown.items():
        print(f"    {k:8s} {v}")
    print("=" * 60)
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    n = parse_to_file(args.excel, args.output)
    print(f"[OK] wrote {n} checks to {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tenderguard", description="TenderGuard v0.1 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    rev = sub.add_parser("review", help="Run a tender review")
    rev.add_argument("--tender", required=True, help="Path to tender PDF")
    rev.add_argument("--bid", required=True, help="Path to bid PDF")
    rev.add_argument("--checklist", default="data/normalized/direct_tender_checks.json")
    rev.add_argument("--excel", default="data/source/售前CK.xlsx", help="If --checklist missing, parse this Excel first")
    rev.add_argument("--output", default="output/report.json")
    rev.add_argument("--project", default="")
    rev.add_argument("--version", default="v0.1")
    rev.add_argument("--include-facts", action="store_true")
    rev.set_defaults(func=cmd_review)

    par = sub.add_parser("parse", help="Parse 售前CK.xlsx into normalized JSON")
    par.add_argument("--excel", default="data/source/售前CK.xlsx")
    par.add_argument("--output", default="data/normalized/direct_tender_checks.json")
    par.set_defaults(func=cmd_parse)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())