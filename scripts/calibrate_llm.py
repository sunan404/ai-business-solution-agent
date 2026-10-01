"""Small paid calibration on fictional data; save metrics, never secrets or raw provider errors."""

import argparse
import hashlib
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


def cumulative_metrics(summary: dict) -> dict:
    """Count every recorded attempt, not only the latest run or successful outputs."""
    cases = [case for run in [*summary.get("previous_runs", []), summary] for case in run["cases"]]
    passed = sum(bool(case["passed"]) for case in cases)
    return {
        "attempts": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "success_rate": passed / len(cases) if cases else None,
        "long_document_attempts": sum(case["input_chars"] >= 20000 for case in cases),
        "long_document_passed": sum(case["input_chars"] >= 20000 and case["passed"] for case in cases),
        "scope": "Integration validation across prompt revisions, not accuracy or production reliability.",
    }


def add_cumulative(summary: dict) -> dict:
    metrics = cumulative_metrics(summary)
    return {
        "all_time_success_rate": f"{metrics['passed']}/{metrics['attempts']}",
        "cumulative": metrics,
        **{k: v for k, v in summary.items() if k not in {"cumulative", "all_time_success_rate"}},
    }


def long_document(base: str, case: str) -> str:
    """Reproducible varied fictional appendices; not copied real client data or repeated padding."""
    text = base + "\n\n## 长文档校准附录（全部虚构，构造的多批次过程记录，不代表客户实绩）\n"
    index = 1
    while len(text) < 22000:
        text += (
            f"\n### {case} 批次 {index:03d}：流程走查与访谈补充\n"
            f"本批次使用虚构项目编号 T{index:03d}，参与者仅记为市场、运营、销售与设计角色，不含姓名或联系方式。"
            f"市场希望在第 {(index % 4) + 1} 周完成该批次验证，先确认目标市场和数据字典，再判断是否扩展范围。"
            "团队继续使用 Excel 台账和共享网盘，不计划本轮替换广告平台。"
            + (
                "当批素材审批的反馈分散在三个群聊，运营不知道哪个版本已批准；负责人称下周必须上线，"
                "若依赖任务没有同步会影响投放排期。设计建议先登记任务负责人、依赖关系和截止时间，"
                "但批准权与异常升级的责任人尚未确认。"
                if index % 3 == 0
                else "本批次素材审批按现有流程完成，没有发现版本混乱，也没有新增延迟；"
                "这只能说明本批记录未见异常，不代表其他批次不存在问题。计划保留批准版本供后续抽查。"
            )
            + (
                "运营从两份 CSV 汇总周报时发现转化口径不同，一个统计注册、另一个统计付费，不能直接相加；"
                "人工核对花费两天。管理者关注数据是否可比较，尚未给出可接受的误差阈值。"
                if index % 2 == 0
                else "本批次数据字典已经双方确认，运营没有发现指标差异。销售对新增合作渠道仍需确认"
                "下一步动作的维护人，但资料未说明是否已经漏跟进，不得据此推断客户流失。"
            )
            + "业务负责人建议先做小范围试点，不自动授权系统修改外部数据。预算、准时交付率的历史基线和"
            "验收目标值仍待下一轮会议确认。该记录只供需求讨论，不承诺收入提升或效率改善幅度。\n"
        )
        index += 1
    return text


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
    parser.add_argument("--case", choices=["game", "brand", "both", "long"], default="both")
    parser.add_argument(
        "--dump-rejected",
        action="store_true",
        help="把校验失败的原始模型输出写到 runtime/rejected/（Git 忽略，仅限虚构样例）",
    )
    parser.add_argument(
        "--summarize-only", action="store_true", help="Refresh cumulative metrics without an API call"
    )
    args = parser.parse_args()
    destination = ROOT / "docs" / "llm-calibration.json"
    if args.summarize_only:
        summary = add_cumulative(json.loads(destination.read_text(encoding="utf-8")))
        destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary["cumulative"]))
        return
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
    if args.case == "long":
        inputs = {f"long-{case}": long_document(text, case) for case, text in inputs.items()}
    capture = Capture()
    logger = logging.getLogger("business_diagnosis")
    logger.addHandler(capture)
    results = []
    try:
        for case in list(inputs) if args.case in {"both", "long"} else [args.case]:
            capture.records.clear()
            started = time.monotonic()
            text = inputs[case]
            result = {
                "case": case,
                "input_chars": len(text),
                "input_sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
            rejected: list[str] = []

            def capture_rejected(raw: str) -> None:
                rejected.append(raw)

            try:
                report = diagnose_with_llm(text, f"fictional-{case}", capture_rejected)
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
                if rejected and args.dump_rejected:
                    # runtime/ 已被 .gitignore 排除：失败载荷只留在本机，供定位原因。
                    dump_dir = ROOT / "runtime" / "rejected"
                    dump_dir.mkdir(parents=True, exist_ok=True)
                    dump = dump_dir / f"{result['input_sha256'][:12]}-{case}.txt"
                    dump.write_text(rejected[-1], encoding="utf-8")
                    result["rejected_dump"] = dump.relative_to(ROOT).as_posix()
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
        "prompt_revision": "schema-enums-v2",
        "scope": "Fictional integration samples, not accuracy or reliability certification.",
    }
    history = []
    if destination.exists():
        previous = json.loads(destination.read_text(encoding="utf-8"))
        history = previous.get("previous_runs", []) + [
            {
                key: value
                for key, value in previous.items()
                if key not in {"previous_runs", "all_time_success_rate", "cumulative"}
            }
        ]
    summary["previous_runs"] = history
    summary = add_cumulative(summary)
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
