"""Streamlit entrypoint for AI 商业需求诊断助手。"""

from __future__ import annotations

from pathlib import Path
from html import escape

import streamlit as st
from dotenv import load_dotenv

from src.diagnose import diagnose
from src.ingest import read_demo_text, read_uploaded_file
from src.llm import LLMConfigurationError, LLMOutputError, LLMRequestError, diagnose_with_llm, is_llm_configured
from src.report import render_markdown


ROOT = Path(__file__).parent
GAME_DEMO = ROOT / "data" / "demo_game_publisher.md"
BRAND_DEMO = ROOT / "data" / "demo_consumer_brand.xlsx"
load_dotenv(ROOT / ".env")


def _load_brand_demo() -> str:
    return read_uploaded_file(BRAND_DEMO.name, BRAND_DEMO.read_bytes())


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


st.set_page_config(page_title="AI 商业需求诊断助手", page_icon="◆", layout="wide")
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
      .high {background:#fbe5e5; color:#a62929;} .medium-high {background:#fff1d6; color:#8a5a00;}
      .medium {background:#fff1d6; color:#8a5a00;} .low {background:#e9f2ff; color:#1f5f9b;} .pending {background:#eceff3; color:#53606c;}
      .evidence {padding:0.62rem 0.75rem; background:#f7f9fb; border-left:3px solid #9cb9d4; color:#435160; margin:0.3rem 0 0.65rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">PORTFOLIO MVP · LOCAL + OPTIONAL LLM</div>
      <h1 style="margin:0.35rem 0 0.45rem;">AI 商业需求诊断助手</h1>
      <div class="muted">基于原文证据识别业务目标、角色、工具与问题信号，再生成可讨论的优先级与改进建议。</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("资料来源")
    mode = st.radio("选择一种方式", ["内置演示案例", "粘贴客户资料", "上传文件"], label_visibility="collapsed")
    st.caption("仅使用虚构或已获授权且脱敏的资料。LLM 模式会发送资料至 OpenAI。")
    st.divider()
    st.header("诊断模式")
    analysis_mode = st.radio("选择诊断模式", ["本地规则模式", "LLM 增强模式"], label_visibility="collapsed")
    if analysis_mode == "本地规则模式":
        st.success("无需 API Key，资料不会离开本机。")
    elif is_llm_configured():
        st.warning("LLM 模式会将本次资料发送至配置的模型服务进行分析。请勿使用机密资料。")
    else:
        st.warning("未检测到本机环境密钥。可继续使用本地规则模式。")

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
            source_text = read_uploaded_file(upload.name, upload.getvalue())
            case_name = upload.name
            st.success(f"已读取 {upload.name}")
        except Exception:
            st.error("读取文件失败。请检查文件是否损坏、Excel 是否加密，或将文本/CSV 另存为 UTF-8 后重试。")

main, preview = st.columns([1.35, 0.65], gap="large")
with main:
    st.subheader("诊断输入")
    if source_text:
        with st.expander("查看已读取资料", expanded=mode == "内置演示案例"):
            st.text(source_text[:7000])
    else:
        st.info("选择演示案例，或提供一份非机密的业务资料后开始诊断。")

    run = st.button("生成结构化诊断报告", type="primary", disabled=not bool(source_text.strip()))

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

if run:
    report = None
    if analysis_mode == "本地规则模式":
        report = diagnose(source_text, case_name)
        report["analysis_mode"] = "本地规则模式"
    else:
        try:
            with st.spinner("正在生成并校验 LLM 结构化诊断……"):
                report = diagnose_with_llm(source_text, case_name)
        except LLMConfigurationError as exc:
            st.error(str(exc))
        except LLMOutputError as exc:
            st.error(f"LLM 输出未通过校验：{exc}")
            st.info("请重试，或切换至本地规则模式生成可解释的诊断报告。")
        except LLMRequestError as exc:
            st.error(str(exc))

    if report:
        st.divider()
        st.subheader(f"客户诊断报告｜{report['case_name']}")
        st.caption(f"生成模式：{report['analysis_mode']}")
        st.write(report["background"])
        for quote in report.get("background_evidence", []):
            st.markdown(f"<div class=\"evidence\">背景证据：“{escape(quote)}”</div>", unsafe_allow_html=True)
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
                st.markdown(f"**{index}. {escape(pain['title'])}** &nbsp; {_priority_badge(pain['priority'])}", unsafe_allow_html=True)
                st.write(f"**影响程度：** {pain['impact']}　 **紧迫程度：** {pain['urgency']}")
                st.write(f"**排序依据：** {pain['rationale']}")
                st.write(f"**建议：** {pain['suggestion']}")
                st.markdown("**证据摘录：**")
                for evidence in pain["evidence"]:
                    st.markdown(f"<div class=\"evidence\">“{escape(evidence['quote'])}”</div>", unsafe_allow_html=True)

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
