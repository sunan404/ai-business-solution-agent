"""Atomic single-host daily reservations, shared across processes and browser sessions."""

import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import LLMSettings


class QuotaError(RuntimeError):
    pass


def reserve_budget(input_token_bound: int, settings: LLMSettings) -> None:
    attempts = settings.retries + 1
    tokens = attempts * (input_token_bound + settings.max_output_tokens)
    usd = (
        attempts
        * (input_token_bound * settings.input_rate + settings.max_output_tokens * settings.output_rate)
        / 1000000
    )
    if attempts > min(settings.daily_requests, settings.tenant_requests) or tokens > min(
        settings.daily_tokens, settings.tenant_tokens
    ):
        raise QuotaError(
            "本次请求预留量超过整日请求/token 预算，尚未扣除额度。请缩短资料或联系管理员调整配置。"
        )
    if settings.daily_usd and usd > settings.daily_usd:
        raise QuotaError("本次请求的预估费用超过整日金额预算，尚未扣除额度。请缩短资料或调整预算。")
    path = Path(os.getenv("QUOTA_DB_PATH", "runtime/quota.sqlite3"))
    day = datetime.now(ZoneInfo("Asia/Hong_Kong")).date().isoformat()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=5)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS daily (day TEXT PRIMARY KEY, requests INTEGER, tokens INTEGER, usd REAL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS tenant_daily (day TEXT, tenant_id TEXT, requests INTEGER, tokens INTEGER, PRIMARY KEY(day, tenant_id))"
            )
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT requests, tokens, usd FROM daily WHERE day=?", (day,)).fetchone() or (
                0,
                0,
                0.0,
            )
            if row[0] + attempts > settings.daily_requests or row[1] + tokens > settings.daily_tokens:
                raise QuotaError("今日共享请求或 token 预算已达上限，请明日重试或使用本地模式。")
            if settings.daily_usd and row[2] + usd > settings.daily_usd:
                raise QuotaError("今日预估费用预算已达上限，请明日重试或使用本地模式。")
            tenant = db.execute(
                "SELECT requests, tokens FROM tenant_daily WHERE day=? AND tenant_id=?",
                (day, settings.tenant_id),
            ).fetchone() or (0, 0)
            if tenant[0] + attempts > settings.tenant_requests or tenant[1] + tokens > settings.tenant_tokens:
                raise QuotaError("当前客户标识的今日请求/token 额度已达上限，其他客户额度不因此扣减。")
            db.execute(
                "INSERT OR REPLACE INTO tenant_daily VALUES (?, ?, ?, ?)",
                (day, settings.tenant_id, tenant[0] + attempts, tenant[1] + tokens),
            )
            db.execute(
                "INSERT OR REPLACE INTO daily VALUES (?, ?, ?, ?)",
                (day, row[0] + attempts, row[1] + tokens, row[2] + usd),
            )
            db.execute("DELETE FROM daily WHERE day < date(?, '-30 days')", (day,))
            db.execute("DELETE FROM tenant_daily WHERE day < date(?, '-30 days')", (day,))
    except (OSError, sqlite3.Error) as exc:
        raise QuotaError("无法读取共享配额存储，已停止模型请求；请联系部署管理员。") from exc


def record_usage(
    settings: LLMSettings, input_tokens: int | None, output_tokens: int | None, estimated_usd: float | None
) -> bool:
    """Aggregate returned usage by opaque deployment tenant; never claim invoice-level accounting."""
    path = Path(os.getenv("QUOTA_DB_PATH", "runtime/quota.sqlite3"))
    day = datetime.now(ZoneInfo("Asia/Hong_Kong")).date().isoformat()
    try:
        with closing(sqlite3.connect(path, timeout=5)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS usage_daily (day TEXT, tenant_id TEXT, measured_responses INTEGER, input_tokens INTEGER, output_tokens INTEGER, estimated_usd REAL, PRIMARY KEY(day, tenant_id))"
            )
            if input_tokens is None or output_tokens is None:
                return True
            db.execute(
                "INSERT INTO usage_daily VALUES (?, ?, 1, ?, ?, ?) ON CONFLICT(day, tenant_id) DO UPDATE SET measured_responses=measured_responses+1, input_tokens=input_tokens+excluded.input_tokens, output_tokens=output_tokens+excluded.output_tokens, estimated_usd=estimated_usd+excluded.estimated_usd",
                (day, settings.tenant_id, input_tokens, output_tokens, estimated_usd),
            )
            db.execute("DELETE FROM usage_daily WHERE day < date(?, '-30 days')", (day,))
        return True
    except (OSError, sqlite3.Error):
        return False
