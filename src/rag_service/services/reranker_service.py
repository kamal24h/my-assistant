# services/reranker_service.py
"""
سرویس مستقل Reranking با Cross-Encoder.

مدل: BAAI/bge-reranker-v2-m3 (چندزبانه، مناسب فارسی)

رفتار:
  - lazy load: مدل فقط در اولین استفاده بارگذاری می‌شود.
  - preload: می‌توانی در startup با `_ensure_reranker()` از قبل بارگذاری کنی.
  - fallback: اگر بارگذاری یا rerank شکست بخورد، لیست اصلی برگردانده می‌شود
    (RAG بدون rerank ادامه می‌دهد، سرویس کرش نمی‌کند).
"""
import logging
from typing import Any, List

logger = logging.getLogger(__name__)

_RERANKER = None
_RERANKER_INITIALIZED = False


def _get_reranker():
    """
    بارگذاری تنبل (lazy) مدل Cross-Encoder.
    اگر بارگذاری شکست بخورد، None برمی‌گردد.
    importها داخل تابع هستند تا در نبود پکیج، سرویس بالا بیاید.
    """
    try:
        from langchain_community.cross_encoders import HuggingFaceCrossEncoder
        from langchain_classic.retrievers.document_compressors import (
            CrossEncoderReranker,
        )
    except Exception as exc:
        logger.warning(
            "Reranker packages not available, skipping rerank: %s", exc
        )
        return None

    try:
        logger.info("Loading reranker model: BAAI/bge-reranker-v2-m3")
        # مدل چندزبانه، مناسب برای فارسی
        cross_encoder = HuggingFaceCrossEncoder(model_name="BAAI/bge-reranker-v2-m3")
        reranker = CrossEncoderReranker(model=cross_encoder, top_n=5)
        logger.info("Reranker model loaded successfully.")
        return reranker
    except Exception as exc:
        logger.warning("Failed to load reranker model: %s", exc)
        return None


def _ensure_reranker():
    """
    تضمین می‌کند مدل فقط یک بار بارگذاری شود (thread-safe نیست، ولی
    در context gunicorn با workerهای جداگانه مشکلی نیست).
    """
    global _RERANKER, _RERANKER_INITIALIZED
    if not _RERANKER_INITIALIZED:
        _RERANKER = _get_reranker()
        _RERANKER_INITIALIZED = True
    return _RERANKER


def rerank_documents(
    question: str,
    docs: List[Any],
    logger_override=None,
) -> List[Any]:
    """
    رتبه‌بندی مجدد اسناد بر اساس ارتباط با question.

    اگر مدل بارگذاری نشده باشد یا خطایی رخ دهد، لیست اصلی برگردانده می‌شود
    (degraded mode: RAG بدون rerank ادامه می‌دهد).

    Args:
        question: پرسش کاربر
        docs: لیست Document ها از Qdrant
        logger_override: لاگر اختیاری (برای تست یا override)

    Returns:
        لیست rerank‌شده (یا لیست اصلی در صورت خطا)
    """
    log = logger_override or logger
    reranker = _ensure_reranker()
    if reranker is None or not docs:
        return docs
    try:
        reranked = reranker.compress_documents(docs, question)
        log.info("Rerank: %d docs -> %d docs", len(docs), len(reranked))
        return reranked
    except Exception as exc:
        log.warning(
            "Rerank failed, falling back to original order: %s", exc
        )
        return docs