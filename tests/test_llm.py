import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ingest import read_demo_text
from src.llm import (
    LLMConfigurationError,
    LLMOutputError,
    LLMRequestError,
    diagnose_with_llm,
    llm_payload_to_report,
    parse_and_validate_llm_output,
    validate_llm_payload,
)

ROOT = Path(__file__).resolve().parents[1]

SOURCE = "市场团队希望本月完成渠道验证。当前用 Excel 手工汇总渠道数据，指标口径不同，复盘需要三天。"


def valid_payload() -> dict:
    return {
        "customer_background": {
            "summary": "市场团队正在推进渠道验证。",
            "evidence": ["市场团队希望本月完成渠道验证。"],
        },
        "business_goals": [{"label": "完成渠道验证", "evidence": ["市场团队希望本月完成渠道验证。"]}],
        "team_roles": [{"label": "市场团队", "evidence": ["市场团队希望本月完成渠道验证。"]}],
        "existing_tools": [
            {"label": "Excel", "evidence": ["当前用 Excel 手工汇总渠道数据，指标口径不同，复盘需要三天。"]}
        ],
        "customer_concerns": [],
        "pain_points": [
            {
                "title": "数据口径不一致",
                "impact": "中",
                "urgency": "高",
                "priority": "高",
                "priority_reason": "每月目标临近且复盘耗时。",
                "evidence": ["当前用 Excel 手工汇总渠道数据，指标口径不同，复盘需要三天。"],
                "suggestion": "统一指标定义和数据责任人。",
            }
        ],
        "questions_to_confirm": ["渠道验证的目标指标和目标值是什么？"],
    }


def test_llm_payload_is_validated_and_normalized() -> None:
    validated, repairs = parse_and_validate_llm_output(
        json.dumps(valid_payload(), ensure_ascii=False), SOURCE
    )
    report = llm_payload_to_report(validated, "测试资料", repairs)

    assert repairs == [], "合法输出不应产生处置记录"
    assert report["analysis_mode"] == "LLM 增强模式"
    assert report["pain_points"][0]["evidence"][0]["quote"] in SOURCE


def test_non_json_llm_output_is_rejected() -> None:
    with pytest.raises(LLMOutputError, match="不是可解析的 JSON"):
        parse_and_validate_llm_output("这不是 JSON", SOURCE)


def test_deepseek_chat_uses_own_key_and_validates_output(monkeypatch):
    from types import SimpleNamespace

    import openai

    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = SimpleNamespace(completions=self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop", message=SimpleNamespace(content=json.dumps(valid_payload()))
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=200),
            )

    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-placeholder-not-a-credential")
    monkeypatch.setenv("LLM_MODEL", "test-selected-model")
    monkeypatch.setattr(openai, "OpenAI", Client)
    report = diagnose_with_llm(SOURCE)
    assert report["provider"] == "deepseek"
    assert report["usage"]["input_tokens"] == 100
    assert captured["base_url"] == "https://api.deepseek.com"
    assert captured["request"]["response_format"] == {"type": "json_object"}
    assert captured["request"]["max_tokens"] == 6000
    assert captured["request"]["model"] == "test-selected-model"


def test_deepseek_does_not_use_openai_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-not-a-credential")
    with pytest.raises(LLMConfigurationError, match="API Key"):
        diagnose_with_llm(SOURCE)


def test_untraceable_evidence_is_dropped_not_fatal() -> None:
    """改写单条证据不再作废整份报告：只丢弃该条并记录处置说明。"""
    payload = valid_payload()
    payload["pain_points"][0]["evidence"] = ["资料中不存在的内容"]

    validated, repairs = parse_and_validate_llm_output(json.dumps(payload, ensure_ascii=False), SOURCE)

    assert validated["pain_points"] == [], "唯一证据不可回溯时该痛点应整条移除"
    assert repairs and any("痛点" in note for note in repairs)
    report = llm_payload_to_report(validated, "测试资料", repairs)
    assert report["pain_points"] == []
    assert "本次校验处置" in report["method_note"]
    assert report["validation_repairs"] == repairs


def test_partially_untraceable_evidence_keeps_traceable_quotes() -> None:
    payload = valid_payload()
    good = payload["pain_points"][0]["evidence"][0]
    payload["pain_points"][0]["evidence"] = [good, "资料中不存在的内容"]

    validated, repairs = parse_and_validate_llm_output(json.dumps(payload, ensure_ascii=False), SOURCE)

    assert validated["pain_points"][0]["evidence"] == [good]
    assert any("丢弃 1 条" in note for note in repairs)


def test_cross_line_join_is_not_traceable() -> None:
    """空白归一化不得把两行拼接成"原文"：跨行引用必须被拒绝。"""
    source = "第一行内容结束。\n第二行内容开始。"
    quote = "第一行内容结束。第二行内容开始。"
    payload = valid_payload()
    payload["customer_background"] = {"summary": "背景", "evidence": [quote]}
    payload["business_goals"] = []
    payload["team_roles"] = []
    payload["existing_tools"] = []
    payload["customer_concerns"] = []
    payload["pain_points"] = []

    validated, repairs = parse_and_validate_llm_output(json.dumps(payload, ensure_ascii=False), source)

    assert validated["customer_background"]["evidence"] == []
    assert validated["customer_background"]["summary"] == "客户背景待确认"
    assert any("降级为待确认" in note for note in repairs)


def test_error_messages_separate_missing_and_extra_fields() -> None:
    extra = valid_payload()
    extra["pain_points"][0]["score"] = 9
    with pytest.raises(LLMOutputError, match="多余 score"):
        validate_llm_payload(extra, SOURCE)

    missing = valid_payload()
    missing["pain_points"][0].pop("suggestion")
    with pytest.raises(LLMOutputError, match="缺少 suggestion"):
        validate_llm_payload(missing, SOURCE)

    bad_level = valid_payload()
    bad_level["pain_points"][0]["priority"] = "P0"
    with pytest.raises(LLMOutputError, match="priority="):
        validate_llm_payload(bad_level, SOURCE)


def test_rejected_hook_receives_raw_output_only_on_validation_failure(monkeypatch) -> None:
    """校准用的失败载荷钩子只在校验失败时触发，且不改变生产行为。"""
    import openai

    bad = json.dumps({"unexpected": "shape"}, ensure_ascii=False)
    responses = [bad, json.dumps(valid_payload(), ensure_ascii=False)]
    seen: list[str] = []

    class Client:
        def __init__(self, **kwargs):
            self.responses = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create(self, **kwargs):
            return SimpleNamespace(status="completed", output_text=responses.pop(0), usage=None)

    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-not-a-credential")
    monkeypatch.setattr(openai, "OpenAI", Client)

    with pytest.raises(LLMOutputError):
        diagnose_with_llm(SOURCE, "测试资料", seen.append)
    assert seen == [bad]

    seen.clear()
    assert diagnose_with_llm(SOURCE, "测试资料", seen.append)["analysis_mode"] == "LLM 增强模式"
    assert seen == [], "校验通过时不应触发失败载荷钩子"


def test_repair_path_returns_report_instead_of_raising(monkeypatch) -> None:
    """端到端：单条证据改写不再抛错，报告仍生成并带处置记录。"""
    import openai

    payload = valid_payload()
    payload["team_roles"][0]["evidence"] = ["被改写的角色证据"]
    body = json.dumps(payload, ensure_ascii=False)

    class Client:
        def __init__(self, **kwargs):
            self.responses = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create(self, **kwargs):
            return SimpleNamespace(
                status="completed",
                output_text=body,
                usage=SimpleNamespace(input_tokens=100, output_tokens=50),
            )

    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-not-a-credential")
    monkeypatch.setattr(openai, "OpenAI", Client)

    report = diagnose_with_llm(SOURCE, "测试资料")
    assert report["facts"]["roles"] == []
    assert report["validation_repairs"]
    assert "本次校验处置" in report["method_note"]
    assert report["pain_points"], "其余结论应保留"


def test_rewritten_role_evidence_degrades_instead_of_voiding_report() -> None:
    """复现长案例真实失败：角色证据被改写时，整份报告不再作废。"""
    source = read_demo_text(ROOT / "data" / "demo_consumer_brand.md")
    traceable = (
        "销售团队维护经销商合作状态，市场团队负责活动方案和素材，运营团队汇总活动数据，财务团队审核活动费用。"
    )
    assert traceable in source
    assert "市场、设计、门店团队" not in source, "本用例依赖该改写串在原文中不存在"

    payload = {
        "customer_background": {"summary": "消费品牌渠道经营。", "evidence": [traceable]},
        "business_goals": [],
        "team_roles": [{"label": "市场、设计、门店", "evidence": ["市场、设计、门店团队"]}],
        "existing_tools": [],
        "customer_concerns": [],
        "pain_points": [
            {
                "title": "排期不同步",
                "impact": "高",
                "urgency": "中",
                "priority": "高",
                "priority_reason": "本月大促临近。",
                "evidence": [traceable],
                "suggestion": "统一活动排期表并指定维护人。",
            }
        ],
        "questions_to_confirm": ["试点负责人和验收目标值是什么？"],
    }

    validated, repairs = parse_and_validate_llm_output(json.dumps(payload, ensure_ascii=False), source)
    report = llm_payload_to_report(validated, "消费品牌", repairs)

    assert validated["team_roles"] == [], "不可回溯的角色条目应被移除"
    assert report["facts"]["roles"] == []
    assert report["pain_points"], "其余结论必须保留，而不是整份作废"
    assert report["validation_repairs"]
    assert "本次校验处置" in report["method_note"]


def test_llm_mode_requires_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError):
        diagnose_with_llm(SOURCE)


def test_unknown_background_requires_questions():
    payload = valid_payload()
    payload["customer_background"] = {"summary": "客户背景待确认", "evidence": []}
    assert parse_and_validate_llm_output(json.dumps(payload), SOURCE)[0]
    payload["questions_to_confirm"] = []
    with pytest.raises(LLMOutputError, match="待确认问题"):
        parse_and_validate_llm_output(json.dumps(payload), SOURCE)


def test_mocked_api_request_and_incomplete_response(monkeypatch):
    from types import SimpleNamespace

    import openai

    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.responses = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                status=captured.get("status", "completed"), output_text=json.dumps(valid_payload())
            )

    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-not-a-credential")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "30")
    monkeypatch.setattr(openai, "OpenAI", FakeClient)
    assert diagnose_with_llm(SOURCE)["analysis_mode"] == "LLM 增强模式"
    assert captured["max_retries"] == 1
    assert captured["timeout"] == 30
    assert captured["request"]["store"] is False
    assert captured["request"]["max_output_tokens"] == 6000
    assert captured["request"]["text"]["format"]["strict"] is True
    captured["status"] = "incomplete"
    with pytest.raises(LLMOutputError, match="未完成"):
        diagnose_with_llm(SOURCE)


def test_invalid_timeout_is_configuration_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-not-a-credential")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "nan")
    with pytest.raises(LLMConfigurationError, match="1 到 60"):
        diagnose_with_llm(SOURCE)


@pytest.mark.parametrize(
    "error_kind,expected", [("auth", "验证失败"), ("rate", "额度不足"), ("network", "超时")]
)
def test_api_failures_have_safe_actionable_messages(monkeypatch, error_kind, expected):
    import httpx
    import openai

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(401 if error_kind == "auth" else 429, request=request)
    errors = {
        "auth": openai.AuthenticationError("untrusted-provider-error", response=response, body=None),
        "rate": openai.RateLimitError("untrusted-provider-error", response=response, body=None),
        "network": openai.APIConnectionError(request=request),
    }

    class FailingClient:
        def __init__(self, **kwargs):
            self.responses = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create(self, **kwargs):
            raise errors[error_kind]

    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-not-a-credential")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "60")
    monkeypatch.setattr(openai, "OpenAI", FailingClient)
    with pytest.raises(LLMRequestError, match=expected) as raised:
        diagnose_with_llm(SOURCE)
    assert "untrusted-provider-error" not in str(raised.value)
    assert "test-placeholder" not in str(raised.value)


def test_quota_blocks_before_client_creation(monkeypatch):
    import openai

    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-not-a-credential")
    monkeypatch.setenv("LLM_DAILY_TOKEN_BUDGET", "1")
    called = []
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: called.append(kwargs))
    with pytest.raises(LLMRequestError, match="预算"):
        diagnose_with_llm(SOURCE)
    assert not called


@pytest.mark.parametrize("status,raw", [("completed", ""), ("completed", "not JSON"), ("incomplete", "{}")])
def test_failed_outputs_logged_without_source(monkeypatch, caplog, status, raw):
    from types import SimpleNamespace

    import openai

    class Client:
        def __init__(self, **kwargs):
            self.responses = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create(self, **kwargs):
            return SimpleNamespace(
                status=status, output_text=raw, usage=SimpleNamespace(input_tokens=100, output_tokens=10)
            )

    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-not-a-credential")
    monkeypatch.setattr(openai, "OpenAI", Client)
    with pytest.raises(LLMOutputError):
        diagnose_with_llm(SOURCE)
    assert "output_validation" in caplog.text
    assert SOURCE not in caplog.text
    assert "test-placeholder" not in caplog.text
