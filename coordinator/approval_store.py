# coordinator/approval_store.py
"""Redis-backed, expiring store for human-approved ERP write operations.

The store deliberately fails closed when Redis is unavailable. It never stores SSO
access tokens, and audit events omit tool arguments and business payloads.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from coordinator.config import settings


class ApprovalStoreError(RuntimeError):
    pass


class ApprovalStore:
    def __init__(self) -> None:
        self._redis: Redis | None = None

    def _client(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=5)
        return self._redis

    @staticmethod
    def _key(approval_id: str) -> str:
        return f"erp-approval:{approval_id}"

    @staticmethod
    def _utcnow() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def ping(self) -> bool:
        try:
            return bool(await self._client().ping())
        except Exception as exc:
            raise ApprovalStoreError("approval_store_unavailable") from exc

    async def create(self, record: dict[str, Any], ttl_seconds: int) -> None:
        try:
            ok = await self._client().set(
                self._key(str(record["approvalId"])),
                json.dumps(record, ensure_ascii=False, separators=(",", ":")),
                ex=ttl_seconds,
                nx=True,
            )
            if not ok:
                raise ApprovalStoreError("approval_id_collision")
            await self.audit({
                "event": "created", "approvalId": record["approvalId"],
                "tenantId": record["tenantId"], "requesterUserId": record["userId"],
                "toolName": record["toolName"], "status": "pending", "at": self._utcnow(),
            })
        except ApprovalStoreError:
            raise
        except Exception as exc:
            raise ApprovalStoreError("approval_store_unavailable") from exc

    async def get(self, approval_id: str) -> dict[str, Any] | None:
        try:
            raw = await self._client().get(self._key(approval_id))
            return json.loads(raw) if raw else None
        except Exception as exc:
            raise ApprovalStoreError("approval_store_unavailable") from exc

    async def save(self, record: dict[str, Any]) -> None:
        try:
            if record.get("status") == "pending":
                expires_at = datetime.fromisoformat(str(record["expiresAt"]))
                ttl = max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
            else:
                # Keep terminal/in-progress states queryable for post-operation reconciliation.
                ttl = 7 * 24 * 60 * 60
            await self._client().set(
                self._key(str(record["approvalId"])),
                json.dumps(record, ensure_ascii=False, separators=(",", ":")),
                ex=ttl,
            )
        except Exception as exc:
            raise ApprovalStoreError("approval_store_unavailable") from exc

    async def acquire_lock(self, approval_id: str, ttl_seconds: int = 45) -> str | None:
        token = secrets.token_urlsafe(24)
        try:
            acquired = await self._client().set(f"{self._key(approval_id)}:lock", token, nx=True, ex=ttl_seconds)
            return token if acquired else None
        except Exception as exc:
            raise ApprovalStoreError("approval_store_unavailable") from exc

    async def release_lock(self, approval_id: str, token: str) -> None:
        script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
        try:
            await self._client().eval(script, 1, f"{self._key(approval_id)}:lock", token)
        except Exception as exc:
            raise ApprovalStoreError("approval_store_unavailable") from exc

    async def audit(self, event: dict[str, Any]) -> None:
        try:
            key = "erp-approval-audit:v1"
            await self._client().lpush(key, json.dumps(event, ensure_ascii=False, separators=(",", ":")))
            await self._client().ltrim(key, 0, 9999)
            await self._client().expire(key, 90 * 24 * 60 * 60)
        except Exception as exc:
            raise ApprovalStoreError("approval_store_unavailable") from exc

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


approval_store = ApprovalStore()
