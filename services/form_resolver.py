# services/form_resolver.py
import json
import logging
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger(__name__)

_FORMS_PATH = Path(__file__).parent.parent / "data" / "menu_forms.json"

_FORMS: List[Dict] = []
_TITLE_TO_ID: Dict[str, int] = {}

# حروف عربی/فارسی برای نرمال‌سازی
_ARABIC_TO_PERSIAN = str.maketrans({
    "ي": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا", "آ": "ا",
    "ؤ": "و", "ئ": "ی",
})
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e"), None)


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = text.translate(_ARABIC_TO_PERSIAN)
    text = text.translate(_ZERO_WIDTH)       # حذف نیم‌فاصله/کاراکترهای نامرئی
    text = re.sub(r"[\u064B-\u065F]", "", text)  # حذف اعراب
    text = re.sub(r"[^\w\s]", " ", text)     # حذف علائم نگارشی
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _load_forms() -> None:
    global _FORMS, _TITLE_TO_ID
    if _FORMS:
        return
    try:
        with open(_FORMS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _FORMS = data
        _TITLE_TO_ID = {_normalize(item["title"]): int(item["id"]) for item in data}
        logger.info("Loaded %d forms from %s", len(_FORMS), _FORMS_PATH)
    except Exception as exc:
        logger.error("Failed to load menu_forms.json: %s", exc)
        _FORMS = []
        _TITLE_TO_ID = {}


def get_all_forms() -> List[Dict]:
    _load_forms()
    return _FORMS


def _match_exact_contains(norm_query: str) -> Optional[int]:
    """
    تطبیق قطعی: اگر عنوان نرمال‌شدهٔ یک فرم، در query باشد (کلمه‌ای)، id برمی‌گردد.
    طولانی‌ترین عنوان اول بررسی می‌شود تا تطبیق دقیق‌تر باشد.
    """
    sorted_titles = sorted(_TITLE_TO_ID.keys(), key=len, reverse=True)
    for title in sorted_titles:
        if not title:
            continue
        # تطبیق با مرز کلمه (چون نرمال‌سازی نیم‌فاصله را حذف کرده)
        pattern = r"(?<![\w])" + re.escape(title) + r"(?![\w])"
        if re.search(pattern, norm_query):
            return _TITLE_TO_ID[title]
    return None


def _match_fuzzy(norm_query: str, cutoff: float = 0.85) -> Optional[int]:
    """
    تطبیق فازی: با difflib، اگر شباهت کل query به یک عنوان خیلی بالا بود.
    برای queryهایی مثل «چطور فاکتور فروش صادر کنم؟» عنوان دقیق پیدا نمی‌شود،
    ولی اگر بخشی از query شبیه عنوان باشد، قابل استفاده است.
    """
    import difflib
    titles = list(_TITLE_TO_ID.keys())
    matches = difflib.get_close_matches(
        norm_query, titles, n=1, cutoff=cutoff
    )
    if matches:
        return _TITLE_TO_ID[matches[0]]
    return None


def resolve_form_id_simple(question: str) -> Optional[int]:
    """
    resolver قطعی بر اساس query کاربر.
    اول تطبیق contains، بعد fuzzy.
    """
    _load_forms()
    if not _FORMS:
        return None

    norm_q = _normalize(question)
    if not norm_q:
        return None

    # ۱. تطبیق contains
    fid = _match_exact_contains(norm_q)
    if fid is not None:
        return fid

    # ۲. تطبیق fuzzy
    fid = _match_fuzzy(norm_q)
    if fid is not None:
        return fid

    return None


def resolve_form_id_llm(
    question: str,
    answer: str,
    llm,
) -> Optional[int]:
    """
    resolver با LLM: فقط انتخاب از بین عناوین مجاز.
    خروجی فقط عنوان یا NONE است؛ id از نگاشت قطعی گرفته می‌شود.
    """
    _load_forms()
    if not _FORMS:
        return None

    titles_block = "\n".join(f"- {item['title']}" for item in _FORMS)

    prompt = f"""لیست فرم‌های نرم‌افزار:
{titles_block}

سؤال کاربر:
{question}

پاسخ دستیار:
{answer}

اگر سؤال کاربر مستقیماً به یکی از فرم‌های بالا مربوط است، دقیقاً همان عنوان را از لیست بالا (کلمه‌به‌کلمه) برگردان. اگر مربوط نیست یا مطمئن نیستی، فقط کلمه NONE را برگردان. هیچ متن دیگری ننویس.
"""

    try:
        raw = llm.invoke(prompt).content.strip()
    except Exception as exc:
        logger.warning("LLM form resolver failed: %s", exc)
        return None

    if raw.upper() == "NONE" or not raw:
        return None

    norm_raw = _normalize(raw)
    # به دنبال تطبیق دقیق عنوان در خروجی LLM
    for title in _TITLE_TO_ID.keys():
        if norm_raw == title or title in norm_raw:
            return _TITLE_TO_ID[title]

    logger.info("LLM returned unknown form title: %s", raw)
    return None


def resolve_form_id(
    question: str,
    answer: Optional[str] = None,
    use_llm_fallback: bool = True,
) -> Optional[int]:
    """
    resolver ترکیبی:
    ۱. قطعی بر اساس question
    ۲. اگر answer داده شد، قطعی بر اساس answer
    ۳. اگر use_llm_fallback، با LLM
    """
    fid = resolve_form_id_simple(question)    
    if fid is not None:
        return fid

    if answer:
        fid = resolve_form_id_simple(answer)
        if fid is not None:
            return fid

    # ← فیلتر سبک قبل از LLM
    if use_llm_fallback:
        # اگر query خیلی کوتاه است، احتمالاً نامرتبط است
        if len(_normalize(question)) < 4:
            return None
        # یا: فقط اگر حداقل یک کلمه از عناوین در query باشد
    
        # LLM فقط وقتی صدا زده می‌شود که تطبیق قطعی شکست خورده باشد
        # برای جلوگیری از overhead، LLM سبک (همان مدل پاسخ) استفاده می‌شود
        from langchain_ollama import ChatOllama
        from config import settings
        llm = ChatOllama(
            model=settings.llm_model,
            base_url=settings.ollama_url,
            temperature=0.0,
        )
        return resolve_form_id_llm(question, answer or "", llm)

    return None