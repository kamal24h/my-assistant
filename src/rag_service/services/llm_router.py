# src/rag_service/services/llm_router.py
"""RAG-specific LLM router: external-first with local fallback.

The sync wrapper `answer_rag_external_first_sync` keeps the existing sync
signature of `generate_rag_response`. FastAPI runs sync endpoints in a
threadpool, so `asyncio.run` inside is safe.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_ollama import ChatOllama

from core.config import settings
from services.openai_service import (
    generate_openai_answer_with_system,
    OpenAIUnavailable,
)

logger = logging.getLogger(__name__)


def policy_for(stage: str) -> str:
    key = f"LLM_POLICY__{stage.upper()}"
    value = os.getenv(key, "").strip().lower()
    if value in ("local", "external"):
        return value
    return "external" if stage == "rag_answer" else "local"


def _format_history_block(chat_history: list[tuple[str, str]] | None) -> str:
    if not chat_history:
        return "(بدون تاریخچه)"
    lines: list[str] = []
    for role, text in chat_history:
        label = "کاربر" if role == "user" else "دستیار"
        lines.append(f"{label}: {text}")
    return "\n".join(lines)


async def answer_rag_external_first(
    question: str,
    system_prompt: str,
    context: str,
    chat_history: list[tuple[str, str]] | None = None,
    terminology_context: str = "",
) -> tuple[str, str]:
    """Async implementation. Returns (answer, source)."""
    policy = policy_for("rag_answer")
    history_block = _format_history_block(chat_history)

    if policy == "external":
        try:
            system_filled = system_prompt.format(
                context=context,
                terminology_context=terminology_context or "(هیچ اصطلاحی از واژه‌نامه تطبیق داده نشد)",
            )
            user_content = (
                f"تاریخچه مکالمه:\n{history_block}\n\n"
                f"سؤال کاربر: {question}"
            )
            answer = await generate_openai_answer_with_system(
                system_content=system_filled,
                user_content=user_content,
                sanitize_user=True,
            )
            return answer, "external"
        except OpenAIUnavailable as exc:
            logger.info("rag_answer: external unavailable (%s); using local", exc)

    # Local fallback
    history_messages: list[Any] = []
    if chat_history:
        for role, text in chat_history:
            if role == "user":
                history_messages.append(HumanMessage(content=text))
            elif role == "assistant":
                history_messages.append(AIMessage(content=text))

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}"),
    ])
    llm = ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_url,
        temperature=settings.llm_temperature,
        reasoning=False,
        num_ctx=settings.llm_num_ctx,
        repeat_penalty=1.1,
        num_predict=1024,
    )
    chain = prompt | llm | StrOutputParser()
    answer = await chain.ainvoke({
        "context": context,
        "terminology_context": terminology_context or "(هیچ اصطلاحی از واژه‌نامه تطبیق داده نشد)",
        "chat_history": history_messages,
        "question": question,
    })
    source = "local" if policy == "local" else "external_failed_local"
    return answer, source


def answer_rag_external_first_sync(
    question: str,
    system_prompt: str,
    context: str,
    chat_history: list[tuple[str, str]] | None = None,
    terminology_context: str = "",
) -> tuple[str, str]:
    """Sync wrapper. Safe in FastAPI sync endpoints (threadpool)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        return asyncio.run(answer_rag_external_first(
            question=question,
            system_prompt=system_prompt,
            context=context,
            chat_history=chat_history,
            terminology_context=terminology_context,
        ))

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            asyncio.run,
            answer_rag_external_first(
                question=question,
                system_prompt=system_prompt,
                context=context,
                chat_history=chat_history,
                terminology_context=terminology_context,
            ),
        )
        return future.result()