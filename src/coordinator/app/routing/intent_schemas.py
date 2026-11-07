# src/coordinator/app/routing/intent_schemas.py
"""Intent schemas for the semantic router.

Design notes:
  - The `Intent` enum is the single source of truth for intent names.
    Its string values MUST match `IntentName` (used by Pydantic).
  - `IntentDecision.routes` is validated against a per-intent whitelist
    in `normalized_routes()`, so an LLM cannot invent arbitrary routes.
  - `needs_clarification` is honored even when `intent` is not AMBIGUOUS,
    so the classifier can ask for clarification on low-confidence
    sensitive intents (ERP_ACTION, ERP_DATA_QUERY).
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------- Intent names ----------
class Intent(str, Enum):
    """Canonical intent names.

    The values MUST match `IntentName` below. They are intentionally
    the same strings so that `Intent("SMALL_TALK") == Intent.SMALL_TALK`
    and Pydantic validation is consistent.
    """
    SMALL_TALK = "SMALL_TALK"
    GENERAL_KNOWLEDGE = "GENERAL_KNOWLEDGE"
    DOCUMENT_QUERY = "DOCUMENT_QUERY"
    ERP_DATA_QUERY = "ERP_DATA_QUERY"
    ERP_ACTION = "ERP_ACTION"
    MIXED_QUERY = "MIXED_QUERY"
    AMBIGUOUS = "AMBIGUOUS"


IntentName = Literal[
    "SMALL_TALK",
    "GENERAL_KNOWLEDGE",
    "DOCUMENT_QUERY",
    "ERP_DATA_QUERY",
    "ERP_ACTION",
    "MIXED_QUERY",
    "AMBIGUOUS",
]

RouteName = Literal[
    "local_llm",
    "local_rag",
    "local_mcp",
    "erp_write",
    "clarification",
    "planning",
]

EntityValue = Union[str, int, float, bool, None]


# ---------- Decision model ----------
class IntentDecision(BaseModel):
    """Structured result of intent classification.

    Attributes:
        intent: canonical intent name.
        routes: normalized list of downstream routes (whitelisted per intent).
        confidence: 0.0..1.0.
        reasoning: short explanation (no chain-of-thought).
        entities: extracted entities (order_number, customer_name, ...).
        needs_clarification: true if the router wants to ask a follow-up.
        clarification_question: Persian follow-up question (if requested).
    """
    model_config = ConfigDict(extra="forbid")

    intent: IntentName
    routes: list[RouteName] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(default="", max_length=1000)
    entities: dict[str, EntityValue] = Field(default_factory=dict)
    needs_clarification: bool = False
    clarification_question: str | None = None

    @field_validator("routes")
    @classmethod
    def _dedupe_routes(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    def normalized_routes(self) -> list[RouteName]:
        """Return canonical routes based on the classified intent.

        The whitelist prevents an LLM from producing arbitrary combinations
        like ["local_mcp", "erp_write", "openai"].
        """
        if self.needs_clarification or self.intent == "AMBIGUOUS":
            return ["clarification"]

        defaults: dict[str, list[RouteName]] = {
            "SMALL_TALK": ["local_llm"],
            "GENERAL_KNOWLEDGE": ["local_llm"],
            "DOCUMENT_QUERY": ["local_rag"],
            "ERP_DATA_QUERY": ["local_mcp"],
            "ERP_ACTION": ["erp_write"],
            "MIXED_QUERY": ["local_rag", "local_mcp"],
            "AMBIGUOUS": ["clarification"],
        }

        allowed: dict[str, set[str]] = {
            "SMALL_TALK": {"local_llm"},
            "GENERAL_KNOWLEDGE": {"local_llm"},
            "DOCUMENT_QUERY": {"local_rag"},
            "ERP_DATA_QUERY": {"local_mcp"},
            "ERP_ACTION": {"erp_write"},
            "MIXED_QUERY": {"local_rag", "local_mcp"},
            "AMBIGUOUS": {"clarification"},
        }

        chosen = [
            route for route in (self.routes or defaults[self.intent])
            if route in allowed[self.intent]
        ]
        return chosen or defaults[self.intent]