"""Validated deployment configuration; secrets are never returned."""

import math
import os
import re
from dataclasses import dataclass


class ConfigurationError(ValueError):
    pass


MAX_INPUT_CHARACTERS = 60000
# Include schema, instructions, filename and protocol framing. Kept above the measured prompt overhead.
PROMPT_TOKEN_MARGIN = 24000


def provider_name() -> str:
    value = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if value not in {"openai", "deepseek"}:
        raise ConfigurationError("LLM_PROVIDER 仅支持 openai 或 deepseek。")
    return value


def service_name() -> str:
    return {"openai": "OpenAI", "deepseek": "DeepSeek"}[provider_name()]


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{name} 必须为整数。") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} 必须在 {minimum} 到 {maximum} 之间。")
    return value


def env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{name} 必须为有效数值。") from exc
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} 必须在 {minimum} 到 {maximum} 之间。")
    return value


@dataclass(frozen=True)
class LLMSettings:
    timeout: float
    retries: int
    max_output_tokens: int
    daily_requests: int
    daily_tokens: int
    daily_usd: float
    input_rate: float
    output_rate: float
    tenant_id: str = "default"
    tenant_requests: int = 20
    tenant_tokens: int = 2000000

    @classmethod
    def load(cls) -> "LLMSettings":
        settings = cls(
            timeout=env_float("OPENAI_TIMEOUT_SECONDS", 30, 1, 60),
            retries=env_int("OPENAI_MAX_RETRIES", 1, 0, 2),
            max_output_tokens=env_int("OPENAI_MAX_OUTPUT_TOKENS", 6000, 256, 12000),
            daily_requests=env_int("LLM_DAILY_REQUEST_LIMIT", 20, 1, 1000),
            daily_tokens=env_int("LLM_DAILY_TOKEN_BUDGET", 2000000, 1, 10000000),
            daily_usd=env_float("LLM_DAILY_USD_BUDGET", 0, 0, 1000),
            input_rate=env_float("LLM_INPUT_USD_PER_MILLION", 0, 0, 1000),
            output_rate=env_float("LLM_OUTPUT_USD_PER_MILLION", 0, 0, 1000),
            tenant_id=os.getenv("TENANT_ID", "default"),
            tenant_requests=env_int("TENANT_DAILY_REQUEST_LIMIT", 20, 1, 1000),
            tenant_tokens=env_int("TENANT_DAILY_TOKEN_BUDGET", 2000000, 1, 10000000),
        )
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", settings.tenant_id):
            raise ConfigurationError(
                "TENANT_ID 必须为 1–64 位英文字母、数字、下划线或连字符，不使用客户真实名称。"
            )
        if settings.daily_usd and not (settings.input_rate and settings.output_rate):
            raise ConfigurationError("设置美元预算时必须同时配置输入与输出费率。")
        return settings

    def validate_maximum_request(self) -> None:
        # A Unicode scalar can take four UTF-8 bytes; cover emoji as well as CJK, and all retries.
        maximum = (MAX_INPUT_CHARACTERS * 4 + PROMPT_TOKEN_MARGIN + self.max_output_tokens) * (
            self.retries + 1
        )
        if min(self.daily_tokens, self.tenant_tokens) < maximum:
            raise ConfigurationError(
                f"LLM_DAILY_TOKEN_BUDGET 至少需要 {maximum}，才能容纳承诺的 60,000 字符最大请求与重试；请调整配置。"
            )
        if min(self.daily_requests, self.tenant_requests) < self.retries + 1:
            raise ConfigurationError("每日请求上限不足以容纳一次请求的最坏重试次数。")
