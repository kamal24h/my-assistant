"""Deterministic, defense-in-depth guardrails for the ERP assistant pipeline.

These controls are not a substitute for ERP authorization, source ACL filtering, or human review.
They deliberately avoid logging raw prompts, model outputs, or business payloads.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Indicators that a prompt may be attempting instruction override or secret extraction.
_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.I),
    re.compile(r"(?:reveal|print|show|repeat|output)\s+(?:your\s+)?(?:system prompt|developer message|hidden instructions)", re.I),
    re.compile(r"(?:افش[اا]|نمایش بده|چاپ کن|بازگو کن).{0,35}(?:پرامپت سیستم|دستورهای داخلی|کلید api|رمز عبور)", re.I),
    re.compile(r"(?:system prompt|developer message).{0,40}(?:ignore|override|bypass)", re.I),
)
_ENTERPRISE_PATTERNS = (
    re.compile(r"\b(?:erp|invoice|purchase order|sales order|inventory|stock|payroll|customer record|employee record|internal data|company policy|internal document|employee data|customer data)\b", re.I),
    re.compile(r"(?:موجودی|فاکتور|سفارش خرید|سفارش فروش|درخواست خرید|حقوق و دستمزد|اطلاعات مشتری|اطلاعات کارمند|داده داخلی|مستندات داخلی|مستندات سازمانی|راهنمای داخلی|سیاست سازمان|رویه سازمان|در سیستم)", re.I),
)
_PII_PATTERNS = (
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)"),
    re.compile(r"(?<!\d)\d{10,16}(?!\d)"),
)
_SECRET_REQUEST_PATTERNS = (
    re.compile(r"\b(?:api[_ -]?key|access[_ -]?token|password|secret key|private key)\b", re.I),
    re.compile(r"(?:کلید api|توکن دسترسی|رمز عبور|کلید خصوصی|اطلاعات محرمانه احراز هویت)", re.I),
)
_SECRET_VALUE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"), "Bearer [REDACTED]"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.S), "[PRIVATE_KEY_REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[API_KEY_REDACTED]"),
    (re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"]?[^\s,;\"']{8,}"), "[SECRET_REDACTED]"),
)
_SENSITIVE_FIELD = re.compile(r"(?:password|passwd|secret|token|authorization|api[_-]?key|access[_-]?key|private[_-]?key|credential)", re.I)


@dataclass(frozen=True)
class InputAssessment:
    force_local: bool
    injection_suspected: bool
    enterprise_data: bool
    pii_detected: bool
    secret_request: bool


def assess_input(text: str) -> InputAssessment:
    injection = any(p.search(text) for p in _INJECTION_PATTERNS)
    enterprise = any(p.search(text) for p in _ENTERPRISE_PATTERNS)
    pii = any(p.search(text) for p in _PII_PATTERNS)
    secret_request = any(p.search(text) for p in _SECRET_REQUEST_PATTERNS)
    # Never route enterprise/PII/injection/credential-related prompts to an external model.
    return InputAssessment(
        force_local=bool(injection or enterprise or pii or secret_request),
        injection_suspected=injection,
        enterprise_data=enterprise,
        pii_detected=pii,
        secret_request=secret_request,
    )


def redact_secrets(text: str, max_chars: int = 16000) -> str:
    value = text[:max_chars]
    for pattern, replacement in _SECRET_VALUE_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def sanitize_tool_payload(value: Any, *, max_chars: int = 12000) -> Any:
    """Redact secret-like fields and bound tool payload size before model summarization."""
    def walk(item: Any, depth: int = 0) -> Any:
        if depth > 8:
            return "[MAX_DEPTH_REACHED]"
        if isinstance(item, dict):
            result: dict[str, Any] = {}
            for key, child in item.items():
                key_text = str(key)
                result[key_text] = "[REDACTED]" if _SENSITIVE_FIELD.search(key_text) else walk(child, depth + 1)
            return result
        if isinstance(item, list):
            return [walk(child, depth + 1) for child in item[:200]]
        if isinstance(item, str):
            return redact_secrets(item, max_chars=4000)
        if isinstance(item, (int, float, bool)) or item is None:
            return item
        return str(item)[:1000]

    sanitized = walk(value)
    # Bound the total serialized representation, even if nested strings are numerous.
    import json
    encoded = json.dumps(sanitized, ensure_ascii=False, default=str)
    if len(encoded) <= max_chars:
        return sanitized
    return {"_truncated": True, "preview": encoded[:max_chars]}


def guard_output(text: str, max_chars: int = 16000) -> tuple[str, list[str]]:
    """Redact credential-shaped output and enforce a bounded response length."""
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


def block_secret_exfiltration(text: str) -> bool:
    """Block explicit requests to reveal internal prompts or authentication secrets."""
    # Do not block every prompt-injection discussion; block only explicit extraction attempts.
    if re.search(r"(?i)(?:reveal|show|print|repeat|output|افشا|نمایش بده|چاپ کن|بازگو کن).{0,50}(?:system prompt|developer message|hidden instructions|پرامپت سیستم|دستورهای داخلی)", text):
        return True
    if any(p.search(text) for p in _SECRET_REQUEST_PATTERNS):
        # Credential-related questions may be legitimate general questions; only block extraction verbs.
        extraction = re.search(
            r"(?i)(?:reveal|show|print|dump|give me|output|افشا|نمایش بده|چاپ کن|بده).{0,50}(?:api[_ -]?key|access[_ -]?token|password|secret key|private key|کلید api|توکن دسترسی|رمز عبور|کلید خصوصی)",
            text,
        )
        return bool(extraction)
    return False
