"""Streamlit entrypoint for AI 商业需求诊断助手。"""

from __future__ import annotations

import hashlib
import os
import time
from html import escape
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.config import ConfigurationError, env_int, service_name
from src.diagnose import diagnose
from src.ingest import MAX_FILE_BYTES, InputError, read_demo_text, read_uploaded_file, validate_text
from src.llm import (
    LLMConfigurationError,
    LLMOutputError,
    LLMRequestError,
    diagnose_with_llm,
    is_llm_configured,
)
from src.report import render_markdown
from src.security import password_version, verify_password
from src.start import validate_deployment

ROOT = Path(__file__).parent
GAME_DEMO = ROOT / "data" / "demo_game_publisher.md"
BRAND_DEMO = ROOT / "data" / "demo_consumer_brand.xlsx"
load_dotenv(ROOT / ".env")


def _load_brand_demo() -> str:
    interview = read_demo_text(ROOT / "data" / "demo_consumer_brand.md")
    return interview + "\n\n" + read_uploaded_file(BRAND_DEMO.name, BRAND_DEMO.read_bytes())


def _priority_badge(priority: str) -> str:
    css = {"高": "high", "中": "medium", "低": "low", "待确认": "pending"}.get(priority, "pending")
    return f'<span class="priority {css}">{priority}</span>'


def _render_fact_group(title: str, facts: list[dict]) -> None:
    st.markdown(f"#### {title}")
    if not facts:
        st.caption("未识别到，已列入待确认问题。")
        return
    for fact in facts:
        st.markdown(f"**{fact['label']}**")
        for evidence in fact["evidence"]:
            st.caption(f"证据：“{evidence['quote']}”")


st.set_page_config(
    page_title="AI 商业需求诊断助手",
    page_icon="◆",
    layout="wide",
    menu_items={"Get Help": None, "Report a bug": None, "About": None},
)

try:
    validate_deployment()
except ConfigurationError as exc:
    st.error(str(exc))
    st.stop()
if os.getenv("APP_ACCESS_PASSWORD") and st.session_state.get("access_version") != password_version():
    st.title("AI 商业需求诊断助手")
    with st.form("access"):
        st.text_input("访问口令", type="password", key="access_password")
        submitted = st.form_submit_button("进入诊断工作台")
    if submitted:
        if time.monotonic() < st.session_state.get("login_after", 0):
            st.error("请稍候再尝试。")
        elif verify_password(st.session_state.pop("access_password", "")):
            st.session_state["access_version"] = password_version()
            st.rerun()
        else:
            st.session_state.pop("access_password", None)
            st.session_state["login_after"] = time.monotonic() + 3
            st.error("口令不正确。")
    st.stop()
st.markdown(
    """
    <style>
      .block-container {max-width: 1180px; padding-top: 2.2rem; padding-bottom: 3rem;}
      h1 {letter-spacing: -0.6px;}
      .hero {padding: 1.35rem 1.55rem; border: 1px solid #dbe5ef; border-radius: 14px;
             background: linear-gradient(110deg, #f7fbff 0%, #f4f7fc 100%); margin-bottom: 1.3rem;}
      .eyebrow {color:#2e6f9e; font-weight:700; font-size:0.85rem; letter-spacing:0.08em;}
      .muted {color:#5b6876;}
      .priority {display:inline-block; padding:0.12rem 0.52rem; border-radius:999px; font-weight:650; font-size:0.82rem;}
      .high {background:#fbe5e5; color:#a62929;}
      .medium {background:#fff1d6; color:#8a5a00;} .low {background:#e9f2ff; color:#1f5f9b;} .pending {background:#eceff3; color:#53606c;}
      .evidence {padding:0.62rem 0.75rem; background:#f7f9fb; border-left:3px solid #9cb9d4; color:#435160; margin:0.3rem 0 0.65rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">客户需求诊断 · 证据驱动</div>
      <h1 style="margin:0.35rem 0 0.45rem;">AI 商业需求诊断助手</h1>
      <div class="muted">基于原文证据识别业务目标、角色、工具与问题信号，再生成可讨论的优先级与改进建议。</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    if os.getenv("APP_ACCESS_PASSWORD") and st.button("退出并清除当前会话"):
        st.session_state.clear()
        st.rerun()
    st.header("资料来源")
    mode = st.radio(
        "选择一种方式", ["内置演示案例", "粘贴客户资料", "上传文件"], label_visibility="collapsed"
    )
    try:
        model_service = service_name()
    except ConfigurationError:
        model_service = "未正确配置的模型服务"
    st.caption(f"仅使用虚构或已获授权且脱敏的资料。LLM 模式会发送资料至 {model_service}。")
    st.divider()
    st.header("诊断模式")
    analysis_mode = st.radio("选择诊断模式", ["本地规则模式", "LLM 增强模式"], label_visibility="collapsed")
    if model_service == "DeepSeek" and analysis_mode == "LLM 增强模式":
        st.warning(
            "DeepSeek 为实验通道：JSON 模式不强制字段结构；校验失败不会生成报告，已预留额度不退。请优先使用虚构资料试用。"
        )
    if analysis_mode == "本地规则模式":
        st.success("无需 API Key，不向模型服务发送资料。远程部署时资料会到达部署服务器。")
    elif is_llm_configured():
        st.warning("LLM 模式会将本次资料发送至配置的模型服务进行分析。请勿使用机密资料。")
    else:
        st.warning("未检测到本机环境密钥。可继续使用本地规则模式。")
    with st.expander("API Key 配置指南"):
        if os.getenv("DIAGNOSIS_DESKTOP") == "1":
            st.markdown(
                "1. 点击窗口菜单“设置 → 编辑模型配置（保存后重启）”。\n"
                "2. 选择 `LLM_PROVIDER=openai` 或 `deepseek`，填写对应密钥。\n"
                "3. 保存配置，关闭并重新打开客户端，选择 LLM 增强模式并确认外发。"
            )
        else:
            st.markdown(
                "1. 将 `.env.example` 复制为 `.env`。\n2. 选择 `LLM_PROVIDER=openai` 或 `deepseek`，填写对应密钥。\n3. 重启应用，选择 LLM 增强模式并确认外发。"
            )
        st.caption(
            "密钥仅从服务端环境读取，不通过网页输入或显示。配置存在不等于连接已验证；生成时才发起请求。"
        )
    with st.expander("隐私、使用条款与数据处理说明"):
        st.write(f"运营方：{os.getenv('SERVICE_OPERATOR', '本机运行者（未配置公开服务运营方）') or '未配置'}")
        st.write(f"联系方式：{os.getenv('SERVICE_CONTACT', '本机演示，未配置服务联系方式') or '未配置'}")
        for title, filename in [
            ("隐私说明", "privacy.md"),
            ("使用条款", "terms.md"),
            ("数据处理说明", "data-processing.md"),
        ]:
            st.markdown(f"#### {title}")
            st.markdown((ROOT / "docs" / filename).read_text(encoding="utf-8"))
    llm_consent = analysis_mode != "LLM 增强模式" or st.checkbox(
        f"我确认资料已脱敏，并同意本次发送至 {model_service} 进行分析。"
    )

case_name = "自定义资料"
source_text = ""
if mode == "内置演示案例":
    case_name = st.sidebar.selectbox("选择案例", ["游戏发行团队", "消费品牌团队"])
    source_text = read_demo_text(GAME_DEMO) if case_name == "游戏发行团队" else _load_brand_demo()
    st.sidebar.success(f"已载入：{case_name}")
elif mode == "粘贴客户资料":
    source_text = st.text_area(
        "粘贴访谈纪要或业务资料",
        height=300,
        placeholder="例如：市场部和销售部使用不同表格维护经销商信息，活动复盘需要手工汇总……",
    )
else:
    upload = st.file_uploader("上传 .txt、.md、.csv 或 .xlsx 文件", type=["txt", "md", "csv", "xlsx"])
    if upload:
        try:
            if upload.size > MAX_FILE_BYTES:
                raise InputError("文件超过 5 MB，请拆分后上传。")
            source_text = read_uploaded_file(upload.name, upload.getvalue())
            case_name = upload.name
            st.success(f"已读取 {upload.name}")
        except InputError as exc:
            st.error(str(exc))

if source_text.strip():
    try:
        validate_text(source_text)
    except InputError as exc:
        st.error(str(exc))
        source_text = ""

main, preview = st.columns([1.35, 0.65], gap="large")
with main:
    st.subheader("诊断输入")
    if source_text:
        with st.expander("查看已读取资料", expanded=mode == "内置演示案例"):
            st.text(source_text[:7000])
    else:
        st.info("选择演示案例，或提供一份非机密的业务资料后开始诊断。")

    run = st.button(
        "生成结构化诊断报告", type="primary", disabled=not bool(source_text.strip()) or not llm_consent
    )

with preview:
    st.subheader("本次会输出")
    st.markdown("""
    1. 原文识别的目标、角色、工具
    2. 当前痛点及影响/紧迫排序
    3. 每项结论的证据摘录
    4. 协作、知识、流程或数据建议
    5. 下一轮确认问题
    """)
    st.caption("本地模式无需密钥。LLM 模式提供增强分析，但会向已配置的模型服务发送资料。")

input_id = hashlib.sha256(f"{analysis_mode}\n{case_name}\n{source_text}".encode()).hexdigest()
if st.session_state.get("report_input_id") != input_id:
    st.session_state.pop("diagnosis_report", None)

if run:
    st.session_state.pop("diagnosis_report", None)
    report = None
    if analysis_mode == "本地规则模式":
        report = diagnose(source_text, case_name)
        report["analysis_mode"] = "本地规则模式"
    else:
        try:
            limit = env_int("LLM_SESSION_REQUEST_LIMIT", 5, 1, 100)
            if st.session_state.get("llm_attempts", 0) >= limit:
                raise LLMRequestError("本会话模型请求次数已达上限，可继续使用本地模式。")
            st.session_state["llm_attempts"] = st.session_state.get("llm_attempts", 0) + 1
            with st.spinner("正在生成并校验 LLM 结构化诊断……"):
                report = diagnose_with_llm(source_text, case_name)
        except (LLMConfigurationError, ConfigurationError) as exc:
            st.error(str(exc))
        except LLMOutputError as exc:
            st.error(f"LLM 输出未通过校验：{exc}")
            st.info("请重试，或切换至本地规则模式生成可解释的诊断报告。")
        except LLMRequestError as exc:
            st.error(str(exc))

    if report:
        st.session_state["diagnosis_report"] = report
        st.session_state["report_input_id"] = input_id

if st.session_state.get("diagnosis_report"):
    report = st.session_state["diagnosis_report"]
    st.divider()
    st.subheader(f"客户诊断报告｜{report['case_name']}")
    st.caption(f"生成模式：{report['analysis_mode']}")
    if report.get("validation_repairs"):
        st.warning(
            "本次模型输出有一处或多处未通过证据回溯校验，应用已按条处置，"
            "其余结论仍然展示：\n\n- " + "\n- ".join(report["validation_repairs"])
        )
    if report.get("usage"):
        usage = report["usage"]
        cost = (
            f"预估 ${usage['estimated_usd']:.6f}"
            if usage["estimated_usd"] is not None
            else "费用未估算（费率或服务商用量未返回）"
        )
        st.caption(
            f"本次返回的用量：输入 {usage['input_tokens'] if usage['input_tokens'] is not None else '未返回'} / 输出 {usage['output_tokens'] if usage['output_tokens'] is not None else '未返回'} tokens；{cost}。重试费用可能未包含，账单以服务商为准。"
        )
    st.write(report["background"])
    for quote in report.get("background_evidence", []):
        st.markdown(f'<div class="evidence">背景证据：“{escape(quote)}”</div>', unsafe_allow_html=True)
    st.markdown("#### 原文识别结果")
    goal_col, role_col, tool_col, concern_col = st.columns(4)
    with goal_col:
        _render_fact_group("业务目标", report["facts"]["goals"])
    with role_col:
        _render_fact_group("团队角色", report["facts"]["roles"])
    with tool_col:
        _render_fact_group("现有工具", report["facts"]["tools"])
    with concern_col:
        _render_fact_group("客户关注点", report["facts"]["concerns"])

    st.markdown("#### 痛点优先级与解决思路")
    if not report["pain_points"]:
        st.info("资料中没有足以支撑痛点判断的原文证据，因此未生成痛点结论。请查看待确认问题。")
    for index, pain in enumerate(report["pain_points"], start=1):
        with st.container(border=True):
            st.markdown(
                f"**{index}. {escape(pain['title'])}** &nbsp; {_priority_badge(pain['priority'])}",
                unsafe_allow_html=True,
            )
            st.write(f"**影响程度：** {pain['impact']}　 **紧迫程度：** {pain['urgency']}")
            st.write(f"**排序依据：** {pain['rationale']}")
            st.write(f"**建议：** {pain['suggestion']}")
            st.markdown("**证据摘录：**")
            for evidence in pain["evidence"]:
                st.markdown(
                    f'<div class="evidence">“{escape(evidence["quote"])}”</div>', unsafe_allow_html=True
                )

    st.markdown("#### 下一轮沟通需要确认的问题")
    for index, question in enumerate(report["questions"], start=1):
        st.markdown(f"{index}. {question}")

    markdown = render_markdown(report)
    st.download_button(
        "下载 Markdown 诊断报告",
        data=markdown.encode("utf-8"),
        file_name="客户需求诊断报告.md",
        mime="text/markdown",
    )
    st.caption(report["method_note"])
