from __future__ import annotations

import re

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_PATTERN = re.compile(r"\+?\d[\d\s\-()]{7,}\d")

_MASK = "***"


def mask_pii(value: str) -> str:
    result = _EMAIL_PATTERN.sub(f"{_MASK}@{_MASK}", value)
    result = _PHONE_PATTERN.sub(_MASK, result)
    return result


def sanitize_log_data(data: dict[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = mask_pii(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_log_data(value)  # type: ignore[arg-type]
        else:
            sanitized[key] = value
    return sanitized
