"""读取本地演示资料和用户上传的非机密文件。"""

from __future__ import annotations

import csv
import posixpath
import zipfile
from io import BytesIO, StringIO
from pathlib import Path
from xml.etree.ElementTree import ParseError, fromstring, iterparse

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string, range_boundaries
from openpyxl.utils.exceptions import InvalidFileException

SUPPORTED_TYPES = ("txt", "md", "csv", "xlsx")
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 60000
MAX_ROWS = 1000
MAX_COLUMNS = 50
MAX_SHEETS = 10
MAX_UNCOMPRESSED = 20 * 1024 * 1024


class InputError(ValueError):
    """Safe, user-facing file validation error."""


def validate_text(text: str) -> str:
    if not text.strip():
        raise InputError("资料为空，请提供有内容的文本或表格。")
    if len(text) > MAX_TEXT_CHARS:
        raise InputError("提取文本超过 60,000 字符，请拆分资料；系统不会静默截断。")
    return text


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise InputError("无法识别文本编码，请另存为 UTF-8 或 GB18030。")


def dataframe_to_text(frame: pd.DataFrame, name: str = "数据表") -> str:
    """把表格压缩成适合规则诊断的可读文本。"""
    if len(frame) > MAX_ROWS or len(frame.columns) > MAX_COLUMNS:
        raise InputError("表格超过 1,000 行或 50 列，请拆分后上传。")
    if frame.empty:
        return f"{name}：空表"
    preview = frame.fillna("").to_csv(index=False)
    return f"{name}\n字段：{'、'.join(str(column) for column in frame.columns)}\n{preview}"


def _check_xlsx(content: bytes) -> dict[str, set[int]]:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(item.file_size for item in entries) > MAX_UNCOMPRESSED:
                raise InputError("Excel 解压体积或文件数超限，已拒绝读取。")
            for item in entries:
                if item.flag_bits & 1 or item.file_size / max(item.compress_size, 1) > 200:
                    raise InputError("Excel 压缩比异常或文件加密，已拒绝读取。")
                if "externalLinks/" in item.filename or "vbaProject" in item.filename:
                    raise InputError("不支持含外部工作簿链接或宏的 Excel，请导出纯数据文件。")
                if item.filename.endswith((".xml", ".rels")):
                    xml = archive.read(item)
                    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                        raise InputError("Excel 含不支持的 XML 实体定义，已拒绝读取。")
                    if item.filename.startswith("xl/worksheets/") and item.filename.endswith(".xml"):
                        # Check actual coordinates before openpyxl allocates sparse rows.
                        for _, element in iterparse(BytesIO(xml), events=("end",)):
                            kind = element.tag.rsplit("}", 1)[-1]
                            if kind == "row" and int(element.attrib.get("r", "0")) > MAX_ROWS:
                                raise InputError("Excel 超过 1,000 行或 50 列，请拆分后上传。")
                            if kind == "c" and element.attrib.get("r"):
                                column, row = coordinate_from_string(element.attrib["r"])
                                if row > MAX_ROWS or column_index_from_string(column) > MAX_COLUMNS:
                                    raise InputError("Excel 超过 1,000 行或 50 列，请拆分后上传。")
                            element.clear()
            if "xl/workbook.xml" not in archive.namelist():
                raise InputError("文件不是有效的 XLSX 工作簿。")
            return _merged_title_rows(archive)
    except (zipfile.BadZipFile, ParseError, KeyError, ValueError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("Excel 文件损坏或不是 XLSX 格式。") from exc


def _merged_title_rows(archive: zipfile.ZipFile) -> dict[str, set[int]]:
    """Only explicitly merged single-row titles may precede the real header."""
    relationships = fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
    workbook = fromstring(archive.read("xl/workbook.xml"))
    result = {}
    for sheet in workbook.findall("{*}sheets/{*}sheet"):
        relationship = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = targets[relationship]
        path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        titles = set()
        for _, element in iterparse(BytesIO(archive.read(path)), events=("end",)):
            if element.tag.rsplit("}", 1)[-1] == "mergeCell":
                first_col, first_row, last_col, last_row = range_boundaries(element.attrib["ref"])
                if first_col == 1 and last_col > 1 and first_row == last_row:
                    titles.add(first_row)
            element.clear()
        result[sheet.attrib["name"]] = titles
    return result


def _sheet_text(rows: list[tuple], name: str, title_rows: set[int] | None = None) -> str:
    populated = [(i, row) for i, row in enumerate(rows, 1) if any(value is not None for value in row)]
    if not populated:
        return f"{name}：空表"
    title_rows = title_rows or set()
    header_index = 0
    while header_index < len(populated):
        row_number, row = populated[header_index]
        if row_number not in title_rows or sum(value is not None for value in row) != 1:
            break
        header_index += 1
    if header_index == len(populated):
        raise InputError("Excel 缺少有效字段名，请在标题下添加表头。")
    header = populated[header_index][1]
    columns = [i for i, value in enumerate(header) if value is not None]
    headers = [str(header[i]) for i in columns]
    if len(set(headers)) != len(headers) or any(not value.strip() for value in headers):
        raise InputError("Excel 列名为空或重复，请设置有效且唯一的字段名。")
    notice = "\n".join(
        str(value) for _, row in populated[:header_index] for value in row if value is not None
    )
    data = [[row[i] if i < len(row) else None for i in columns] for _, row in populated[header_index + 1 :]]
    for _, row in populated[header_index + 1 :]:
        if any(value is not None and i not in columns for i, value in enumerate(row)):
            raise InputError("Excel 存在无字段名的数据列，请补齐表头。")
    return notice + "\n" + dataframe_to_text(pd.DataFrame(data, columns=headers), name)


def read_uploaded_file(filename: str, content: bytes) -> str:
    """将允许的文本/表格文件提取为文本；不向外部服务发送数据。"""
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_TYPES:
        raise InputError("仅支持 .txt、.md、.csv、.xlsx 文件")
    if len(content) > MAX_FILE_BYTES:
        raise InputError("文件超过 5 MB，请拆分后上传。")
    if not content:
        raise InputError("上传文件为空。")

    if suffix in {"txt", "md"}:
        return validate_text(_decode(content))
    if suffix == "csv":
        try:
            rows = []
            for row in csv.reader(StringIO(_decode(content)), strict=True):
                if len(row) > MAX_COLUMNS or len(rows) >= MAX_ROWS + 1:
                    raise InputError("CSV 超过 1,000 行或 50 列，请拆分后上传。")
                rows.append(row)
            if (
                not rows
                or not rows[0]
                or len(set(rows[0])) != len(rows[0])
                or any(not cell.strip() for cell in rows[0])
            ):
                raise InputError("CSV 缺少有效且唯一的字段名。")
            if any(len(row) != len(rows[0]) for row in rows[1:]):
                raise InputError("CSV 行列数不一致，请检查引号和分隔符。")
            return validate_text(dataframe_to_text(pd.DataFrame(rows[1:], columns=rows[0]), filename))
        except csv.Error as exc:
            raise InputError("CSV 格式无效，请检查字段长度、引号和分隔符。") from exc

    title_rows = _check_xlsx(content)
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False)
        try:
            if len(workbook.worksheets) > MAX_SHEETS:
                raise InputError("Excel 超过 10 个工作表，请拆分后上传。")
            sections = []
            for sheet in workbook.worksheets:
                if (sheet.max_row or 0) > MAX_ROWS or (sheet.max_column or 0) > MAX_COLUMNS:
                    raise InputError("Excel 超过 1,000 行或 50 列，请拆分后上传。")
                sheet.reset_dimensions()
                rows = []
                for row in sheet.iter_rows(values_only=True):
                    if len(rows) >= MAX_ROWS or len(row) > MAX_COLUMNS:
                        raise InputError("Excel 超过 1,000 行或 50 列，请拆分后上传。")
                    rows.append(row)
                sections.append(_sheet_text(rows, f"{filename} / {sheet.title}", title_rows.get(sheet.title)))
            return validate_text("\n\n".join(sections))
        finally:
            workbook.close()
    except (InvalidFileException, KeyError, ValueError, OSError, zipfile.BadZipFile, ParseError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("Excel 文件无法解析，请检查完整性或导出纯数据 XLSX。") from exc


def read_demo_text(path: Path) -> str:
    return validate_text(path.read_text(encoding="utf-8"))
