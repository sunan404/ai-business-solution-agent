import json

import pytest

from src.llm import (
    LLMConfigurationError,
    LLMOutputError,
    LLMRequestError,
    diagnose_with_llm,
    llm_payload_to_report,
    parse_and_validate_llm_output,
)

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
    report = llm_payload_to_report(
        parse_and_validate_llm_output(json.dumps(valid_payload(), ensure_ascii=False), SOURCE), "测试资料"
    )

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
    monkeypatch.setattr(openai, "OpenAI", Client)
    report = diagnose_with_llm(SOURCE)
    assert report["provider"] == "deepseek"
    assert report["usage"]["input_tokens"] == 100
    assert captured["base_url"] == "https://api.deepseek.com"
    assert captured["request"]["response_format"] == {"type": "json_object"}
    assert captured["request"]["max_tokens"] == 6000


def test_deepseek_does_not_use_openai_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder-not-a-credential")
    with pytest.raises(LLMConfigurationError, match="API Key"):
        diagnose_with_llm(SOURCE)


def test_evidence_not_in_source_is_rejected() -> None:
    payload = valid_payload()
    payload["pain_points"][0]["evidence"] = ["资料中不存在的内容"]

    with pytest.raises(LLMOutputError, match="无法回溯"):
        parse_and_validate_llm_output(json.dumps(payload, ensure_ascii=False), SOURCE)


def test_llm_mode_requires_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError):
        diagnose_with_llm(SOURCE)


def test_unknown_background_requires_questions():
    payload = valid_payload()
    payload["customer_background"] = {"summary": "客户背景待确认", "evidence": []}
    assert parse_and_validate_llm_output(json.dumps(payload), SOURCE)
    payload["questions_to_confirm"] = []
    with pytest.raises(LLMOutputError, match="必须提供"):
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
