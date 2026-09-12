import json

import pytest

from src.llm import LLMConfigurationError, LLMOutputError, diagnose_with_llm, llm_payload_to_report, parse_and_validate_llm_output


SOURCE = "市场团队希望本月完成渠道验证。当前用 Excel 手工汇总渠道数据，指标口径不同，复盘需要三天。"


def valid_payload() -> dict:
    return {
        "customer_background": {"summary": "市场团队正在推进渠道验证。", "evidence": ["市场团队希望本月完成渠道验证。"]},
        "business_goals": [{"label": "完成渠道验证", "evidence": ["市场团队希望本月完成渠道验证。"]}],
        "team_roles": [{"label": "市场团队", "evidence": ["市场团队希望本月完成渠道验证。"]}],
        "existing_tools": [{"label": "Excel", "evidence": ["当前用 Excel 手工汇总渠道数据，指标口径不同，复盘需要三天。"]}],
        "customer_concerns": [],
        "pain_points": [{"title": "数据口径不一致", "impact": "中", "urgency": "高", "priority": "高", "priority_reason": "每月目标临近且复盘耗时。", "evidence": ["当前用 Excel 手工汇总渠道数据，指标口径不同，复盘需要三天。"], "suggestion": "统一指标定义和数据责任人。"}],
        "questions_to_confirm": ["渠道验证的目标指标和目标值是什么？"],
    }


def test_llm_payload_is_validated_and_normalized() -> None:
    report = llm_payload_to_report(parse_and_validate_llm_output(json.dumps(valid_payload(), ensure_ascii=False), SOURCE), "测试资料")

    assert report["analysis_mode"] == "LLM 增强模式"
    assert report["pain_points"][0]["evidence"][0]["quote"] in SOURCE


def test_non_json_llm_output_is_rejected() -> None:
    with pytest.raises(LLMOutputError, match="不是可解析的 JSON"):
        parse_and_validate_llm_output("这不是 JSON", SOURCE)


def test_evidence_not_in_source_is_rejected() -> None:
    payload = valid_payload()
    payload["pain_points"][0]["evidence"] = ["资料中不存在的内容"]

    with pytest.raises(LLMOutputError, match="无法回溯"):
        parse_and_validate_llm_output(json.dumps(payload, ensure_ascii=False), SOURCE)


def test_llm_mode_requires_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError):
        diagnose_with_llm(SOURCE)

