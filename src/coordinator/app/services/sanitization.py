# src/rag_service/services/sanitization.py
"""Conservative text sanitization before external-model calls."""
import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL_REDACTED]"),
    (re.compile(r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:0\d{2,4}[\s.-]?)?\d{7,8}(?!\w)"), "[PHONE_OR_ID_REDACTED]"),
    (re.compile(r"(?<!\d)\d{10,16}(?!\d)"), "[NUMBER_ID_REDACTED]"),
)


def sanitize_for_external_model(text: str) -> str:
    sanitized = text
    for pattern, replacement in _PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized