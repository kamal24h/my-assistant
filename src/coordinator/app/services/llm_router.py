# src/coordinator/app/services/llm_router.py
"""Unified LLM router: external-first with local fallback.

Each call site declares a `stage`. Policy per stage:
  - "external": try external (OpenAI), fallback to local on OpenAIUnavailable.
  - "local": always local.

Override per-stage via env:
  LLM_POLICY__LOCAL_LLM_ANSWER=local
  LLM_POLICY__RAG_ANSWER=local
"""
from __future__ import annotations

import logging
import os

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.routing.llm_factory import build_local_llm
from app.services.openai_service import (
    generate_openai_answer,
    OpenAIUnavailable,
)

logger = logging.getLogger(__name__)

_DEFAULT_POLICY: dict[str, str] = {
    "local_llm_answer":  "external",
    "erp_summarizer":    "external",
    "planning_combiner": "external",
    "openai_direct":     "external",
    "rag_answer":        "external",
    "intent_classifier": "local",
    "tool_selector":     "local",
    "small_talk":        "local",
    "form_resolver":     "local",
}


def policy_for(stage: str) -> str:
    key = f"LLM_POLICY__{stage.upper()}"
    value = os.getenv(key, "").strip().lower()
    if value in ("local", "external"):
        return value
    return _DEFAULT_POLICY.get(stage, "local")


async def answer_external_first(
    stage: str,
    question: str,
    *,
    system_prompt: str | None = None,
    local_num_predict: int | None = None,
) -> tuple[str, str]:
    """Return (answer, source). source ∈ {"external", "local", "external_failed_local"}."""
    policy = policy_for(stage)

    if policy == "external":
        try:
            answer = await generate_openai_answer(question)
            return answer, "external"
        except OpenAIUnavailable as exc:
            logger.info("Stage %s: external unavailable (%s); using local", stage, exc)

    if system_prompt:
        prompt = ChatPromptTemplate.from_messages(
            [("system", system_prompt), ("human", "{question}")]
        )
    else:
        prompt = ChatPromptTemplate.from_messages(
            [("system", "به فارسی حرفه‌ای و دقیق پاسخ بده."), ("human", "{question}")]
        )
    chain = prompt | build_local_llm(num_predict=local_num_predict) | StrOutputParser()
    answer = await chain.ainvoke({"question": question})
    source = "local" if policy == "local" else "external_failed_local"
    return answer, source