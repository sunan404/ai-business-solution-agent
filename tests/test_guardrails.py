import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook
from streamlit.testing.v1 import AppTest

from scripts.evaluate import evaluate
from scripts.package_release import release_files
from src.budget import QuotaError, record_usage, reserve_budget
from src.config import ConfigurationError, LLMSettings, env_float, env_int
from src.diagnose import diagnose
from src.ingest import MAX_FILE_BYTES, InputError, read_uploaded_file
from src.llm import DIAGNOSIS_SCHEMA, SYSTEM_INSTRUCTIONS, llm_payload_to_report
from src.priority import priority
from src.security import verify_password
from src.start import validate_deployment

ROOT = Path(__file__).resolve().parents[1]


def test_budget_atomic_across_sessions(monkeypatch):
    settings = replace(LLMSettings.load(), retries=0, daily_requests=3)

    def attempt(_):
        try:
            reserve_budget(100, settings)
            return True
        except QuotaError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(8))) == 3
    with pytest.raises(QuotaError):
        reserve_budget(100, settings)


def test_budget_failure_and_token_money_caps(monkeypatch, tmp_path):
    settings = LLMSettings.load()
    with pytest.raises(QuotaError, match="token"):
        reserve_budget(100, replace(settings, daily_tokens=1))
    with pytest.raises(QuotaError, match="费用"):
        reserve_budget(100, replace(settings, daily_usd=0.001, input_rate=1000, output_rate=1000))
    monkeypatch.setenv("QUOTA_DB_PATH", str(tmp_path))
    with pytest.raises(QuotaError, match="配额存储"):
        reserve_budget(100, settings)


def test_maximum_chinese_request_fits_fresh_default_budget(monkeypatch):
    from src.config import PROMPT_TOKEN_MARGIN

    settings = LLMSettings.load()
    settings.validate_maximum_request()
    bound = (
        len(("中" * 60000 + SYSTEM_INSTRUCTIONS + json.dumps(DIAGNOSIS_SCHEMA)).encode())
        + PROMPT_TOKEN_MARGIN
    )
    reserve_budget(bound, settings)


def test_oversized_single_request_is_not_daily_exhaustion():
    settings = replace(LLMSettings.load(), daily_tokens=1)
    with pytest.raises(QuotaError, match="本次请求预留量超过整日"):
        reserve_budget(100, settings)
    with pytest.raises(ConfigurationError, match="60,000"):
        settings.validate_maximum_request()


def test_tenant_limits_and_returned_usage_are_isolated(monkeypatch):
    import os
    import sqlite3

    settings = replace(LLMSettings.load(), retries=0, tenant_requests=1, tenant_id="trial_a")
    reserve_budget(100, settings)
    with pytest.raises(QuotaError, match="客户标识"):
        reserve_budget(100, settings)
    second = replace(settings, tenant_id="trial_b")
    reserve_budget(100, second)
    assert record_usage(settings, 100, 50, 0.01)
    assert record_usage(second, 200, 70, 0.02)
    from contextlib import closing

    with closing(sqlite3.connect(os.environ["QUOTA_DB_PATH"])) as db:
        rows = db.execute("SELECT tenant_id,input_tokens FROM usage_daily ORDER BY tenant_id").fetchall()
    assert rows == [("trial_a", 100), ("trial_b", 200)]


def test_deployment_fails_closed_and_password(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ConfigurationError, match="12 位"):
        validate_deployment()
    monkeypatch.setenv("APP_ACCESS_PASSWORD", "test-access-placeholder")
    assert verify_password("test-access-placeholder")
    assert not verify_password("incorrect")
    with pytest.raises(ConfigurationError, match="SERVICE_OPERATOR"):
        validate_deployment()
    monkeypatch.setenv("SERVICE_OPERATOR", "虚构试点运营者")
    monkeypatch.setenv("SERVICE_CONTACT", "测试联系人")
    validate_deployment()


def test_access_gate_hides_inputs_until_authenticated(monkeypatch):
    monkeypatch.setenv("APP_ACCESS_PASSWORD", "test-access-placeholder")
    app = AppTest.from_file(str(ROOT / "app.py")).run()
    assert not app.get("file_uploader")
    app.text_input[0].set_value("incorrect")
    app.button[0].click().run()
    assert app.error
    app.session_state["login_after"] = 0
    app.text_input[0].set_value("test-access-placeholder")
    app.button[0].click().run()
    assert not app.exception
    assert app.radio


@pytest.mark.parametrize("value", ["nan", "inf", "-1", "not-a-number"])
def test_invalid_config_rejected(monkeypatch, value):
    monkeypatch.setenv("TEST_RATE", value)
    with pytest.raises(ConfigurationError):
        env_float("TEST_RATE", 0, 0, 1000)


def test_config_limits_and_cost_rate_requirements(monkeypatch):
    monkeypatch.setenv("TEST_INT", "no")
    with pytest.raises(ConfigurationError):
        env_int("TEST_INT", 1, 1, 10)
    monkeypatch.setenv("TEST_INT", "11")
    with pytest.raises(ConfigurationError):
        env_int("TEST_INT", 1, 1, 10)
    monkeypatch.setenv("LLM_DAILY_USD_BUDGET", "1")
    with pytest.raises(ConfigurationError, match="费率"):
        LLMSettings.load()


def test_file_limits_and_encodings():
    assert "市场团队" in read_uploaded_file("case.csv", "团队,问题\n市场团队,手工汇总".encode("gb18030"))
    with pytest.raises(InputError, match="5 MB"):
        read_uploaded_file("large.txt", b"a" * (MAX_FILE_BYTES + 1))
    with pytest.raises(InputError, match="60,000"):
        read_uploaded_file("long.txt", b"a" * 60001)
    with pytest.raises(InputError, match="为空"):
        read_uploaded_file("empty.txt", b"")
    with pytest.raises(InputError, match="行列数"):
        read_uploaded_file("bad.csv", b"a,b\n1,2,3")
    with pytest.raises(InputError, match="1,000"):
        read_uploaded_file("long.csv", b"a\n" + b"x\n" * 1001)


def test_zip_bomb_and_external_links_rejected():
    for member, data, message in [
        ("xl/workbook.xml", b"a" * 100000, "压缩比"),
        ("xl/externalLinks/link.xml", b"link", "外部"),
    ]:
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            archive.writestr(member, data)
        with pytest.raises(InputError, match=message):
            read_uploaded_file("bad.xlsx", buffer.getvalue())


def test_workbook_bounds_and_merged_titles():
    text = read_uploaded_file("demo.xlsx", (ROOT / "data/demo_consumer_brand.xlsx").read_bytes())
    assert "Unnamed:" not in text and "虚构" in text and "原始访谈摘录" in text
    workbook = Workbook()
    workbook.active.cell(1001, 1, "over-limit")
    buffer = BytesIO()
    workbook.save(buffer)
    with pytest.raises(InputError, match="1,000"):
        read_uploaded_file("big.xlsx", buffer.getvalue())


def test_rule_negation_and_unknown_priority():
    assert not diagnose("目前没有延期，审批正常，最新版本的规范已归档。")["pain_points"]
    report = diagnose("当前找不到文档，业务影响与时限尚未确认。")
    assert report["pain_points"][0]["priority"] == "待确认"
    assert priority("高", "中") == (8, "高")


def test_llm_sort_uses_shared_priority():
    background = {"summary": "客户背景待确认", "evidence": []}
    pain = {
        "title": "问题",
        "impact": "中",
        "urgency": "低",
        "priority": "高",
        "priority_reason": "模型理由",
        "evidence": ["证据"],
        "suggestion": "建议",
    }
    payload = {
        "customer_background": background,
        "business_goals": [],
        "team_roles": [],
        "existing_tools": [],
        "customer_concerns": [],
        "questions_to_confirm": ["背景？"],
        "pain_points": [pain, {**pain, "title": "更高", "impact": "高", "urgency": "高"}],
    }
    result = llm_payload_to_report(payload, "测试")
    assert [item["priority_score"] for item in result["pain_points"]] == [9, 5]
    assert result["pain_points"][1]["priority"] == "中"


def test_synthetic_baseline_and_clean_bundle():
    cases = json.loads((ROOT / "data/evaluation_cases.json").read_text(encoding="utf-8"))
    result = evaluate(cases)
    assert len(cases) == 25 and result["pain_f1"] >= 0.8
    assert result["evidence_trace_rate"] == 1
    paths = [path.relative_to(ROOT).as_posix() for path in release_files(ROOT)]
    assert ".env.example" in paths and "Dockerfile" in paths
    assert not any(
        path.startswith((".agents/", ".venv/", "node_modules/", "runtime/")) or path == ".env"
        for path in paths
    )


def test_llm_consent_and_session_cap(monkeypatch):
    import src.llm

    called = []

    def fake_llm(text, case_name):
        called.append(text)
        report = diagnose(text, case_name)
        report["analysis_mode"] = "LLM 增强模式"
        return report

    monkeypatch.setattr(src.llm, "diagnose_with_llm", fake_llm)
    monkeypatch.setenv("LLM_SESSION_REQUEST_LIMIT", "1")
    app = AppTest.from_file(str(ROOT / "app.py")).run()
    app.radio[1].set_value("LLM 增强模式").run()
    assert app.button[0].disabled
    app.checkbox[0].check().run()
    app.button[0].click().run()
    assert not app.exception and len(called) == 1
    app.button[0].click().run()
    assert len(called) == 1 and any("上限" in error.value for error in app.error)


def test_page_discloses_dropped_evidence_and_markdown_keeps_it(monkeypatch):
    """报告被按条处置时，页面与下载内容都必须披露，不能静默少内容。"""
    import src.llm
    from src.report import render_markdown

    repairs = ["team_roles「市场、设计、门店」：无可用证据，整条移除"]

    def fake_llm(text, case_name):
        report = diagnose(text, case_name)
        report["analysis_mode"] = "LLM 增强模式"
        report["validation_repairs"] = repairs
        report["method_note"] += " 本次校验处置：" + "；".join(repairs) + "。被移除的内容未出现在报告中。"
        return report

    monkeypatch.setattr(src.llm, "diagnose_with_llm", fake_llm)
    app = AppTest.from_file(str(ROOT / "app.py")).run()
    app.radio[1].set_value("LLM 增强模式").run()
    app.checkbox[0].check().run()
    app.button[0].click().run()

    assert not app.exception
    assert any("未通过证据回溯校验" in warning.value for warning in app.warning)
    markdown = render_markdown(app.session_state["diagnosis_report"])
    assert "本次校验处置" in markdown
