"""读取本地演示资料和用户上传的非机密文件。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd


SUPPORTED_TYPES = ("txt", "md", "csv", "xlsx")


def dataframe_to_text(frame: pd.DataFrame, name: str = "数据表") -> str:
    """把表格压缩成适合规则诊断的可读文本。"""
    if frame.empty:
        return f"{name}：空表"
    preview = frame.fillna("").head(80).to_csv(index=False)
    return f"{name}\n字段：{'、'.join(str(column) for column in frame.columns)}\n{preview}"


def read_uploaded_file(filename: str, content: bytes) -> str:
    """将允许的文本/表格文件提取为文本；不向外部服务发送数据。"""
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_TYPES:
        raise ValueError("仅支持 .txt、.md、.csv、.xlsx 文件")

    if suffix in {"txt", "md"}:
        return content.decode("utf-8-sig", errors="replace")
    if suffix == "csv":
        frame = pd.read_csv(BytesIO(content), encoding="utf-8-sig")
        return dataframe_to_text(frame, filename)

    workbook = pd.ExcelFile(BytesIO(content))
    sections: list[str] = []
    for sheet_name in workbook.sheet_names[:5]:
        frame = pd.read_excel(workbook, sheet_name=sheet_name)
        sections.append(dataframe_to_text(frame, f"{filename} / {sheet_name}"))
    return "\n\n".join(sections)


def read_demo_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

