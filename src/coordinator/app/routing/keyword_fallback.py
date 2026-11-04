# src/coordinator/app/routing/keyword_fallback.py

from __future__ import annotations

import re

from .intent_schemas import IntentDecision


def _normalize_fa(text: str) -> str:
    """Normalize common Persian/Arabic character and whitespace variants."""
    text = (text or "").casefold().replace("ي", "ی").replace("ك", "ک")
    text = text.replace("\u200c", " ")
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_small_talk(text: str) -> bool:
    exact = {
        "سلام",
        "درود",
        "صبح بخیر",
        "وقت بخیر",
        "خسته نباشید",
        "ممنون",
        "متشکرم",
        "سپاس",
        "خداحافظ",
        "شب بخیر",
    }

    return text in exact or any(
        text.startswith(prefix) and len(text) <= len(prefix) + 12
        for prefix in ("سلام ", "درود ", "ممنون ", "متشکرم ")
    )


# Explicit change commands only.
# Bare ERP nouns must never trigger write operations.
_WRITE_PATTERNS = (
    r"ثبت\s+کن",
    r"ایجاد\s+کن",
    r"بساز",
    r"ویرایش\s+کن",
    r"به.?روزرسانی\s+کن",
    r"حذف\s+کن",
    r"پاک\s+کن",
    r"ارسال\s+کن",
    r"تایید\s+کن",
    r"تأیید\s+کن",
    r"رد\s+کن",
    r"ابطال\s+کن",
    r"لغو\s+کن",
    r"اجرا\s+کن",
)


# Strong indicators of requests for actual ERP records or values.
_DATA_PATTERNS = (
    r"وضعیت\s+(?:فاکتور|سفارش|درخواست|خرید|تولید)",
    r"(?:فاکتور|سفارش|درخواست)\s+(?:شماره|#)\s*[\w۰-۹0-9-]+",
    r"موجودی\s+(?:فعلی|امروز|انبار|کالا)",
    r"آخرین\s+(?:فاکتور|سفارش|درخواست|تراکنش)",
    r"اطلاعات\s+(?:ثبت\s+شده|مشتری|کاربر)",
    r"مشتری\s+(?:شماره|با\s+کد)\s*[\w۰-۹0-9-]+",
)


# Indicators of internal documentation or procedural questions.
# These take precedence over ERP entity names.
_DOC_PATTERNS = (
    r"چطور(?:\s+می‌توانم|\s+میتوانم)?",
    r"چگونه",
    r"مراحل",
    r"نحوه",
    r"روش\s+(?:ثبت|صدور|ابطال|تایید|تأیید|حذف)",
    r"رویه",
    r"دستورالعمل",
    r"آیین\s*نامه",
    r"طبق\s+مستند",
    r"در\s+مستند",
    r"چه\s+کسی\s+مجاز",
    r"قوانین\s+(?:شرکت|سازمان)",
    r"فرآیند|فرایند",
)


def keyword_fallback(question: str) -> IntentDecision:
    """
    Conservative fallback for when the semantic model is unavailable.

    Priority:
    1. Empty input
    2. Small talk
    3. Document/procedure questions
    4. Explicit ERP write actions
    5. Actual ERP data queries
    6. Default to Local RAG
    """

    text = _normalize_fa(question)

    if not text:
        return IntentDecision(
            intent="AMBIGUOUS",
            routes=["clarification"],
            confidence=0.0,
            reasoning="درخواست خالی است.",
            needs_clarification=True,
            clarification_question="لطفاً درخواست خود را توضیح دهید.",
        )

    # Small talk → Local LLM
    if _is_small_talk(text):
        return IntentDecision(
            intent="SMALL_TALK",
            routes=["local_llm"],
            confidence=0.99,
            reasoning="پیام از نوع گفت‌وگوی کوتاه است.",
        )

    # Procedural wording takes precedence over ERP entity words.
    # Example: "فاکتور فروش چگونه صادر می‌شود؟" → Local RAG
    if any(re.search(pattern, text) for pattern in _DOC_PATTERNS):
        return IntentDecision(
            intent="DOCUMENT_QUERY",
            routes=["local_rag"],
            confidence=0.88,
            reasoning="پرسش درباره روش، مراحل یا دستورالعمل است.",
        )

    # Explicit ERP write request → ERP Write
    if any(re.search(pattern, text) for pattern in _WRITE_PATTERNS):
        return IntentDecision(
            intent="ERP_ACTION",
            routes=["erp_write"],
            confidence=0.86,
            reasoning="فعل صریح برای تغییر یا اجرای عملیات ERP وجود دارد.",
        )

    # Actual ERP record/status query → MCP
    if any(re.search(pattern, text) for pattern in _DATA_PATTERNS):
        return IntentDecision(
            intent="ERP_DATA_QUERY",
            routes=["local_mcp"],
            confidence=0.86,
            reasoning="پرسش درباره وضعیت یا مقدار یک رکورد واقعی ERP است.",
        )

    # Default → Local RAG
    # This preserves the previous safe behavior for internal/company questions.
    return IntentDecision(
        intent="DOCUMENT_QUERY",
        routes=["local_rag"],
        confidence=0.55,
        reasoning=(
            "نشانه قطعی برای MCP یا گفت‌وگوی عمومی وجود ندارد؛ "
            "مسیر پیش‌فرض RAG است."
        ),
    )