"""可解释、可回溯的本地客户需求诊断规则。"""

from __future__ import annotations

from dataclasses import dataclass

from .retrieve import find_evidence, split_evidence_units


@dataclass(frozen=True)
class FactRule:
    label: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class PainRule:
    title: str
    issue_keywords: tuple[str, ...]
    recommendation: str


ROLE_RULES = (
    FactRule("管理者", ("负责人", "管理团队", "管理者", "总经理", "业务负责人")),
    FactRule("市场团队", ("市场部", "市场团队", "市场、", "市场和")),
    FactRule("销售/商务团队", ("销售团队", "销售主管", "销售、", "商务团队", "商务同事")),
    FactRule("运营团队", ("运营团队", "渠道运营", "运营同事", "运营、", "门店团队", "门店、")),
    FactRule("研发/产品团队", ("研发/产品", "研发团队", "产品团队", "研发、")),
    FactRule("设计/内容团队", ("设计团队", "设计、", "本地化团队", "本地化、", "内容团队")),
    FactRule("财务团队", ("财务团队", "财务、")),
)

TOOL_RULES = (
    FactRule("Excel/表格", ("Excel", "表格", "电子表格")),
    FactRule("即时消息/聊天", ("即时消息", "聊天记录", "聊天确认", "群聊", "企业微信", "钉钉", "飞书")),
    FactRule("个人网盘/文件夹", ("个人网盘", "个人文件夹", "网盘", "共享盘")),
    FactRule("邮件", ("邮件", "邮箱")),
    FactRule("项目管理工具", ("Jira", "Trello", "Asana", "项目管理工具")),
    FactRule("CRM", ("CRM", "客户管理系统")),
)

GOAL_RULES = (
    FactRule("完成市场验证或拓展", ("市场验证", "上线", "进入", "覆盖", "渠道组合", "增长")),
    FactRule("提升项目交付效率", ("同一节奏", "交付效率", "缩短", "准时", "活动延期")),
    FactRule("提升渠道或客户经营", ("经销商覆盖", "客户响应", "合作", "渠道效果")),
    FactRule("提升数据复盘与决策效率", ("复盘效率", "经营复盘", "统一口径", "更快的市场决策")),
)

CONCERN_RULE = FactRule("客户关注点", ("关心", "关注", "担心", "希望", "优先", "关键", "是否能", "要求"))

PAIN_RULES = (
    PainRule("信息与知识分散", ("资料分散", "找不到", "重复收集", "难以检索", "最新版本"), "建立按业务主题、地区/渠道和项目归档的共享知识库；设置资料负责人、标签、版本和更新规则。"),
    PainRule("跨团队协作与项目状态不透明", ("多个表格", "不同步", "截止时间", "延期", "无法同步", "交接"), "在统一项目空间维护里程碑、任务负责人、依赖关系、素材版本和风险；用固定节奏同步阻塞项。"),
    PainRule("客户或渠道跟进存在断点", ("跟进状态", "历史沟通", "遗漏", "客户问题", "交接时", "漏跟进"), "统一客户/渠道档案、合作阶段、下一步动作和交接清单，并为逾期跟进建立提醒。"),
    PainRule("数据汇总与指标口径不一致", ("手工汇总", "数据口径", "指标口径", "数据不同", "汇总慢"), "先明确指标定义、数据来源、更新负责人和复盘周期，再沉淀可追溯的数据看板。"),
    PainRule("关键审批缺少流程留痕", ("审批", "聊天确认", "流程记录", "可追溯", "漏批", "审批等待"), "把预算、对外内容等关键事项配置为标准表单和审批流，明确审批人、时限及留痕规则。"),
)

IMPACT_TERMS = ("收入", "销售", "客户", "渠道", "经销商", "上线", "合同", "预算", "交付", "核心", "覆盖")
MEDIUM_IMPACT_TERMS = ("延期", "遗漏", "漏", "返工", "风险", "耗时", "两天", "三天", "问题响应")
HIGH_URGENCY_TERMS = ("今天", "本周", "本月", "90 天", "90天", "截止", "即将", "正在", "延期", "漏", "每天", "每周")
MEDIUM_URGENCY_TERMS = ("每月", "季度", "尽快", "优先", "希望", "需要")


def _evidence_items(text: str, keywords: tuple[str, ...], limit: int = 3) -> list[dict[str, object]]:
    return [{"quote": quote, "matched_terms": [term for term in keywords if term.lower() in quote.lower()]} for quote in find_evidence(text, list(keywords), limit)]


def _extract_facts(text: str, rules: tuple[FactRule, ...]) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    for rule in rules:
        evidence = _evidence_items(text, rule.keywords, limit=2)
        if evidence:
            facts.append({"label": rule.label, "evidence": evidence})
    return facts


def _levels(evidence: list[dict[str, object]], all_roles: list[dict[str, object]]) -> tuple[str, str, int, str]:
    combined = " ".join(str(item["quote"]) for item in evidence)
    impact_score = 3 if any(term in combined for term in IMPACT_TERMS) else 2 if any(term in combined for term in MEDIUM_IMPACT_TERMS) else 1
    roles_in_evidence = {fact["label"] for fact in all_roles if any(str(ev["quote"]) in combined for ev in fact["evidence"])}
    if len(roles_in_evidence) >= 2:
        impact_score = min(3, impact_score + 1)
    urgency_score = 3 if any(term in combined for term in HIGH_URGENCY_TERMS) else 2 if any(term in combined for term in MEDIUM_URGENCY_TERMS) else 1
    level = {1: "低", 2: "中", 3: "高"}
    priority_score = impact_score * 2 + urgency_score
    rationale = f"影响程度为{level[impact_score]}，紧迫程度为{level[urgency_score]}；评分依据仅来自下方证据摘录中的业务后果、时限或频率描述。"
    return level[impact_score], level[urgency_score], priority_score, rationale


def _missing_questions(facts: dict[str, list[dict[str, object]]], pain_points: list[dict[str, object]]) -> list[str]:
    questions: list[str] = []
    if not facts["goals"]:
        questions.append("本次希望优先达成什么业务结果？请提供目标指标、目标值和期望完成时间。")
    if not facts["roles"]:
        questions.append("该流程涉及哪些角色？分别负责什么输入、决策和交付物？")
    if not facts["tools"]:
        questions.append("每个关键流程当前使用哪些工具或表格？谁维护、谁有编辑权限？")
    if not facts["concerns"]:
        questions.append("客户当前最希望优先解决的问题是什么？判断改善是否成功的标准是什么？")
    if not pain_points:
        questions.append("请描述一条实际受阻流程：从开始到交付的步骤、频率、耗时、参与角色和造成的业务影响。")
    questions.extend(["如需优先推进一个改进项，您愿意用哪个指标衡量成效，例如交付周期、漏跟进率或复盘准备时间？", "哪些资料或数据必须成为唯一可信来源？请确认更新负责人、更新频率和访问权限。"])
    return list(dict.fromkeys(questions))[:5]


def diagnose(text: str, case_name: str = "自定义资料") -> dict:
    """从用户原文抽取事实和问题信号；不调用模型，也不编造缺失事实。"""
    if not text or not text.strip():
        raise ValueError("请粘贴资料、上传文件或选择一个演示案例。")

    facts = {"goals": _extract_facts(text, GOAL_RULES), "roles": _extract_facts(text, ROLE_RULES), "tools": _extract_facts(text, TOOL_RULES), "concerns": _extract_facts(text, (CONCERN_RULE,))}
    pain_points: list[dict[str, object]] = []
    for rule in PAIN_RULES:
        evidence = _evidence_items(text, rule.issue_keywords)
        if evidence:
            impact, urgency, priority_score, rationale = _levels(evidence, facts["roles"])
            pain_points.append({"title": rule.title, "impact": impact, "urgency": urgency, "priority": "待排序", "priority_score": priority_score, "rationale": rationale, "evidence": evidence, "suggestion": rule.recommendation})

    pain_points.sort(key=lambda item: (int(item["priority_score"]), len(item["evidence"])), reverse=True)
    for pain in pain_points:
        score = int(pain["priority_score"])
        pain["priority"] = "高" if score >= 8 else "中" if score >= 5 else "低"

    source_units = split_evidence_units(text)
    return {
        "case_name": case_name,
        "background": f"本报告基于“{case_name}”提供的 {len(source_units)} 条原文资料生成。未识别到的业务背景、角色或工具不会补写为结论。",
        "facts": facts,
        "pain_points": pain_points,
        "questions": _missing_questions(facts, pain_points),
        "method_note": "本报告为本地规则分析。所有已识别事实和痛点均附原文证据摘录；未提供的信息仅以待确认问题呈现。",
    }
