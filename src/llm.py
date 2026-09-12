"""可选的 OpenAI LLM 诊断模式。

密钥仅从运行环境读取，模块不会写入、打印或返回密钥。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any


class LLMConfigurationError(RuntimeError):
    """LLM 模式缺少本地运行配置。"""


class LLMOutputError(ValueError):
    """模型输出无法作为可回溯的诊断报告使用。"""


class LLMRequestError(RuntimeError):
    """模型请求未成功完成。"""


LEVELS = {"高", "中", "低", "待确认"}

DIAGNOSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["customer_background", "business_goals", "team_roles", "existing_tools", "customer_concerns", "pain_points", "questions_to_confirm"],
    "properties": {
        "customer_background": {
            "type": "object",
            "additionalProperties": False,
            "required": ["summary", "evidence"],
            "properties": {"summary": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}},
        },
        "business_goals": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["label", "evidence"], "properties": {"label": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}}}},
        "team_roles": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["label", "evidence"], "properties": {"label": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}}}},
        "existing_tools": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["label", "evidence"], "properties": {"label": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}}}},
        "customer_concerns": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["label", "evidence"], "properties": {"label": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}}}},
        "pain_points": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "impact", "urgency", "priority", "priority_reason", "evidence", "suggestion"],
                "properties": {
                    "title": {"type": "string"}, "impact": {"type": "string"}, "urgency": {"type": "string"}, "priority": {"type": "string"},
                    "priority_reason": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}, "suggestion": {"type": "string"},
                },
            },
        },
        "questions_to_confirm": {"type": "array", "items": {"type": "string"}},
    },
}

SYSTEM_INSTRUCTIONS = """你是 SaaS 客户需求诊断助手。只基于用户提供的资料生成中文诊断。
不得编造客户背景、目标、工具、角色、数据、痛点或优先级。每一个客户背景、目标、角色、工具和痛点必须附至少一条从资料原样复制的证据摘录。
证据摘录不得改写、拼接或使用省略号。资料不足时不要输出猜测性的条目，而是在 questions_to_confirm 中提出具体待确认问题。
痛点 priority 只能为 高、中、低、待确认，并综合 impact 与 urgency 判断。建议必须与已列痛点对应且具体可执行。
"""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def is_llm_configured() -> bool:
    """仅检查环境中是否存在非空密钥，不暴露密钥本身。"""
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _validate_evidence(evidence: Any, source_text: str, field: str) -> list[str]:
    if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item.strip() for item in evidence):
        raise LLMOutputError(f"模型输出的 {field} 缺少有效证据摘录。")
    normalized_source = _normalize(source_text)
    for quote in evidence:
        if _normalize(quote) not in normalized_source:
            raise LLMOutputError(f"模型输出的 {field} 包含无法回溯到原文的证据摘录。")
    return evidence


def validate_llm_payload(payload: Any, source_text: str) -> dict[str, Any]:
    """对结构化输出进行应用端校验，拒绝非 JSON、缺字段和不可回溯证据。"""
    if not isinstance(payload, dict):
        raise LLMOutputError("模型输出不是 JSON 对象。")
    required = set(DIAGNOSIS_SCHEMA["required"])
    if set(payload) != required:
        raise LLMOutputError("模型 JSON 字段不完整或包含未预期字段。")

    background = payload["customer_background"]
    if not isinstance(background, dict) or set(background) != {"summary", "evidence"} or not isinstance(background["summary"], str):
        raise LLMOutputError("模型输出的客户背景格式无效。")
    _validate_evidence(background["evidence"], source_text, "客户背景")

    for field in ("business_goals", "team_roles", "existing_tools", "customer_concerns"):
        if not isinstance(payload[field], list):
            raise LLMOutputError(f"模型输出的 {field} 不是列表。")
        for item in payload[field]:
            if not isinstance(item, dict) or set(item) != {"label", "evidence"} or not isinstance(item["label"], str) or not item["label"].strip():
                raise LLMOutputError(f"模型输出的 {field} 条目格式无效。")
            _validate_evidence(item["evidence"], source_text, field)

    if not isinstance(payload["pain_points"], list):
        raise LLMOutputError("模型输出的 pain_points 不是列表。")
    pain_fields = {"title", "impact", "urgency", "priority", "priority_reason", "evidence", "suggestion"}
    for item in payload["pain_points"]:
        if not isinstance(item, dict) or set(item) != pain_fields:
            raise LLMOutputError("模型输出的痛点字段不完整。")
        if any(not isinstance(item[field], str) or not item[field].strip() for field in pain_fields - {"evidence"}):
            raise LLMOutputError("模型输出的痛点包含空字段。")
        if item["impact"] not in LEVELS or item["urgency"] not in LEVELS or item["priority"] not in LEVELS:
            raise LLMOutputError("模型输出的痛点等级必须为高、中、低或待确认。")
        _validate_evidence(item["evidence"], source_text, "痛点")

    if not isinstance(payload["questions_to_confirm"], list) or not all(isinstance(question, str) and question.strip() for question in payload["questions_to_confirm"]):
        raise LLMOutputError("模型输出的待确认问题格式无效。")
    return payload


def parse_and_validate_llm_output(raw_output: str, source_text: str) -> dict[str, Any]:
    """拒绝非 JSON 文本，并校验字段与原文证据。"""
    try:
        payload = json.loads(raw_output)
    except (TypeError, json.JSONDecodeError) as exc:
        raise LLMOutputError("模型返回内容不是可解析的 JSON，未生成诊断报告。请重试或切换至本地规则模式。") from exc
    return validate_llm_payload(payload, source_text)


def _fact_records(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"label": item["label"], "evidence": [{"quote": quote, "matched_terms": []} for quote in item["evidence"]]} for item in items]


def llm_payload_to_report(payload: dict[str, Any], case_name: str) -> dict[str, Any]:
    """把校验后的 LLM JSON 转成与本地模式共用的页面/下载报告结构。"""
    return {
        "case_name": case_name,
        "background": payload["customer_background"]["summary"],
        "background_evidence": payload["customer_background"]["evidence"],
        "facts": {"goals": _fact_records(payload["business_goals"]), "roles": _fact_records(payload["team_roles"]), "tools": _fact_records(payload["existing_tools"]), "concerns": _fact_records(payload["customer_concerns"])},
        "pain_points": [{"title": item["title"], "impact": item["impact"], "urgency": item["urgency"], "priority": item["priority"], "priority_score": 0, "rationale": item["priority_reason"], "evidence": [{"quote": quote, "matched_terms": []} for quote in item["evidence"]], "suggestion": item["suggestion"]} for item in payload["pain_points"]],
        "questions": payload["questions_to_confirm"],
        "method_note": "本报告由 LLM 增强模式生成。应用已校验 JSON 结构和每条证据摘录与输入原文的对应关系；仍应由业务人员人工核验。",
        "analysis_mode": "LLM 增强模式",
    }


def diagnose_with_llm(text: str, case_name: str = "自定义资料") -> dict[str, Any]:
    """调用 Responses API 并将严格校验后的 JSON 转为诊断报告。"""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise LLMConfigurationError("未检测到 API Key。请在本机环境中配置后重试，或使用本地规则模式。")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMConfigurationError("未安装 OpenAI SDK。请安装 requirements.txt 中的依赖后重试。") from exc

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=f"资料名称：{case_name}\n\n客户资料：\n{text}",
            text={"format": {"type": "json_schema", "name": "customer_diagnosis", "strict": True, "schema": DIAGNOSIS_SCHEMA}},
            store=False,
        )
        raw_output = response.output_text
    except Exception as exc:
        raise LLMRequestError("LLM 请求未能完成。请检查网络、模型访问权限与本机环境配置后重试。") from exc

    return llm_payload_to_report(parse_and_validate_llm_output(raw_output, text), case_name)
