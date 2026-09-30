import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from scripts.calibrate_llm import add_cumulative, long_document
from scripts.check_delivery import check_delivery, validate_delivery_text
from src.budget import record_usage
from src.config import ConfigurationError, LLMSettings
from src.version import bundle_name, project_version

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("marker", ["<" * 7 + " HEAD", "=" * 7, ">" * 7 + " origin/main", "|" * 7 + " base"])
def test_conflict_markers_block_delivery_and_packaging(tmp_path, marker, monkeypatch):
    from scripts import package_release

    (tmp_path / "README.md").write_text(f"intro\n{marker}\nend\n", encoding="utf-8")
    with pytest.raises(ValueError, match="README.md"):
        check_delivery(tmp_path)
    monkeypatch.setattr(package_release, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="conflict marker"):
        package_release.main()
    assert not (tmp_path / "dist").exists()


def test_current_delivery_sources_are_clean():
    check_delivery(ROOT)
    validate_delivery_text("## Header\n```python\nvalue = '======='\n```", "example")


def test_usage_rates_can_change_without_null_poisoning():
    settings = LLMSettings.load()
    # No reserve required for this focused test; normally reserve creates its parent.
    Path(os.environ["QUOTA_DB_PATH"]).parent.mkdir(exist_ok=True)
    assert record_usage(settings, 100, 20, None)
    assert record_usage(settings, 200, 30, None)
    with closing(sqlite3.connect(os.environ["QUOTA_DB_PATH"])) as db:
        assert db.execute("SELECT estimated_usd FROM usage_daily").fetchone()[0] is None
    assert record_usage(settings, 300, 40, 0.02)
    assert record_usage(settings, 400, 50, None)
    assert record_usage(settings, 500, 60, 0.03)
    with closing(sqlite3.connect(os.environ["QUOTA_DB_PATH"])) as db:
        row = db.execute("SELECT measured_responses, input_tokens, estimated_usd FROM usage_daily").fetchone()
    assert row[:2] == (5, 1500)
    assert row[2] == pytest.approx(0.05)  # Only known-priced usage, not a complete invoice.


def test_llm_alias_precedence_and_legacy_compatibility(monkeypatch):
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "41")
    assert LLMSettings.load().timeout == 41
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "17")
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "7000")
    settings = LLMSettings.load()
    assert (settings.timeout, settings.retries, settings.max_output_tokens) == (17, 0, 7000)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "invalid")
    with pytest.raises(ConfigurationError, match="LLM_TIMEOUT_SECONDS"):
        LLMSettings.load()


def test_calibration_cumulative_does_not_hide_failed_runs():
    summary = {
        "cases": [{"passed": True, "input_chars": 22000}],
        "previous_runs": [{"cases": [{"passed": False, "input_chars": 1000}]}],
    }
    result = add_cumulative(summary)
    assert result["all_time_success_rate"] == "1/2"
    assert result["cumulative"]["failed"] == 1
    assert result["cumulative"]["long_document_passed"] == 1
    assert add_cumulative(json.loads(json.dumps(result))) == result


def test_long_calibration_documents_are_bounded_and_reproducible():
    first = long_document("虚构原始案例", "game")
    assert 20000 <= len(first) <= 60000
    assert first == long_document("虚构原始案例", "game")
    assert "T001" in first and "未见异常" in first


def test_release_version_single_source(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "9.8.7"\n', encoding="utf-8")
    assert project_version(tmp_path) == "9.8.7"
    assert bundle_name() == f"ai-business-solution-agent-{project_version()}.zip"


def test_start_exec_path_is_validated_without_launching_server(monkeypatch, capsys):
    from src import start

    monkeypatch.setattr(start, "load_dotenv", lambda: None)
    calls = []
    monkeypatch.setattr(start.os, "execv", lambda executable, args: calls.append((executable, args)))
    start.main()
    assert calls[0][1] == [calls[0][0], "-m", "streamlit", "run", "app.py", "--server.address", "0.0.0.0"]
    calls.clear()
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(SystemExit) as raised:
        start.main()
    assert raised.value.code == 1
    assert not calls
    assert "APP_ACCESS_PASSWORD" in capsys.readouterr().err
