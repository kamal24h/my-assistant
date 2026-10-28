# src/rag_service/core/redis_client.py
import json
import logging
from typing import Optional, List, Dict, Any

import redis

from core.config import settings

logger = logging.getLogger(__name__)

redis_pool = redis.ConnectionPool(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password,
    decode_responses=True,
)


def get_redis_client() -> redis.Redis:
    return redis.Redis(connection_pool=redis_pool)


class ConversationCache:
    """
    مدیریت کش مکالمه در Redis.

    ساختار کلیدها:
      conv:{conv_id}:meta   -> JSON شامل app_id, tenant_id, user_id, user_name, tenant_desc, status
      conv:{conv_id}:turns  -> hash با field=message_id و value=JSON({"query","answer","duration","error","meta_info","liked","created_at"})

    منبع حقیقت: PostgreSQL.
    Redis صرفاً به‌عنوان کش سریع استفاده می‌شود. در صورت عدم دسترسی،
    سیستم باید بدون خطا به کار خود ادامه دهد.
    """

    # ---------- Meta ----------

    @staticmethod
    def create_conversation(
        redis_client: redis.Redis,
        conv_id: str,
        app_id: str,
        tenant_id: str,
        user_id: str,
        user_name: Optional[str] = None,
        tenant_desc: Optional[str] = None,
        ttl_seconds: int = settings.redis_ttl_seconds,
    ) -> None:
        key = f"conv:{conv_id}:meta"
        data = {
            "conversation_id": conv_id,
            "app_id": app_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "user_name": user_name,
            "tenant_desc": tenant_desc,
            "status": "active",
        }
        redis_client.set(key, json.dumps(data, ensure_ascii=False), ex=ttl_seconds)

    @staticmethod
    def get_conversation_meta(redis_client: redis.Redis, conv_id: str):
        key = f"conv:{conv_id}:meta"
        raw = redis_client.get(key)
        return json.loads(raw) if raw else None

    # ---------- Turns ----------

    @staticmethod
    def _turns_key(conv_id: str) -> str:
        return f"conv:{conv_id}:turns"

    @staticmethod
    def upsert_turn(
        redis_client: redis.Redis,
        conv_id: str,
        message_id: str,
        query: Optional[str] = None,
        answer: Optional[str] = None,
        duration: Optional[float] = None,
        error: Optional[str] = None,
        meta_info: Optional[Dict[str, Any]] = None,
        liked: Optional[bool] = None,
        created_at: Optional[str] = None,
        ttl_seconds: int = settings.redis_ttl_seconds,
    ) -> None:
        """
        درج یا به‌روزرسانی یک turn در hash.
        - هنگام دریافت query: query پر، answer/duration/error/liked خالی.
        - هنگام دریافت answer: فیلدهای اضافه به‌روزرسانی می‌شوند.
        - هنگام دریافت liked: فقط liked به‌روزرسانی می‌شود (بقیه دست‌نخورده).

        هیچ فیلدی با None بازنویسی نمی‌شود؛ None یعنی «تغییر نده».
        """
        key = ConversationCache._turns_key(conv_id)
        existing_raw = redis_client.hget(key, message_id)
        existing = json.loads(existing_raw) if existing_raw else {}

        merged = {
            "message_id": message_id,
            "query": query if query is not None else existing.get("query"),
            "answer": answer if answer is not None else existing.get("answer"),
            "duration": duration if duration is not None else existing.get("duration"),
            "error": error if error is not None else existing.get("error"),
            "meta_info": meta_info if meta_info is not None else existing.get("meta_info", {}),
            "liked": liked if liked is not None else existing.get("liked"),
            "created_at": created_at if created_at is not None else existing.get("created_at"),
        }

        pipe = redis_client.pipeline()
        pipe.hset(key, message_id, json.dumps(merged, ensure_ascii=False))
        pipe.expire(key, ttl_seconds)
        pipe.execute()

    @staticmethod
    def get_recent_turns(
        redis_client: redis.Redis,
        conv_id: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """
        آخرین `limit` turn مکالمه به ترتیب زمانی (قدیم -> جدید).
        ترتیب بر اساس created_at.
        """
        key = ConversationCache._turns_key(conv_id)
        raw = redis_client.hgetall(key)
        if not raw:
            return []

        turns = [json.loads(v) for v in raw.values()]
        # مرتب‌سازی بر اساس created_at (رشته ISO، قابل مقایسه)
        turns.sort(key=lambda t: t.get("created_at") or "")
        return turns[-limit:]

    @staticmethod
    def set_turns(
        redis_client: redis.Redis,
        conv_id: str,
        turns: List[Dict[str, Any]],
        ttl_seconds: int = settings.redis_ttl_seconds,
    ) -> None:
        """
        بازنویسی کل hash برای repopulate از Postgres.
        هر turn باید شامل message_id باشد.
        اگر liked در turn نباشد، None ذخیره می‌شود.
        """
        key = ConversationCache._turns_key(conv_id)
        pipe = redis_client.pipeline()
        pipe.delete(key)
        if turns:
            mapping = {
                t["message_id"]: json.dumps(t, ensure_ascii=False)
                for t in turns
                if t.get("message_id")
            }
            if mapping:
                pipe.hset(key, mapping=mapping)
                pipe.expire(key, ttl_seconds)
        pipe.execute()

    # ---------- Cleanup ----------

    @staticmethod
    def clear_conversation(redis_client: redis.Redis, conv_id: str) -> None:
        redis_client.delete(f"conv:{conv_id}:meta")
        redis_client.delete(ConversationCache._turns_key(conv_id))