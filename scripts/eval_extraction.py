"""Evaluate the real extraction client against eval/golden_set.json.

Usage: ./.venv/bin/python -m scripts.eval_extraction
Requires OPENAI_KEY (or OPENAI_API_KEY) configured; calls the real provider.
"""

import argparse
import json
import sys
from pathlib import Path

from app.llm_client import ExtractedAttribute, OpenAILLMClient

GOLDEN_SET_PATH = Path(__file__).resolve().parent.parent / "eval" / "golden_set.json"


def load_records() -> list[dict]:
    return json.loads(GOLDEN_SET_PATH.read_text())


def score_record(record: dict, extracted: list[ExtractedAttribute]) -> dict:
    expected_kind = record["expected_kind"]
    expected_keywords = [kw.lower() for kw in record["expected_keywords"]]
    expected_restricted = record["expected_restricted"]

    best = None
    best_hits = -1
    for attribute in extracted:
        if attribute["kind"] != expected_kind:
            continue
        text = attribute["text"].lower()
        hits = sum(1 for kw in expected_keywords if kw in text)
        if hits > best_hits:
            best, best_hits = attribute, hits

    kind_ok = best is not None
    keywords_ok = kind_ok and best_hits == len(expected_keywords)
    restricted_ok = kind_ok and best["restricted"] == expected_restricted

    return {
        "message": record["message"],
        "expected_restricted": expected_restricted,
        "passed": kind_ok and keywords_ok and restricted_ok,
        "kind_ok": kind_ok,
        "keywords_ok": keywords_ok,
        "restricted_ok": restricted_ok,
        "extracted": extracted,
    }


def run_eval(records: list[dict] | None = None, client: OpenAILLMClient | None = None) -> list[dict]:
    records = records if records is not None else load_records()
    owns_client = client is None
    client = client or OpenAILLMClient()
    try:
        return [score_record(record, client.extract_attributes(record["message"])) for record in records]
    finally:
        if owns_client:
            client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate extraction against eval/golden_set.json")
    parser.add_argument("--threshold", type=float, default=1.0, help="Minimum pass rate required, 0-1 (default: 1.0)")
    args = parser.parse_args()

    records = load_records()
    results = run_eval(records)
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(
            f"[{status}] {r['message'][:60]!r} "
            f"kind_ok={r['kind_ok']} keywords_ok={r['keywords_ok']} restricted_ok={r['restricted_ok']}"
        )
        if not r["passed"]:
            print(f"       extracted={r['extracted']}")
    rate = passed / total
    print(f"\n{passed}/{total} passed ({rate:.0%})")
    return 0 if rate >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
