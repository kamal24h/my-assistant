# src/coordinator/app/services/sanitization.py
"""Conservative text sanitization before optional external-model calls.

Pattern masking is defense-in-depth, not a guarantee that text is anonymous.
The routing policy must keep ERP/document-bound prompts on local paths.
"""
import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL_REDACTED]"),
    # فقط شماره‌های تلفن با فرمت واضح: شروع با + یا ۰۹ یا ۹ رقم پیوسته پس از پیشوند
    (re.compile(r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:0\d{2,4}[\s.-]?)?\d{7,8}(?!\w)"), "[PHONE_OR_ID_REDACTED]"),
    # شناسه‌های عددی پیوسته ۱۰ تا ۱۶ رقم (کد ملی/کارت/شناسه)
    (re.compile(r"(?<!\d)\d{10,16}(?!\d)"), "[NUMBER_ID_REDACTED]"),
)


def sanitize_for_external_model(text: str) -> str:
    """Mask common direct identifiers; callers must enforce the routing policy too."""
    sanitized = text
    for pattern, replacement in _PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized