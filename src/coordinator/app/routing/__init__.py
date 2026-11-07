# src/coordinator/app/routing/__init__.py
"""Intent routing package for the ERP Assistant Coordinator.

Public exports:
  - Intent, IntentName, IntentDecision
  - keyword_fallback
  - IntentClassifier, intent_classifier (singleton)
  - clarification helpers
  - build_local_llm (shared LLM factory with reasoning=False)
"""
from app.routing.intent_schemas import Intent, IntentName, IntentDecision
from app.routing.keyword_fallback import keyword_fallback, _is_small_talk
from app.routing.intent_classifier import IntentClassifier, intent_classifier
from app.routing.clarification import (
    _needs_clarification,
    _extract_reason,
    _has_reason_hint,
    _has_identifier,
    _has_entity_hint,
)
from app.routing.llm_factory import build_local_llm

__all__ = [
    "Intent",
    "IntentName",
    "IntentDecision",
    "keyword_fallback",
    "IntentClassifier",
    "intent_classifier",
    "_is_small_talk",
    "_needs_clarification",
    "_extract_reason",
    "_has_reason_hint",
    "_has_identifier",
    "_has_entity_hint",
    "build_local_llm",
]