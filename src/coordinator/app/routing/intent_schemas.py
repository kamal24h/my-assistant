# src/coordinator/app/routing/intent_schemas.py

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator


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
    "local_rag",
    "local_llm",
    "local_mcp",
    "erp_write",
    "clarification",
]


class IntentDecision(BaseModel):
    """Structured result returned by the intent classifier."""

    model_config = ConfigDict(extra="forbid")

    intent: IntentName

    routes: list[RouteName] = Field(default_factory=list)

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score of the intent classification.",
    )

    reasoning: str = Field(
        default="",
        max_length=1000,
        description="Short explanation of the classification.",
    )

    entities: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        description="Entities explicitly extracted from the user request.",
    )

    needs_clarification: bool = False

    clarification_question: str | None = None

    @field_validator("routes")
    @classmethod
    def remove_duplicate_routes(
        cls,
        value: list[RouteName],
    ) -> list[RouteName]:
        """Remove duplicate routes while preserving their order."""
        return list(dict.fromkeys(value))

    def normalized_routes(self) -> list[RouteName]:
        """
        Return canonical routes based on the classified intent.

        This prevents arbitrary route combinations returned by the LLM.
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

        routes = [
            route
            for route in (self.routes or defaults[self.intent])
            if route in allowed[self.intent]
        ]

        return routes or defaults[self.intent]