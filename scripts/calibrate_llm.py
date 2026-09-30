"""Small paid calibration on fictional data; save metrics, never secrets or raw provider errors."""

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.config import LLMSettings, provider_name
from src.ingest import read_demo_text, read_uploaded_file
from src.llm import LLMConfigurationError, LLMOutputError, LLMRequestError, diagnose_with_llm

ROOT = Path(__file__).resolve().parents[1]


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        try:
            self.records.append(json.loads(record.getMessage()))
        except (ValueError, TypeError):
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-paid-api", action="store_true")
    parser.add_argument("--case", choices=["game", "brand", "both"], default="both")
    args = parser.parse_args()
    if not args.allow_paid_api:
        parser.error("真实校准会发送虚构资料并产生费用；请显式传入 --allow-paid-api。")
    load_dotenv(ROOT / ".env")
    settings = LLMSettings.load()
    inputs = {
        "game": read_demo_text(ROOT / "data/demo_game_publisher.md"),
        "brand": read_demo_text(ROOT / "data/demo_consumer_brand.md")
        + "\n\n"
        + read_uploaded_file(
            "demo_consumer_brand.xlsx", (ROOT / "data/demo_consumer_brand.xlsx").read_bytes()
        ),
    }
    capture = Capture()
    logger = logging.getLogger("business_diagnosis")
    logger.addHandler(capture)
    results = []
    try:
        for case in list(inputs) if args.case == "both" else [args.case]:
            capture.records.clear()
            started = time.monotonic()
            text = inputs[case]
            result = {"case": case, "input_chars": len(text)}
            try:
                report = diagnose_with_llm(text, f"fictional-{case}")
                result.update(
                    {
                        "passed": True,
                        "json_and_schema_valid": True,
                        "evidence_valid": True,
                        "pain_count": len(report["pain_points"]),
                        "usage": report["usage"],
                        "model": report["model"],
                    }
                )
            except (LLMConfigurationError, LLMRequestError, LLMOutputError) as exc:
                result.update({"passed": False, "error_type": type(exc).__name__, "error_message": str(exc)})
            result["duration_seconds"] = round(time.monotonic() - started, 3)
            result["events"] = capture.records.copy()
            results.append(result)
    finally:
        logger.removeHandler(capture)
    summary = {
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "provider": provider_name(),
        "max_output_tokens": settings.max_output_tokens,
        "timeout_seconds": settings.timeout,
        "max_retries": settings.retries,
        "sample_count": len(results),
        "passed": sum(item["passed"] for item in results),
        "cases": results,
        "scope": "Two fictional integration samples, not accuracy or reliability certification.",
    }
    destination = ROOT / "docs" / "llm-calibration.json"
    history = []
    if destination.exists():
        previous = json.loads(destination.read_text(encoding="utf-8"))
        history = previous.get("previous_runs", []) + [
            {key: value for key, value in previous.items() if key != "previous_runs"}
        ]
    summary["previous_runs"] = history
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
