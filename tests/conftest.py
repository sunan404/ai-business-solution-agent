import pytest


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    # No real credentials, network budget database or deployment settings in tests.
    for name in ("LLM_MODEL", "LLM_TIMEOUT_SECONDS", "LLM_MAX_RETRIES", "LLM_MAX_OUTPUT_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "6000")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APP_ACCESS_PASSWORD", "")
    monkeypatch.setenv("QUOTA_DB_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "1")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("LLM_DAILY_REQUEST_LIMIT", "20")
    monkeypatch.setenv("LLM_DAILY_TOKEN_BUDGET", "2000000")
    monkeypatch.setenv("TENANT_ID", "default")
    monkeypatch.setenv("TENANT_DAILY_REQUEST_LIMIT", "20")
    monkeypatch.setenv("TENANT_DAILY_TOKEN_BUDGET", "2000000")
    monkeypatch.setenv("LLM_DAILY_USD_BUDGET", "0")
    monkeypatch.setenv("LLM_INPUT_USD_PER_MILLION", "0")
    monkeypatch.setenv("LLM_OUTPUT_USD_PER_MILLION", "0")
