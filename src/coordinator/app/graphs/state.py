# src/coordinator/app/graphs/state.py
"""LangGraph state for the ERP Assistant Coordinator.

Kept separate from `workflow.py` so that routing modules can import it
without creating circular imports.
"""
from __future__ import annotations

from typing import Any, TypedDict
from uuid import UUID

from app.core.schemas import ChatRequest
from app.routing.intent_schemas import IntentDecision


class GraphState(TypedDict, total=False):
    # Core request
    request: ChatRequest
    authorization: str | None

    # Routing (populated by intent_classifier_node)
    intent_decision: IntentDecision

    # Output
    answer: str
    sources: list[dict[str, Any]]
    conversation_id: UUID | None
    message_id: UUID | None
    status: str
    approval_id: UUID | None
    approval_expires_at: str | None

    # Guardrails
    guardrail_assessment: dict[str, Any]
    blocked: bool

    # Clarification (populated by clarification_node)
    clarification_missing_fields: list[str]