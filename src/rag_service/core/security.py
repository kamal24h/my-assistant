# src/rag_service/core/security.py
import logging
import secrets
from typing import Optional

from fastapi import Header, HTTPException, status

from core.config import settings

logger = logging.getLogger(__name__)


def require_api_key(
    x_api_key: Optional[str] = Header(default=None, alias=settings.api_key_header_name),
) -> None:
    """
    Dependency برای محافظت از endpoints با API Key ثابت.

    - کلید از هدر `X-API-Key` خوانده می‌شود.
    - اگر settings.api_key خالی باشد → 500 (configuration error).
    - اگر کلید غایب یا اشتباه باشد → 401.
    - مقایسه با secrets.compare_digest انجام می‌شود (ضد timing attack).
    - کلید هرگز لاگ نمی‌شود.
    """
    expected = (settings.api_key or "").strip()

    if not expected:
        # خطای پیکربندی، نه خطای کاربر.
        logger.error(
            "API_KEY is not configured. Refusing to serve protected endpoints."
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="سرور به‌درستی پیکربندی نشده است.",
        )

    provided = (x_api_key or "").strip()
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="کلید API غایب است.",
        )

    if not secrets.compare_digest(provided, expected):
        logger.warning("Invalid API key attempt from client.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="کلید API نامعتبر است.",
        )