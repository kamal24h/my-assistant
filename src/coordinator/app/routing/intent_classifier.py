# src/coordinator/app/routing/intent_classifier.py
"""Semantic intent classifier.

Strategy (in order):
  1. Hard keyword rules (ERP_ACTION, MIXED_QUERY are never overridden
     because they affect approvals/planning and must be deterministic).
  2. Structured LLM classification (when available and enabled).
  3. Keyword fallback (when the LLM is unavailable or fails).

Confidence policy:
  - confidence < clarification_threshold → AMBIGUOUS (ask the user)
  - confidence < confidence_threshold AND intent in {ERP_ACTION, ERP_DATA_QUERY}
    → AMBIGUOUS (never auto-execute sensitive operations without confidence)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.config import settings
from app.routing.intent_prompts import INTENT_SYSTEM_PROMPT
from app.routing.intent_schemas import IntentDecision, IntentName
from app.routing.keyword_fallback import keyword_fallback, _has_identifier
from app.routing.llm_factory import build_local_llm

logger = logging.getLogger(__name__)


class IntentClassifier:
    """Semantic intent classifier with structured output and confidence policy."""

    def __init__(
        self,
        *,
        confidence_threshold: float = 0.65,
        clarification_threshold: float = 0.45,
        use_structured_output: bool = True,
    ) -> None:
        if not (0.0 <= clarification_threshold <= confidence_threshold <= 1.0):
            raise ValueError(
                "Expected: 0 <= clarification_threshold <= confidence_threshold <= 1"
            )
        self.confidence_threshold = confidence_threshold
        self.clarification_threshold = clarification_threshold
        self.use_structured_output = use_structured_output
        self._structured_llm = None

        if use_structured_output:
            self._initialize_structured_llm()

    # ---------------------------------------------------------
    # Initialization
    # ---------------------------------------------------------

    def _initialize_structured_llm(self) -> None:
        try:
            llm = build_local_llm(temperature=0.0, num_predict=512)
            if not hasattr(llm, "with_structured_output"):
                logger.warning(
                    "ChatOllama has no with_structured_output; keyword fallback only."
                )
                return
            self._structured_llm = llm.with_structured_output(IntentDecision)
            logger.info("Intent classifier initialized with structured output.")
        except Exception:
            logger.exception(
                "Failed to initialize structured output; keyword fallback only."
            )
            self._structured_llm = None

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    async def classify(
        self,
        question: str,
        *,
        conversation_context: str = "",
    ) -> IntentDecision:
        question = (question or "").strip()
        if not question:
            return keyword_fallback(question)

        # 1. Hard keyword rules for sensitive intents.
        kw = keyword_fallback(question)
        if kw.intent in ("ERP_ACTION", "MIXED_QUERY"):
            return kw

        # 2. Structured LLM.
        if self._structured_llm is None:
            return kw

        try:
            llm_decision = await self._classify_with_llm(question, conversation_context)
            if llm_decision is None:
                return kw
            return self._apply_confidence_policy(llm_decision, kw)
        except Exception:
            logger.exception("LLM intent classification failed; using keyword fallback.")
            return kw

    # ---------------------------------------------------------
    # LLM invocation
    # ---------------------------------------------------------

    async def _classify_with_llm(
        self,
        question: str,
        conversation_context: str,
    ) -> Optional[IntentDecision]:
        user_message = self._build_user_message(question, conversation_context)
        result = await self._structured_llm.ainvoke([
            ("system", INTENT_SYSTEM_PROMPT),
            ("human", user_message),
        ])
        if isinstance(result, IntentDecision):
            return result
        if isinstance(result, dict):
            return IntentDecision.model_validate(result)
        logger.warning(
            "Unexpected structured output type: %s", type(result).__name__,
        )
        return None

    @staticmethod
    def _build_user_message(question: str, conversation_context: str) -> str:
        context = conversation_context.strip() if conversation_context else "(empty)"
        return (
            "Conversation context:\n"
            f"{context}\n\n"
            "Current user request:\n"
            f"{question}"
        )

    # ---------------------------------------------------------
    # Confidence policy
    # ---------------------------------------------------------

    def _apply_confidence_policy(
        self,
        decision: IntentDecision,
        fallback: IntentDecision,
    ) -> IntentDecision:
        # Explicit clarification requested by the model.
        if decision.needs_clarification or decision.intent == "AMBIGUOUS":
            if not decision.clarification_question:
                decision.clarification_question = (
                    "لطفاً درخواست خود را دقیق‌تر توضیح دهید."
                )
            decision.intent = "AMBIGUOUS"
            decision.routes = ["clarification"]
            decision.needs_clarification = True
            return decision

        # Very low confidence.
        if decision.confidence < self.clarification_threshold:
            return self._ambiguous(
                confidence=decision.confidence,
                entities=decision.entities,
                reasoning="اطمینان طبقه‌بندی برای انتخاب مسیر مناسب کافی نیست.",
                question="منظورتان دریافت راهنمای انجام این فرایند است یا بررسی اطلاعات واقعی آن در ERP؟",
            )

        # Medium confidence for sensitive intents.
        if (
            decision.confidence < self.confidence_threshold
            and decision.intent in ("ERP_ACTION", "ERP_DATA_QUERY")
        ):
            return self._ambiguous(
                confidence=decision.confidence,
                entities=decision.entities,
                reasoning="تشخیص درخواست مرتبط با ERP با اطمینان کافی انجام نشده است.",
                question="لطفاً مشخص کنید که راهنمای انجام کار را می‌خواهید یا قصد بررسی یا اجرای عملیات واقعی در ERP را دارید؟",
            )

        # Normalize routes against the whitelist.
        decision.routes = decision.normalized_routes()

        # Extra safety: ERP_ACTION without an explicit identifier is ambiguous
        # (prevents e.g. "فاکتور را حذف کن" from creating an approval without
        # a concrete target).
        if (
            decision.intent == "ERP_ACTION"
            and not _has_identifier(decision.entities.get("order_number", "") or "")
            and not _has_identifier(decision.entities.get("invoice_number", "") or "")
            and not any(
                _has_identifier(str(v))
                for v in decision.entities.values()
                if v is not None
            )
        ):
            # Let the clarification layer add "order_id/entity" questions.
            pass

        return decision

    @staticmethod
    def _ambiguous(
        *,
        confidence: float,
        entities: dict[str, Any] | None = None,
        reasoning: str = "",
        question: str = "",
    ) -> IntentDecision:
        return IntentDecision(
            intent="AMBIGUOUS",
            routes=["clarification"],
            confidence=confidence,
            reasoning=reasoning,
            entities=entities or {},
            needs_clarification=True,
            clarification_question=question or "لطفاً درخواست خود را دقیق‌تر توضیح دهید.",
        )


# Singleton used by workflow.
intent_classifier = IntentClassifier(
    use_structured_output=settings.router_use_structured_output,
)