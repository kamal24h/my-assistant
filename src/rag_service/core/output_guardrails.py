"""Small local output guard for the standalone RAG service.

Kept service-local so the RAG container does not depend on importing Coordinator code.
Keep its secret patterns aligned with Coordinator guardrails during future shared-policy refactoring.
"""
from __future__ import annotations
import re

_SECRET_VALUE_PATTERNS = (
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"), "Bearer [REDACTED]"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.S), "[PRIVATE_KEY_REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[API_KEY_REDACTED]"),
    (re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"]?[^\s,;\"']{8,}"), "[SECRET_REDACTED]"),
)

def guard_output(text: str, max_chars: int = 16000) -> tuple[str, list[str]]:
    flags: list[str] = []
    if re.search(r"تو یک دستیار هوشمند فارسی.?زبان برای کاربران سازمانی هستی", text, re.I):
        return "پاسخ به‌دلیل شناسایی محتوای داخلی نامناسب نمایش داده نشد.", ["internal_prompt_pattern_detected"]
    result = text
    for pattern, replacement in _SECRET_VALUE_PATTERNS:
        result, count = pattern.subn(replacement, result)
        if count:
            flags.append("secret_redacted")
    if len(result) > max_chars:
        result = result[:max_chars].rstrip() + "…"
        flags.append("output_truncated")
    return result, flags
