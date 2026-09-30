"""Evaluate a small synthetic development set, not real-customer accuracy."""

import argparse
import json
from pathlib import Path

from src.diagnose import diagnose

ROOT = Path(__file__).resolve().parents[1]


def evaluate(cases: list[dict], mode: str = "local") -> dict:
    tp = fp = fn = exact = goals_correct = evidence_count = evidence_valid = failures = 0
    details = []
    for case in cases:
        try:
            if mode == "llm":
                from src.llm import diagnose_with_llm

                report = diagnose_with_llm(case["text"], case["id"])
            else:
                report = diagnose(case["text"], case["id"])
            predicted = {pain["title"] for pain in report["pain_points"]}
            expected = set(case["pain_points"])
            tp += len(predicted & expected)
            fp += len(predicted - expected)
            fn += len(expected - predicted)
            exact += predicted == expected
            goals_correct += bool(report["facts"]["goals"]) == case["has_goals"]
            for items in list(report["facts"].values()) + [report["pain_points"]]:
                for item in items:
                    for evidence in item["evidence"]:
                        evidence_count += 1
                        evidence_valid += evidence["quote"] in case["text"]
            details.append(
                {
                    "id": case["id"],
                    "expected": sorted(expected),
                    "predicted": sorted(predicted),
                    "exact": predicted == expected,
                }
            )
        except (ValueError, RuntimeError):
            failures += 1
            fn += len(case["pain_points"])
            details.append({"id": case["id"], "failed": True})
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "mode": mode,
        "set": "synthetic-development-v1",
        "case_count": len(cases),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "pain_precision": precision,
        "pain_recall": recall,
        "pain_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "pain_exact_match": exact / len(cases),
        "goal_presence_accuracy": goals_correct / len(cases),
        "evidence_trace_rate": evidence_valid / evidence_count if evidence_count else 0.0,
        "failures": failures,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--mode", choices=["local", "llm"], default="local")
    parser.add_argument("--allow-paid-api", action="store_true")
    args = parser.parse_args()
    if args.mode == "llm":
        parser.error(
            "LLM 开放式痛点标题尚无稳定类别映射，不能直接与规则类别计算准确率；请先建立人工标注映射。当前不执行付费评估。"
        )
    cases = json.loads((ROOT / "data/evaluation_cases.json").read_text(encoding="utf-8"))
    result = evaluate(cases, args.mode)
    output = ROOT / "docs" / f"evaluation-{args.mode}.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "details"}, ensure_ascii=False, indent=2
        )
    )
    if args.check and (result["pain_f1"] < 0.8 or result["pain_exact_match"] < 0.75 or result["failures"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
