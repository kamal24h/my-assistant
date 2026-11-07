# src/coordinator/app/routing/llm_factory.py
"""Shared LLM factory.

Used by both the intent classifier and the workflow. The `reasoning=False`
flag is critical for qwen3.5-style models: without it, the model puts its
answer in the `thinking` field and `content` is empty.
"""
from __future__ import annotations

from langchain_ollama import ChatOllama

from app.core.config import settings


def build_local_llm(
    *,
    temperature: float | None = None,
    num_predict: int | None = None,
) -> ChatOllama:
    """Build a ChatOllama instance with `reasoning=False` (critical for qwen3.5)."""
    return ChatOllama(
        model=settings.local_llm_model,
        base_url=settings.ollama_base_url,
        temperature=(
            settings.local_llm_temperature
            if temperature is None else temperature
        ),
        num_predict=(
            settings.local_llm_num_predict
            if num_predict is None else num_predict
        ),
        reasoning=False,
    )