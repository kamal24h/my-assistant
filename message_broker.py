# message_broker.py
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import pika
from pika.exceptions import AMQPError

from config import settings

logger = logging.getLogger(__name__)


class MessageBroker:
    """
    انتشار رویدادهای پیام به RabbitMQ.

    Exchange و Queue اصلی با نام LogAi پیکربندی می‌شوند.
    علاوه بر آن، امکان ارسال به صف‌های اختصاصی (مثل like_queue و conv_feedback)
    از طریق publish_to_queue فراهم است.

    در صورت عدم دسترسی به RabbitMQ، خطا پرتاب نمی‌شود؛ فقط لاگ می‌شود.
    """

    @staticmethod
    def _build_connection() -> pika.BlockingConnection:
        credentials = pika.PlainCredentials(
            settings.rabbitmq_user,
            settings.rabbitmq_password,
        )
        params = pika.ConnectionParameters(
            host=settings.rabbitmq_host,
            port=settings.rabbitmq_port,
            virtual_host=settings.rabbitmq_vhost,
            credentials=credentials,
            heartbeat=30,
            blocked_connection_timeout=10,
            connection_attempts=2,
            retry_delay=1,
        )
        return pika.BlockingConnection(params)

    @staticmethod
    def _ensure_topology(
        channel: pika.adapters.blocking_connection.BlockingChannel,
    ) -> None:
        channel.exchange_declare(
            exchange=settings.rabbitmq_exchange,
            exchange_type="topic",
            durable=True,
        )
        channel.queue_declare(
            queue=settings.rabbitmq_queue,
            durable=True,
        )
        channel.queue_bind(
            queue=settings.rabbitmq_queue,
            exchange=settings.rabbitmq_exchange,
            routing_key=settings.rabbitmq_routing_key,
        )

    @staticmethod
    def publish_message_event(payload: Dict[str, Any]) -> bool:
        """
        ارسال رویداد turn.completed به topology اصلی (exchange موضوعی LogAi).
        """
        if not settings.rabbitmq_enabled:
            return False

        connection = None
        try:
            connection = MessageBroker._build_connection()
            channel = connection.channel()
            channel.confirm_delivery()

            MessageBroker._ensure_topology(channel)

            body = json.dumps(payload, ensure_ascii=False, default=str)

            channel.basic_publish(
                exchange=settings.rabbitmq_exchange,
                routing_key=settings.rabbitmq_routing_key,
                body=body.encode("utf-8"),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,  # persistent
                    timestamp=int(datetime.utcnow().timestamp()),
                ),
                mandatory=False,
            )
            return True

        except AMQPError as exc:
            logger.warning("RabbitMQ publish failed (AMQP): %s", exc)
            return False
        except Exception as exc:
            logger.warning("RabbitMQ publish failed (unexpected): %s", exc)
            return False
        finally:
            if connection is not None and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    pass

    @staticmethod
    def publish_to_queue(
        queue_name: str,
        payload: Dict[str, Any],
        ensure_main_topology: bool = True,
    ) -> bool:
        """
        ارسال یک پیام JSON به یک صف مشخص (مثلاً like_queue یا conv_feedback).

        - اگر صف وجود نداشته باشد، durable ساخته می‌شود.
        - اگر ensure_main_topology=True، topology اصلی (exchange/queue/routing)
          هم تضمین می‌شود تا با تنظیمات موجود پروژه سازگار بماند.
        - ارسال به‌صورت direct (exchange پیش‌فرض "") با routing_key=queue_name است؛
          یعنی صف مستقل از exchange موضوعی پروژه کار می‌کند.
        - در صورت خطا، فقط لاگ می‌شود و False برمی‌گردد (best-effort).
        """
        if not settings.rabbitmq_enabled:
            return False

        connection = None
        try:
            connection = MessageBroker._build_connection()
            channel = connection.channel()
            channel.confirm_delivery()

            if ensure_main_topology:
                MessageBroker._ensure_topology(channel)

            # تعریف صف اختصاصی مقصد (idempotent است)
            channel.queue_declare(queue=queue_name, durable=True)

            body = json.dumps(payload, ensure_ascii=False, default=str)

            channel.basic_publish(
                exchange="",            # direct به صف، بدون exchange
                routing_key=queue_name,
                body=body.encode("utf-8"),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,  # persistent
                    timestamp=int(datetime.utcnow().timestamp()),
                ),
                mandatory=False,
            )
            return True

        except AMQPError as exc:
            logger.warning(
                "RabbitMQ publish to '%s' failed (AMQP): %s", queue_name, exc
            )
            return False
        except Exception as exc:
            logger.warning(
                "RabbitMQ publish to '%s' failed (unexpected): %s",
                queue_name,
                exc,
            )
            return False
        finally:
            if connection is not None and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    pass


# ---------- Payload builders ----------

def build_message_payload(
    message_id: str,
    conversation_id: str,
    tenant_id: Optional[str],
    tenant_desc: Optional[str],
    user_id: Optional[str],
    user_name: Optional[str],
    app_id: Optional[str],
    query: str,
    answer: Optional[str],
    duration: Optional[float],
    error: Optional[str],
    meta_info: Optional[Dict[str, Any]],
    created_at: datetime,
) -> Dict[str, Any]:
    """
    payload رویداد تکمیل یک turn (query + answer).
    رویداد فقط یک بار، بعد از آماده شدن پاسخ، منتشر می‌شود.
    """
    return {
        "event_type": "message.turn.completed",
        "message_id": message_id,
        "conversation_id": conversation_id,
        "tenant_id": tenant_id,
        "tenant_desc": tenant_desc,
        "user_id": user_id,
        "user_name": user_name,
        "app_id": app_id,
        "query": query,
        "answer": answer,
        "duration": duration,
        "error": error,
        "meta_info": meta_info or {},
        "created_at": created_at.isoformat(),
    }


def build_message_row_payload(
    msg,
    app_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    payload کامل یک رکورد جدول messages برای صف like_queue.
    همه فیلدهای شناخته‌شده رکورد را شامل می‌شود.
    """
    return {
        "event_type": "message.row.updated",
        "messages_id": str(msg.id),
        "conversation_id": str(msg.conversation_id),
        "app_id": app_id, 
        "query": msg.query,
        "answer": msg.answer,
        "duration": msg.duration,
        "error": msg.error,
        #"meta_info": msg.meta_info or {},
        "liked": msg.liked,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def build_conversation_row_payload(conv) -> Dict[str, Any]:
    """
    payload کامل یک رکورد جدول conversations برای صف conv_feedback.
    همه فیلدهای شناخته‌شده رکورد را شامل می‌شود.
    """
    return {
        "event_type": "conversation.feedback.updated",
        "conversation_id": str(conv.id),
        "app_id": conv.app_id,
        "tenant_id": conv.tenant_id,
        "user_id": conv.user_id,
        "user_name": conv.user_name,
        "tenant_desc": conv.tenant_desc,
        "title": conv.title,
        "status": conv.status,
        "feedback_score": conv.feedback_score,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
    }