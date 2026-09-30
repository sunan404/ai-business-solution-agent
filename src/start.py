"""Fail closed before the HTTP service starts in production."""

import os
import sys

from dotenv import load_dotenv

from .config import ConfigurationError, LLMSettings, provider_name
from .security import production


def validate_deployment() -> None:
    if not production():
        return
    if len(os.getenv("APP_ACCESS_PASSWORD", "")) < 12:
        raise ConfigurationError("生产模式必须配置至少 12 位的 APP_ACCESS_PASSWORD。")
    if not os.getenv("SERVICE_OPERATOR", "").strip() or not os.getenv("SERVICE_CONTACT", "").strip():
        raise ConfigurationError("生产模式必须配置 SERVICE_OPERATOR 和 SERVICE_CONTACT。")
    provider_name()
    LLMSettings.load().validate_maximum_request()


def main() -> None:
    load_dotenv()
    try:
        validate_deployment()
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    os.execv(
        sys.executable, [sys.executable, "-m", "streamlit", "run", "app.py", "--server.address", "0.0.0.0"]
    )


if __name__ == "__main__":
    main()
