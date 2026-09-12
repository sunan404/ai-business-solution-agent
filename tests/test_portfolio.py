"""Release-facing regressions; no real API requests or secret reads."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.ingest import read_uploaded_file
from src.llm import LLMOutputError, validate_llm_payload


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('filename,content', [
    ('note.txt', '市场团队希望改善流程。'.encode('utf-8-sig')),
    ('note.md', '# 虚构访谈\n市场团队希望改善流程。'.encode()),
    ('table.csv', '团队,问题\n市场团队,数据口径不同'.encode('utf-8-sig')),
])
def test_supported_text_uploads(filename, content):
    assert '市场团队' in read_uploaded_file(filename, content)


def test_workbook_demo_is_readable_and_marked_fictional():
    text = read_uploaded_file('demo.xlsx', (ROOT / 'data/demo_consumer_brand.xlsx').read_bytes())
    assert '虚构' in text
    assert '手工汇总' in text


def test_unsupported_or_corrupt_files_are_rejected():
    with pytest.raises(ValueError):
        read_uploaded_file('input.exe', b'data')
    with pytest.raises(Exception):
        read_uploaded_file('input.xlsx', b'not a workbook')


@pytest.mark.parametrize('payload', [[], {}, {'customer_background': 'wrong type'}])
def test_bad_llm_structure_rejected(payload):
    with pytest.raises(LLMOutputError):
        validate_llm_payload(payload, '虚构资料')


def test_local_page_generates_report_with_download():
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    app.button[0].click().run()
    assert not app.exception
    assert app.get('download_button')[0].label == '下载 Markdown 诊断报告'
