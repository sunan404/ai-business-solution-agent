"""本地文本切分与证据检索工具，不向外部服务发送资料。"""

from __future__ import annotations

import re


def split_evidence_units(text: str) -> list[str]:
    """按原始段落、项目符号和句号切分，保留可回溯的原文。"""
    units: list[str] = []
    for line in text.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)]|#+)\s*", "", line).strip()
        if not cleaned or ("虚构" in cleaned and ("仅用于" in cleaned or "不代表" in cleaned)):
            continue
        for sentence in re.split(r"(?<=[。！？；;])\s*", cleaned):
            sentence = sentence.strip()
            if len(sentence) >= 8:
                units.append(sentence)
    return units


def find_evidence(text: str, keywords: list[str], limit: int = 3) -> list[str]:
    """返回包含关键词的原始句子，而非模型改写的摘要。"""
    matches: list[str] = []
    for unit in split_evidence_units(text):
        if any(keyword.lower() in unit.lower() for keyword in keywords) and unit not in matches:
            matches.append(unit)
        if len(matches) >= limit:
            break
    return matches
