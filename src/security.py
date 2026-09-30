"""Shared-password access gate for small controlled deployments, not enterprise identity."""

import hashlib
import hmac
import os


def production() -> bool:
    return os.getenv("APP_ENV", "development") == "production"


def verify_password(candidate: str) -> bool:
    expected = os.getenv("APP_ACCESS_PASSWORD", "")
    return bool(expected) and hmac.compare_digest(candidate.encode(), expected.encode())


def password_version() -> str:
    return hashlib.sha256(os.getenv("APP_ACCESS_PASSWORD", "").encode()).hexdigest()
