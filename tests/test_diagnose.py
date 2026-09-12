from src.diagnose import diagnose
from src.report import render_markdown


def test_extracts_facts_and_keeps_evidence_in_source() -> None:
    text = (
        "市场团队和销售团队希望在 90 天内完成渠道市场验证。"
        "目前用 Excel 和聊天记录维护联系人；每周手工汇总渠道数据，复盘需要两天。"
    )
    report = diagnose(text)

    assert any(item["label"] == "市场团队" for item in report["facts"]["roles"])
    assert any(item["label"] == "Excel/表格" for item in report["facts"]["tools"])
    assert report["facts"]["goals"]
    for pain in report["pain_points"]:
        for evidence in pain["evidence"]:
            assert evidence["quote"] in text


def test_pain_points_are_sorted_by_impact_then_urgency() -> None:
    text = (
        "销售团队每周手工汇总经销商渠道数据，数据口径不同，影响客户覆盖决策。"
        "市场团队的活动排期使用多个表格，但尚未说明截止时间。"
    )
    report = diagnose(text)

    assert report["pain_points"][0]["title"] == "数据汇总与指标口径不一致"
    assert report["pain_points"][0]["impact"] == "高"
    assert report["pain_points"][0]["urgency"] == "高"


def test_missing_information_creates_questions_not_invented_facts() -> None:
    report = diagnose("客户希望改善协作体验。")

    assert report["facts"]["roles"] == []
    assert report["facts"]["tools"] == []
    assert report["pain_points"] == []
    assert any("哪些角色" in question for question in report["questions"])
    assert any("哪些工具" in question for question in report["questions"])


def test_markdown_contains_evidence_excerpt_section() -> None:
    report = diagnose("审批依赖聊天确认，审批人和最终版本没有统一流程记录。")
    markdown = render_markdown(report)

    assert "证据摘录" in markdown
    assert "审批依赖聊天确认" in markdown
    assert "下一轮沟通需确认的问题" in markdown

