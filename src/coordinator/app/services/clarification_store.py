# src/coordinator/app/services/clarification_store.py
"""Redis-backed, expiring store for pending clarification requests."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from redis.asyncio import Redis

from app.core.config import settings


class ClarificationStoreError(RuntimeError):
    pass


class ClarificationStore:
    def __init__(self) -> None:
        self._redis: Redis | None = None

    def _client(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(
                settings.redis_url, decode_responses=True,
                socket_connect_timeout=3, socket_timeout=5,
            )
        return self._redis

    @staticmethod
    def _key(conversation_id: str) -> str:
        return f"clarification:{conversation_id}"

    async def set(
        self,
        conversation_id: str,
        intent: str,
        tool_name: str | None,
        partial_context: dict[str, Any],
        missing_fields: list[str],
        question: str,
        clarification_id: str,
        ttl_seconds: int | None = None,
    ) -> None:
        record = {
            "conversationId": conversation_id,
            "intent": intent,
            "toolName": tool_name,
            "partialContext": partial_context,
            "missingFields": missing_fields,
            "question": question,
            "clarificationId": clarification_id,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "expiresAt": (
                datetime.now(timezone.utc)
                + timedelta(seconds=ttl_seconds or settings.clarification_ttl_seconds)
            ).isoformat(),
        }
        try:
            await self._client().set(
                self._key(conversation_id),
                json.dumps(record, ensure_ascii=False, separators=(",", ":")),
                ex=ttl_seconds or settings.clarification_ttl_seconds,
            )
        except Exception as exc:
            raise ClarificationStoreError("clarification_store_unavailable") from exc

    async def get(self, conversation_id: str) -> dict[str, Any] | None:
        try:
            raw = await self._client().get(self._key(conversation_id))
            return json.loads(raw) if raw else None
        except Exception as exc:
            raise ClarificationStoreError("clarification_store_unavailable") from exc

    async def clear(self, conversation_id: str) -> None:
        try:
            await self._client().delete(self._key(conversation_id))
        except Exception as exc:
            raise ClarificationStoreError("clarification_store_unavailable") from exc

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


clarification_store = ClarificationStore()