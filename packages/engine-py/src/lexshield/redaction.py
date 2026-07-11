"""Secret redaction per SPEC §9.6."""

from __future__ import annotations

import hashlib
import re
from typing import Any

# Frozen redaction patterns from SPEC §9.6
_AWS_KEY = re.compile(r"AKIA[0-9A-Z]{16}")
_API_KEY = re.compile(r"sk-(?:proj-)?[a-zA-Z0-9]{20,}")
_BEARER = re.compile(r"Bearer [A-Za-z0-9._\-]+")
_PASSWORD = re.compile(r"(?i)password\s*[:=]\s*\S+")
_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (_AWS_KEY, "[REDACTED_AWS_KEY]"),
    (_API_KEY, "[REDACTED_API_KEY]"),
    (_BEARER, "Bearer [REDACTED]"),
    (_PASSWORD, "password=[REDACTED]"),
]


def redact_string(value: str, *, redact_emails: str = "hash") -> tuple[str, list[str]]:
    """Apply regex redaction to a string.

    Args:
        value: Input string.
        redact_emails: ``hash`` (sha256 prefix), ``redact``, or ``off``.

    Returns:
        Tuple of (redacted string, list of redaction type labels applied).
    """
    redacted = value
    applied: list[str] = []

    for pattern, replacement in REDACTION_PATTERNS:
        if pattern.search(redacted):
            applied.append(replacement)
            redacted = pattern.sub(replacement, redacted)

    if redact_emails != "off" and _EMAIL.search(redacted):
        applied.append("email")

        def _replace_email(match: re.Match[str]) -> str:
            email = match.group(0)
            if redact_emails == "hash":
                digest = hashlib.sha256(email.encode()).hexdigest()[:12]
                return f"[EMAIL_HASH:{digest}]"
            return "[REDACTED_EMAIL]"

        redacted = _EMAIL.sub(_replace_email, redacted)

    return redacted, applied


def redact_value(value: Any, *, redact_emails: str = "hash") -> tuple[Any, list[str]]:
    """Recursively redact secrets in nested structures."""
    if isinstance(value, str):
        return redact_string(value, redact_emails=redact_emails)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        all_applied: list[str] = []
        for key, item in value.items():
            redacted_item, applied = redact_value(item, redact_emails=redact_emails)
            result[key] = redacted_item
            all_applied.extend(applied)
        return result, all_applied
    if isinstance(value, list):
        result_list: list[Any] = []
        all_applied = []
        for item in value:
            redacted_item, applied = redact_value(item, redact_emails=redact_emails)
            result_list.append(redacted_item)
            all_applied.extend(applied)
        return result_list, all_applied
    return value, []


def redact_arguments(
    arguments: dict[str, Any],
    *,
    redact_emails: str = "hash",
) -> tuple[dict[str, Any], list[str]]:
    """Redact secrets in tool call arguments."""
    redacted, applied = redact_value(arguments, redact_emails=redact_emails)
    return redacted, applied
