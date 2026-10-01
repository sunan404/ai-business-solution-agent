"""Regression cases for the independently reproduced review defects."""

import re
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

from src.ingest import InputError, read_uploaded_file
from src.llm import LLMOutputError, validate_llm_payload


def workbook_bytes(rows: list[list], dimension: str | None = None) -> bytes:
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    original = BytesIO()
    workbook.save(original)
    if dimension is None:
        return original.getvalue()
    changed = BytesIO()
    with ZipFile(original) as source, ZipFile(changed, "w", ZIP_DEFLATED) as target:
        for name in source.namelist():
            content = source.read(name)
            if name == "xl/worksheets/sheet1.xml":
                content = re.sub(
                    rb'<dimension ref="[^"]+"', f'<dimension ref="{dimension}"'.encode(), content
                )
            target.writestr(name, content)
    return changed.getvalue()


def test_underreported_excel_dimension_does_not_drop_last_row():
    content = workbook_bytes(
        [["角色", "问题"], ["市场团队", "手工汇总"], ["运营团队", "客户问题遗漏"]], "A1:B2"
    )
    text = read_uploaded_file("input.xlsx", content)
    assert "运营团队,客户问题遗漏" in text
    assert "市场团队,手工汇总" in text


@pytest.mark.parametrize(
    "rows",
    [
        [["字段"]] + [[f"row-{i}"] for i in range(1000)],
        [["字段"] + [None] * 50, ["内容"] + [None] * 49 + ["超界"]],
    ],
)
def test_actual_excel_limits_apply_when_dimensions_lie(rows):
    with pytest.raises(InputError, match="1,000 行或 50 列"):
        read_uploaded_file("input.xlsx", workbook_bytes(rows, "A1:A2"))


@pytest.mark.parametrize(
    "rows",
    [
        [["角色", "问题", None], ["市场团队", "手工汇总", "客户问题遗漏"]],
        [["角色", None], ["市场团队", "手工汇总"]],
    ],
)
def test_data_row_cannot_become_header_to_hide_missing_column_name(rows):
    with pytest.raises(InputError, match="无字段名"):
        read_uploaded_file("input.xlsx", workbook_bytes(rows))


def minimal_payload() -> dict:
    return {
        "customer_background": {"summary": "团队存在资料分散问题", "evidence": ["资料分散"]},
        "business_goals": [],
        "team_roles": [],
        "existing_tools": [],
        "customer_concerns": [],
        "pain_points": [
            {
                "title": "资料分散",
                "impact": "中",
                "urgency": "高",
                "priority": "高",
                "priority_reason": "需进一步确认",
                "evidence": ["资料分散"],
                "suggestion": "建立资料目录",
            }
        ],
        "questions_to_confirm": ["涉及哪些资料？"],
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", 123),
        ("suggestion", {"x": 1}),
        ("priority_reason", True),
        ("impact", []),
        ("urgency", {}),
        ("priority", None),
        ("evidence", "资料分散"),
        ("evidence", [123]),
    ],
)
def test_pain_schema_type_errors_are_rejected_as_output_errors(field, value):
    payload = minimal_payload()
    payload["pain_points"][0][field] = value
    with pytest.raises(LLMOutputError):
        validate_llm_payload(payload, "资料分散")


@pytest.mark.parametrize("value", ["资料分散", [123], None, {}])
def test_background_evidence_type_errors_are_not_repaired(value):
    payload = minimal_payload()
    payload["customer_background"]["evidence"] = value
    with pytest.raises(LLMOutputError, match="字符串数组"):
        validate_llm_payload(payload, "资料分散")
