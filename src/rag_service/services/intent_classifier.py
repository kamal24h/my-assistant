# services/intent_classifier.py
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# الگوهای پیام‌های عمومی که نیازی به RAG ندارند
_GREETING_PATTERNS = [
    r"^(سلام|درود|وقت بخیر|صبح بخیر|ظهر بخیر|عصر بخیر|شب بخیر)[\s!?.]*$",
    r"^(hi|hello|hey|greetings)[\s!?.]*$",
]

_THANKS_PATTERNS = [
    r"^(ممنون|مرسی|متشکرم|سپاس|دستت درد نکنه|لطف کردی)[\s!?.]*$",
    r"^(thanks|thank you|thx)[\s!?.]*$",
]

_GOODBYE_PATTERNS = [
    r"^(خداحافظ|خدا نگهدار|فعلا|بای)[\s!?.]*$",
    r"^(bye|goodbye|see you)[\s!?.]*$",
]

_ACK_PATTERNS = [
    r"^(باشه|اوکی|درسته|فهمیدم|متوجه شدم|حله|آره|بله|نه|خیر)[\s!?.]*$",
    r"^(ok|okay|got it|understood|sure|yes|no)[\s!?.]*$",
]

# ترکیب همه الگوها
_ALL_PATTERNS = (
    _GREETING_PATTERNS
    + _THANKS_PATTERNS
    + _GOODBYE_PATTERNS
    + _ACK_PATTERNS
)


def is_small_talk(question: str) -> bool:
    """
    تشخیص می‌دهد آیا پیام کاربر «گفتگوی عمومی» است (سلام، تشکر، خداحافظی، تأیید).
    اگر True برگرداند، نیازی به RAG نیست و مستقیماً به LLM می‌رود.
    """
    if not question or not question.strip():
        return True

    normalized = question.strip().lower()

    # اگر پیام خیلی کوتاه است (مثلاً ۱-۲ کلمه) و شامل کلمات سؤال نیست، احتمالاً small talk است
    if len(normalized) <= 3:
        return True

    for pattern in _ALL_PATTERNS:
        if re.match(pattern, normalized, re.IGNORECASE):
            logger.info("Small talk detected: %r", question[:50])
            return True

    return False