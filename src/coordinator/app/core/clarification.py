# src/coordinator/app/core/clarification.py
"""تشخیص ابهام سؤال کاربر برای پرسیدن سؤال تکمیلی (clarification).

دو لایه:
  ۱. heuristic محافظه‌کارانه — فقط واضح‌ترین موارد مبهم را می‌گیرد.
  ۲. LLM-based — فقط برای موارد مرزی ("uncertain") اجرا می‌شود.

قواعد طراحی:
  - اگر سؤال به سؤال قبلی مکالمه مربوط است، heuristic آن را مبهم اعلام نمی‌کند
    و تصمیم را به LLM می‌سپارد.
  - سؤال‌های erp_write هرگز clarification نمی‌گیرند (این در workflow چک می‌شود).
  - خروجی heuristic: "clear" | "ambiguous" | "uncertain"

بک لاگ: فعلاً توابع این کلاس در workflow پیاده سازی شده اند و بعداً از این کلاس هم استفاده خواهم کرد. 
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)

ClarificationDecision = Literal["clear", "ambiguous", "uncertain"]

# کلماتی که نشان می‌دهند سؤال به دامنه‌ی مشخصی اشاره دارد.
_DOMAIN_KEYWORDS = (
    "فاکتور", "سفارش", "موجودی", "انبار", "خرید", "فروش", "مشتری",
    "کارمند", "حقوق", "گزارش", "مستند", "راهنما", "آیین", "رویه",
    "سیاست", "فرآیند", "فرایند", "دستورالعمل", "قرارداد",
    "erp", "invoice", "order", "inventory", "customer", "stock",
    "employee", "payroll", "policy", "procedure", "report", "document",
)

# کلماتی که در جمله‌ی کوتاه بدون زمینه، نشانه‌ی ابهام‌اند.
_AMBIGUOUS_WORDS = (
    "این", "آن", "اون", "اینو", "اونو", "این یکی", "اون یکی",
    "چیه", "چیست", "چیکار", "چی کار", "چه کار", "چطوره",
)

# کلمات پرسشی که اگر با موضوع مشخص نیایند، نشانه‌ی ابهام‌اند.
_VAGUE_QUESTION_WORDS = (
    "چطور", "چگونه", "روش", "مراحل", "کمک", "راهنمایی",
)


def _tokens(text: str) -> list[str]:
    return [t for t in text.strip().casefold().replace("\u200c", " ").split() if t]


def heuristic_decision(question: str, has_history: bool) -> ClarificationDecision:
    """تصمیم محافظه‌کارانه. فقط موارد واضح را مبهم اعلام می‌کند."""
    text = question.strip()
    lower = text.casefold().replace("\u200c", " ")
    tokens = _tokens(text)

    if not tokens:
        return "ambiguous"

    # ۱. خیلی کوتاه و بدون کلمه‌ی دامنه
    if len(tokens) <= 2:
        if not any(k in lower for k in _DOMAIN_KEYWORDS):
            return "ambiguous"
        return "clear"

    # ۲. کلمات مبهم
    has_ambiguous_word = any(w in lower for w in _AMBIGUOUS_WORDS)
    if has_ambiguous_word:
        if not has_history:
            return "ambiguous"
        # اگر history هست، ممکن است به سؤال قبلی ربط داشته باشد → LLM
        return "uncertain"

    # ۳. سؤال چندوجهی بدون تفکیک (حداقل ۲ «و» یا ۲ «یا»)
    if lower.count(" و ") >= 2 or lower.count(" یا ") >= 2:
        if len(tokens) < 15:
            return "uncertain"

    # ۴. کلمات پرسشی مبهم بدون موضوع مشخص
    has_vague_q = any(w in lower for w in _VAGUE_QUESTION_WORDS)
    has_domain = any(k in lower for k in _DOMAIN_KEYWORDS)
    if has_vague_q and not has_domain:
        return "uncertain"

    # ۵. طولانی و حاوی کلمه‌ی دامنه → واضح
    if len(tokens) >= 15 and has_domain:
        return "clear"

    # ۶. حاوی کلمه‌ی دامنه → واضح
    if has_domain:
        return "clear"

    # ۷. بقیه → LLM تصمیم بگیرد
    return "uncertain"


def _format_history(history: list[tuple[str, str]], max_chars: int = 2000) -> str:
    """تاریخچه را برای prompt آماده می‌کند. آخرین پیام‌ها اولویت دارند."""
    if not history:
        return "(بدون تاریخچه)"
    parts: list[str] = []
    for role, text in history[-6:]:
        label = "کاربر" if role == "user" else "دستیار"
        parts.append(f"{label}: {text[:400]}")
    joined = "\n".join(parts)
    return joined[-max_chars:]


CLARIFICATION_PROMPT = """تو یک دستیار ERP هستی. وظیفه‌ات فقط تشخیص «آیا سؤال کاربر به اندازه‌ی کافی واضح است تا پاسخ دقیق بدهیم؟» است.

قواعد:
- اگر سؤال مبهم است و پاسخ دقیق نیاز به اطلاعات بیشتر دارد، حداکثر {max_q} سؤال کوتاه و آزاد بپرس (هر کدام یک خط).
- اگر سؤال واضح است، چیزی نپرس.
- اگر سؤال به مکالمه‌ی قبلی مربوط است، با توجه به آن زمینه ارزیابی کن. پیام دستیار با برچسب «[دستیار سؤال تکمیلی پرسید]» یعنی نوبت قبل منتظر شفاف‌سازی بوده‌ایم؛ اگر کاربر الان جواب داده، معمولاً کافی است.
- خودت پاسخ نده.
- هیچ توضیح اضافه‌ای بیرون از JSON نده.

خروجی JSON:
{{"sufficient": true}}
یا
{{"sufficient": false, "questions": ["...", "..."]}}

مکالمه‌ی قبلی:
{history}

سؤال کاربر: {question}
خروجی:"""


def parse_llm_decision(raw: str, max_questions: int) -> tuple[bool, list[str]]:
    """پارس مقاوم خروجی LLM. در صورت شکست، محافظه‌کارانه 'sufficient=True'."""
    if not raw:
        return True, []
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return True, []
        parsed = json.loads(raw[start:end + 1])
    except (ValueError, json.JSONDecodeError):
        return True, []
    if not isinstance(parsed, dict):
        return True, []
    sufficient = parsed.get("sufficient")
    if sufficient is True:
        return True, []
    if sufficient is False:
        questions_raw = parsed.get("questions") or []
        if not isinstance(questions_raw, list):
            return True, []
        questions = [str(q).strip() for q in questions_raw if str(q).strip()]
        if not questions:
            # sufficient=False ولی سؤالی ندارد → محافظه‌کارانه واضح فرض کن
            return True, []
        return False, questions[:max_questions]
    return True, []


def build_llm_chain(settings_obj: Any):
    """ساخت chain برای LLM-based check. importها داخل تابع تا از circular import جلوگیری شود."""
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_ollama import ChatOllama

    llm = ChatOllama(
        model=settings_obj.local_llm_model,
        base_url=settings_obj.ollama_base_url,
        temperature=0,
        num_predict=settings_obj.clarification_num_predict,
    )
    return llm | StrOutputParser()


async def llm_decision(
    question: str,
    history: list[tuple[str, str]],
    *,
    max_questions: int,
    llm_chain,
) -> tuple[bool, list[str]]:
    """تصمیم LLM-based. در صورت خطا، محافظه‌کارانه واضح فرض می‌کند."""
    prompt = CLARIFICATION_PROMPT.format(
        max_q=max_questions,
        history=_format_history(history),
        question=question[:2000],
    )
    try:
        raw = await llm_chain.ainvoke(prompt)
    except Exception:
        logger.warning("Clarification LLM failed; defaulting to sufficient=True")
        return True, []
    return parse_llm_decision(raw, max_questions)