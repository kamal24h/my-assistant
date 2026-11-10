# src/coordinator/app/routing/keyword_fallback.py
"""Deterministic keyword fallback for intent classification.

Used when structured LLM output is unavailable or throws. Precedence:
  1. Empty input -> AMBIGUOUS
  2. Small talk -> SMALL_TALK
  3. Procedural wording -> DOCUMENT_QUERY
  4. Explicit ERP write -> ERP_ACTION
  5. Actual ERP data hints -> ERP_DATA_QUERY
  6. Default -> DOCUMENT_QUERY (preserves safe, RAG-first behavior)

Note on normalization:
  - Persian ZWNJ (U+200C) is converted to a regular space in `_normalize_fa`.
  - Pattern texts MUST therefore use `\\s*` (or plain spaces) instead of ZWNJ,
    otherwise the regex won't match after normalization.
"""
from __future__ import annotations

import re

from app.routing.intent_schemas import IntentDecision


def _normalize_fa(text: str) -> str:
    """Normalize Persian/Arabic character and whitespace variants.

    - ي -> ی, ك -> ک
    - ZWNJ (U+200C) -> space
    - remove Arabic diacritics
    - collapse whitespace
    """
    text = (text or "").casefold().replace("ي", "ی").replace("ك", "ک")
    text = text.replace("\u200c", " ")
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_small_talk(text: str) -> bool:
    """Conservative small-talk detector.

    True only for greetings/thanks/farewells, and only when the prompt
    does not also contain an identifier or entity hint.
    """
    normalized = _normalize_fa(text)
    if not normalized:
        return True
    # If an identifier or an ERP entity is present, it's not small talk.
    if _has_identifier(normalized) or _has_entity_hint(normalized):
        return False

    exact = {
        "سلام", "درود", "صبح بخیر", "وقت بخیر", "خسته نباشید",
        "ممنون", "متشکرم", "سپاس", "خداحافظ", "شب بخیر",
    }
    if normalized in exact:
        return True

    # Allow a short trailing phrase after the greeting.
    prefixes = ("سلام ", "درود ", "ممنون ", "متشکرم ", "وقت بخیر ")
    return any(
        normalized.startswith(p) and len(normalized) <= len(p) + 20
        for p in prefixes
    )


# ---------- Entity / identifier helpers ----------
_ID_PATTERNS = (
    re.compile(r"\b(?:SO|PO|INV|ORD|PR)-?\d{3,}\b", re.I),
    re.compile(r"\b\d{4,}\b"),
    # حذف شد: `[\w۰-۹0-9]{4,}` خیلی گسترده بود و هر متن ۴+ کاراکتری (شامل
    # کلمات فارسی مثل «سلام») را به عنوان identifier شناسایی می‌کرد.
)
_ENTITY_HINTS = (
    "سفارش", "فاکتور", "درخواست", "محصول", "کالا", "انبار", "مشتری",
    "order", "invoice", "product", "item",
)


def _has_identifier(text: str) -> bool:
    return any(p.search(text) for p in _ID_PATTERNS)


def _has_entity_hint(text: str) -> bool:
    lowered = text.casefold()
    return any(h in lowered for h in _ENTITY_HINTS)


# ---------- Explicit write commands ----------
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


# ---------- ERP data hints ----------
_DATA_PATTERNS = (
    r"وضعیت\s+(?:فاکتور|سفارش|درخواست|خرید|تولید)",
    r"(?:فاکتور|سفارش|درخواست)\s+(?:شماره|#)\s*[\w۰-۹0-9-]+",
    r"موجودی\s+(?:فعلی|امروز|انبار|کالا)",
    r"آخرین\s+(?:فاکتور|سفارش|درخواست|تراکنش)",
    r"اطلاعات\s+(?:ثبت\s+شده|مشتری|کاربر)",
    r"مشتری\s+(?:شماره|با\s+کد)\s*[\w۰-۹0-9-]+",
)


# ---------- Documentation/procedure hints ----------
# IMPORTANT: ZWNJ is converted to space by _normalize_fa; use `\s*` or
# plain spaces here, never ZWNJ.
_DOC_PATTERNS = (
    r"چطور(?:\s*می\s*توانم|\s*میتوانم)?",
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


def _match_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, text) for p in patterns)


# ---------- Public API ----------
def keyword_fallback(question: str) -> IntentDecision:
    """Return a deterministic IntentDecision.

    Precedence:
      1. empty -> AMBIGUOUS
      2. small talk -> SMALL_TALK
      3. procedural wording -> DOCUMENT_QUERY
      4. explicit write -> ERP_ACTION
      5. actual ERP data hints -> ERP_DATA_QUERY
      6. default -> DOCUMENT_QUERY
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

    if _is_small_talk(text):
        return IntentDecision(
            intent="SMALL_TALK",
            routes=["local_llm"],
            confidence=0.99,
            reasoning="پیام از نوع گفت‌وگوی کوتاه است.",
        )

    # Documentation takes precedence over ERP entity names.
    if _match_any(text, _DOC_PATTERNS):
        return IntentDecision(
            intent="DOCUMENT_QUERY",
            routes=["local_rag"],
            confidence=0.88,
            reasoning="پرسش درباره روش، مراحل یا دستورالعمل است.",
        )

    if _match_any(text, _WRITE_PATTERNS):
        return IntentDecision(
            intent="ERP_ACTION",
            routes=["erp_write"],
            confidence=0.86,
            reasoning="فعل صریح برای تغییر یا اجرای عملیات ERP وجود دارد.",
        )

    if _match_any(text, _DATA_PATTERNS):
        return IntentDecision(
            intent="ERP_DATA_QUERY",
            routes=["local_mcp"],
            confidence=0.86,
            reasoning="پرسش درباره وضعیت یا مقدار یک رکورد واقعی ERP است.",
        )

    return IntentDecision(
        intent="DOCUMENT_QUERY",
        routes=["local_rag"],
        confidence=0.55,
        reasoning=(
            "نشانه قطعی برای MCP یا گفت‌وگوی عمومی وجود ندارد؛ "
            "مسیر پیش‌فرض RAG است."
        ),
    )