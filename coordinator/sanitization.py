"""Conservative text sanitization before optional external-model calls.

Pattern masking is defense-in-depth, not a guarantee that text is anonymous.
The routing policy must keep ERP/document-bound prompts on local paths.
"""
import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL_REDACTED]"),
    # International and common Iranian phone formats
    (re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)"), "[PHONE_OR_ID_REDACTED]"),
    (re.compile(r"(?<!\d)\d{10,16}(?!\d)"), "[NUMBER_ID_REDACTED]"),
)


def sanitize_for_external_model(text: str) -> str:
    """Mask common direct identifiers; callers must enforce the routing policy too."""
    sanitized = text
    for pattern, replacement in _PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized
