from pathlib import Path

from src.desktop import prepare_environment, server_command, user_directory


def test_client_configuration_is_preserved_and_relative_quota_is_user_scoped(monkeypatch, tmp_path):
    config = tmp_path / ".env"
    config.write_text("LLM_PROVIDER=deepseek\n", encoding="utf-8")
    monkeypatch.delenv("LLM_PROVIDER")
    monkeypatch.setenv("QUOTA_DB_PATH", "runtime/quota.sqlite3")
    assert prepare_environment(tmp_path) == config
    assert config.read_text(encoding="utf-8") == "LLM_PROVIDER=deepseek\n"
    import os

    assert os.environ["LLM_PROVIDER"] == "deepseek"
    assert Path(os.environ["QUOTA_DB_PATH"]) == tmp_path / "runtime" / "quota.sqlite3"


def test_client_first_launch_copies_only_empty_secret_template(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    config = prepare_environment(tmp_path)
    text = config.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=\n" in text and "DEEPSEEK_API_KEY=\n" in text
    assert text.split("OPENAI_API_KEY=", 1)[1].splitlines()[0] == ""


def test_client_uses_localappdata_and_frozen_executable_for_backend(monkeypatch, tmp_path):
    import sys

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert user_directory() == tmp_path / "BusinessDiagnosis"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    command = server_command(12345)
    assert command[0] == sys.executable
    assert command[1:4] == ["--serve", "--port", "12345"]
    assert "desktop.py" not in command


def test_backend_applies_loopback_flags_before_starting_streamlit(monkeypatch):
    from streamlit.web import bootstrap

    from src import desktop

    calls = []
    monkeypatch.setattr(desktop.threading.Thread, "start", lambda self: None)
    monkeypatch.setattr(bootstrap, "load_config_options", lambda flags: calls.append(("load", flags)))
    monkeypatch.setattr(bootstrap, "run", lambda *args: calls.append(("run", args[3])))
    desktop.serve(12345, 123)
    assert [call[0] for call in calls] == ["load", "run"]
    assert calls[0][1] == calls[1][1]
    assert calls[0][1]["server_address"] == "127.0.0.1"
    assert calls[0][1]["server_port"] == 12345
    assert calls[0][1]["server_enableXsrfProtection"] is True
    assert calls[0][1]["global_developmentMode"] is False


def test_client_smoke_generates_reports_serves_http_and_stops_backend(monkeypatch, tmp_path):
    import json

    from src.desktop import smoke_test

    monkeypatch.setenv("DIAGNOSIS_DESKTOP", "")
    monkeypatch.setenv("DIAGNOSIS_CONFIG_PATH", "")
    result = tmp_path / "smoke.json"
    smoke_test(result)
    report = json.loads(result.read_text(encoding="utf-8"))
    assert report["passed"]
    assert {"both_report_pages", "download_buttons", "http", "shutdown"} <= set(report["checks"])
