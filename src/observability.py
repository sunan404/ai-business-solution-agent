"""Allowlisted JSON events without source text, filenames, secrets or exception bodies."""

import json
import logging
from datetime import datetime, timezone

LOGGER = logging.getLogger("business_diagnosis")
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)

ALLOWED = {
    "request_id",
    "category",
    "duration_ms",
    "input_chars",
    "input_tokens",
    "output_tokens",
    "estimated_usd",
    "attempts_reserved",
    "exception_type",
}


def event(name: str, **fields: str | int | float | None) -> None:
    record = {key: value for key, value in fields.items() if key in ALLOWED}
    LOGGER.info(
        json.dumps(
            {"event": name, "time": datetime.now(timezone.utc).isoformat(), **record}, ensure_ascii=False
        )
    )
