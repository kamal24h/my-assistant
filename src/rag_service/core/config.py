# src/rag_service/core/config.py
import os
from typing import Optional
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # تنظیمات احراز هویت
    api_key: Optional[str] = None
    api_key_header_name: str = "X-API-Key"

    # تنظیمات پایگاه داده رابطه‌ای (PostgreSQL)
    postgres_user: str = "assistant_user"
    postgres_password: str = "aRian2502aSsist2026"
    postgres_db: str = "assistant_db"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # تنظیمات Vector DB (Qdrant)
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: Optional[str] = None
    collection_name: str = "assistant_knowledge1"

    # تنظیمات Ollama و هوش مصنوعی
    ollama_url: str = "http://ollama:11434"
    #llm_model: str = "qwen3:8b"
    llm_model: str = "qwen3.5:9b"
    embedding_model: str = "qllama/bge-m3:q4_k_m"

    # اضافه کردن پارامترهای کانتکست و تولید متن
    llm_num_ctx: int = 8192
    llm_temperature: float = 0.3

    # تنظیمات Chunker و پردازش اسناد
    chunk_size: int = 800
    chunk_overlap: int = 120
    embed_batch_size: int = 32

    # تنظیمات Cache (Redis)
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_ttl_seconds: int = 86400  # ۱ روز

    # تنظیمات تاریخچه مکالمه
    # حداکثر تعداد نوبت‌هایی که به LLM داده می‌شود (هر نوبت = query + answer)
    chat_history_max_turns: int = 3
    
    # تنظیمات RabbitMQ
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "admin"
    rabbitmq_password: str = "admin"
    rabbitmq_vhost: str = "/"
    rabbitmq_exchange: str = "LogAi"
    rabbitmq_queue: str = "LogAi"
    rabbitmq_routing_key: str = "message.created"
    rabbitmq_enabled: bool = True
    rabbitmq_like_queue: str = "FeedBackLike"
    rabbitmq_conv_feedback_queue: str = "FeedBackScore"

    # تولید URL دیتابیس بدون نیاز به ترکیب دستی رشته‌ها
    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # اولویت‌دهی به متغیرهای محیطی سیستم و سپس فایل .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# بررسی fail-fast در startup (اگر API_KEY ست نشده باشد و DEBUG فعال نباشد)
# اگر می‌خواهی در dev بدون کلید کار کنی، API_KEY را ست کن یا از APP_ENV=dev استفاده کن
