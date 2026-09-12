"""将具有原文证据的结构化诊断结果渲染为 Markdown。"""

from __future__ import annotations


def _render_facts(title: str, facts: list[dict]) -> list[str]:
    lines = [f"### {title}"]
    if not facts:
        return lines + ["- 未从资料中识别到，需要在下一轮沟通中确认。", ""]
    for fact in facts:
        quotes = "；".join(f"“{item['quote']}”" for item in fact["evidence"])
        lines.append(f"- **{fact['label']}**：{quotes}")
    return lines + [""]


def render_markdown(report: dict) -> str:
    lines = [f"# 客户需求诊断报告｜{report['case_name']}", "", f"生成模式：{report.get('analysis_mode', '本地规则模式')}", "", "## 1. 资料范围", report["background"]]
    if report.get("background_evidence"):
        lines.append(f"- 证据摘录：{'；'.join(f'“{quote}”' for quote in report['background_evidence'])}")
    lines.extend(["", "## 2. 原文识别结果", ""])
    lines.extend(_render_facts("业务目标", report["facts"]["goals"]))
    lines.extend(_render_facts("团队角色", report["facts"]["roles"]))
    lines.extend(_render_facts("现有工具", report["facts"]["tools"]))
    lines.extend(_render_facts("客户关注点", report["facts"]["concerns"]))
    lines.extend(["## 3. 痛点优先级与解决思路", ""])
    if not report["pain_points"]:
        lines.append("- 未从资料中识别到足以支撑痛点判断的原文证据，详见待确认问题。")
    for index, pain in enumerate(report["pain_points"], start=1):
        lines.extend([f"### {index}. {pain['title']}（优先级：{pain['priority']}）", f"- 影响程度：{pain['impact']}", f"- 紧迫程度：{pain['urgency']}", f"- 排序依据：{pain['rationale']}", "- 证据摘录："])
        lines.extend(f"  - “{item['quote']}”" for item in pain["evidence"])
        lines.extend([f"- 建议：{pain['suggestion']}", ""])
    lines.extend(["## 4. 下一轮沟通需确认的问题", ""])
    lines.extend(f"{index}. {question}" for index, question in enumerate(report["questions"], start=1))
    lines.extend(["", "---", report["method_note"]])
    return "\n".join(lines)
