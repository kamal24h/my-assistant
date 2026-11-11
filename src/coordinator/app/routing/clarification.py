# src/coordinator/app/routing/clarification.py
"""Rule-based clarification detection + heuristic reason extraction.

This module was previously inline in workflow.py. It is kept here so that
routing and clarification live in the same package and share keyword helpers.
"""
from __future__ import annotations

from app.core.config import settings
from app.routing.intent_schemas import IntentName
from app.routing.keyword_fallback import (
    _has_identifier,
    _has_entity_hint,
    _is_howto_question,
    _is_small_talk,
)


_REASON_HINTS = (
    "به دلیل", "به‌دلیل", "بخاطر", "به خاطر", "چون", "زیرا",
    "دلیل:", "دلیل :", "علت:", "علت :", "جهت", "به منظور",
    "برای اینکه", "because", "reason:", "due to",
)


def _has_reason_hint(text: str) -> bool:
    lowered = text.casefold()
    return any(hint in lowered for hint in _REASON_HINTS)


def _extract_reason(prompt: str, max_chars: int = 500) -> str:
    """Extract a short reason fragment from the prompt (heuristic)."""
    text = prompt.strip()
    if not text:
        return ""
    lowered = text.casefold()
    for hint in _REASON_HINTS:
        idx = lowered.find(hint)
        if idx < 0:
            continue
        fragment = text[idx:]
        for sep in (".", "،", "\n", "؛", "!", "?"):
            sep_idx = fragment.find(sep, len(hint))
            if sep_idx > 0:
                fragment = fragment[:sep_idx]
                break
        return fragment.strip()[:max_chars]
    return ""


def _needs_clarification(
    prompt: str,
    intent: IntentName,
) -> tuple[bool, list[str], str]:
    """Rule-based clarification for the non-LLM layer.

    Returns (needs, missing_fields, question).
    """
    text = prompt.strip()

    # 1. Small talk first (BEFORE length check).
    if intent == "SMALL_TALK" and _is_small_talk(text):
        return (False, [], "")

    # 2. Very short prompts.
    if len(text) < settings.clarification_min_prompt_chars:
        return (
            True,
            ["query"],
            "سؤالتان کوتاه است. لطفاً دقیق‌تر بگویید چه اطلاعاتی نیاز دارید "
            "(مثلاً وضعیت سفارش، موجودی کالا، یا ثبت درخواست خرید).",
        )

    # 3. How-to questions must go to RAG, never to clarification,
    #    even if they contain a write verb like "ثبت کنم".
    if settings.clarification_skip_howto_questions and _is_howto_question(text):
        return (False, [], "")

    # 4. ERP_ACTION without order_id / entity / reason.
    if intent == "ERP_ACTION":
        missing = []
        if not _has_identifier(text):
            missing.append("order_id")
        if not _has_entity_hint(text):
            missing.append("entity")
        has_reason = _has_reason_hint(text)
        if missing:
            pieces = []
            if "order_id" in missing:
                pieces.append("شماره سفارش/فاکتور")
            if "entity" in missing:
                pieces.append("نوع موجودیت (سفارش خرید، سفارش فروش، فاکتور و…)")
            if not has_reason:
                pieces.append("دلیل/توضیح مختصر")
            return (
                True,
                missing,
                "برای انجام این عملیات در ERP، لطفاً مشخص کنید: " + "، ".join(pieces) + ".",
            )

    # 5. ERP_DATA_QUERY without identifier / entity.
    if intent == "ERP_DATA_QUERY":
        if not _has_identifier(text) and not _has_entity_hint(text):
            return (
                True,
                ["entity_or_id"],
                "برای پاسخ به این سؤال، لطفاً مشخص کنید کدام کالا/سفارش/فاکتور مد نظر است "
                "(مثلاً نام کالا یا شماره سفارش).",
            )

    return (False, [], "")