# src/coordinator/app/routing/intent_classifier.py

# Hybrid Semantic Router
# 1. Rule-based برای موارد قطعی و ساده.
# 2. Local Qwen برای تشخیص معنایی Intent.
# 3. Pydantic Structured Output برای خروجی استاندارد.
# 4. Policy Engine برای کنترل مجوزها و عملیات حساس.
# 5. LangGraph Conditional Routing برای انتخاب مسیر.
# 6. Clarification برای موارد مبهم.
# 7. Multi-route Workflow برای درخواست‌های ترکیبی.

from __future__ import annotations

import logging
from typing import Any

from .intent_prompts import INTENT_SYSTEM_PROMPT
from .intent_schemas import IntentDecision
from .keyword_fallback import keyword_fallback


logger = logging.getLogger(__name__)


class IntentClassifier:
    """
    Semantic intent classifier for ERP Assistant.

    Responsibilities:
        1. Classify user requests based on semantic intent.
        2. Select the appropriate execution route.
        3. Use conversation context to resolve references.
        4. Detect ambiguous requests.
        5. Fall back to deterministic keyword routing if
           structured LLM classification is unavailable.

    Supported intents:
        - SMALL_TALK
        - GENERAL_KNOWLEDGE
        - DOCUMENT_QUERY
        - ERP_DATA_QUERY
        - ERP_ACTION
        - MIXED_QUERY
        - AMBIGUOUS

    Supported routes:
        - local_llm
        - local_rag
        - local_mcp
        - erp_write
        - clarification
    """

    def __init__(
        self,
        llm: Any,
        *,
        confidence_threshold: float = 0.65,
        clarification_threshold: float = 0.45,
    ) -> None:
        """
        Initialize the intent classifier.

        Args:
            llm:
                LangChain chat model, preferably the local Qwen model.

            confidence_threshold:
                Minimum confidence required for normal routing.

            clarification_threshold:
                Below this threshold, the request is considered ambiguous.
        """

        if not (
            0.0 <= clarification_threshold
            <= confidence_threshold
            <= 1.0
        ):
            raise ValueError(
                "Expected: 0 <= clarification_threshold "
                "<= confidence_threshold <= 1"
            )

        self.llm = llm

        self.confidence_threshold = confidence_threshold
        self.clarification_threshold = clarification_threshold

        self._structured_llm = None

        self._initialize_structured_llm()

    # ---------------------------------------------------------
    # Initialization
    # ---------------------------------------------------------

    def _initialize_structured_llm(self) -> None:
        """
        Configure structured output for the LLM.

        If the model does not support structured output,
        the classifier will use keyword fallback.
        """

        if not hasattr(self.llm, "with_structured_output"):
            logger.warning(
                "LLM does not support with_structured_output. "
                "Keyword fallback will be used."
            )
            return

        try:
            self._structured_llm = (
                self.llm.with_structured_output(IntentDecision)
            )

            logger.info(
                "Intent classifier initialized with structured output."
            )

        except Exception:
            logger.exception(
                "Failed to initialize structured output for intent classifier."
            )

            self._structured_llm = None

    # ---------------------------------------------------------
    # Main classification method
    # ---------------------------------------------------------

    async def classify(
        self,
        question: str,
        conversation_context: str = "",
    ) -> IntentDecision:
        """
        Classify a user request.

        Args:
            question:
                Current user message.

            conversation_context:
                Relevant conversation history or summarized context.

        Returns:
            IntentDecision
        """

        question = (question or "").strip()

        # Empty input
        if not question:
            return keyword_fallback(question)

        # Structured output unavailable
        if self._structured_llm is None:
            logger.warning(
                "Structured intent classification unavailable. "
                "Using keyword fallback."
            )

            return keyword_fallback(question)

        try:
            decision = await self._classify_with_llm(
                question=question,
                conversation_context=conversation_context,
            )

            if decision is None:
                return keyword_fallback(question)

            return self._apply_confidence_policy(decision)

        except Exception:
            logger.exception(
                "Intent classification failed. "
                "Using keyword fallback."
            )

            return keyword_fallback(question)

    # ---------------------------------------------------------
    # LLM classification
    # ---------------------------------------------------------

    async def _classify_with_llm(
        self,
        question: str,
        conversation_context: str = "",
    ) -> IntentDecision | None:
        """
        Invoke the structured LLM classifier.
        """

        user_message = self._build_user_message(
            question=question,
            conversation_context=conversation_context,
        )

        result = await self._structured_llm.ainvoke(
            [
                (
                    "system",
                    INTENT_SYSTEM_PROMPT,
                ),
                (
                    "human",
                    user_message,
                ),
            ]
        )

        if isinstance(result, IntentDecision):
            return result

        if isinstance(result, dict):
            return IntentDecision.model_validate(result)

        logger.warning(
            "Unexpected intent classifier output type: %s",
            type(result).__name__,
        )

        return None

    # ---------------------------------------------------------
    # Prompt construction
    # ---------------------------------------------------------

    @staticmethod
    def _build_user_message(
        question: str,
        conversation_context: str = "",
    ) -> str:
        """
        Build the user message passed to the classifier.

        Conversation context is provided only for resolving references
        and understanding the current request.
        """

        context = (
            conversation_context.strip()
            if conversation_context
            else "(empty)"
        )

        return (
            "Conversation context:\n"
            f"{context}\n\n"
            "Current user request:\n"
            f"{question}"
        )

    # ---------------------------------------------------------
    # Confidence and routing policy
    # ---------------------------------------------------------

    def _apply_confidence_policy(
        self,
        decision: IntentDecision,
    ) -> IntentDecision:
        """
        Apply confidence thresholds and normalize routes.

        Important:
            Low-confidence ERP actions and data queries should not
            be executed automatically.
        """

        # Explicit clarification requested by classifier
        if (
            decision.needs_clarification
            or decision.intent == "AMBIGUOUS"
        ):
            decision.intent = "AMBIGUOUS"
            decision.routes = ["clarification"]
            decision.needs_clarification = True

            if not decision.clarification_question:
                decision.clarification_question = (
                    "لطفاً درخواست خود را دقیق‌تر توضیح دهید."
                )

            return decision

        # Very low confidence
        if decision.confidence < self.clarification_threshold:
            return self._create_ambiguous_decision(
                confidence=decision.confidence,
                entities=decision.entities,
                reasoning=(
                    "اطمینان طبقه‌بندی برای انتخاب مسیر مناسب کافی نیست."
                ),
                clarification_question=(
                    "منظورتان دریافت راهنمای انجام این فرایند است "
                    "یا بررسی اطلاعات واقعی آن در ERP؟"
                ),
            )

        # Medium confidence for sensitive ERP routes
        if (
            decision.confidence < self.confidence_threshold
            and decision.intent in {
                "ERP_ACTION",
                "ERP_DATA_QUERY",
            }
        ):
            return self._create_ambiguous_decision(
                confidence=decision.confidence,
                entities=decision.entities,
                reasoning=(
                    "تشخیص درخواست مرتبط با ERP "
                    "با اطمینان کافی انجام نشده است."
                ),
                clarification_question=(
                    "لطفاً مشخص کنید که راهنمای انجام کار را می‌خواهید "
                    "یا قصد بررسی یا اجرای عملیات واقعی در ERP را دارید؟"
                ),
            )

        # Normalize routes according to the selected intent
        decision.routes = decision.normalized_routes()

        return decision

    # ---------------------------------------------------------
    # Ambiguous decision
    # ---------------------------------------------------------

    @staticmethod
    def _create_ambiguous_decision(
        confidence: float,
        entities: dict[str, Any] | None = None,
        reasoning: str = "",
        clarification_question: str = "",
    ) -> IntentDecision:
        """
        Create a standardized clarification decision.
        """

        return IntentDecision(
            intent="AMBIGUOUS",
            routes=["clarification"],
            confidence=confidence,
            reasoning=reasoning,
            entities=entities or {},
            needs_clarification=True,
            clarification_question=clarification_question,
        )

    # ---------------------------------------------------------
    # Fallback
    # ---------------------------------------------------------

    @staticmethod
    def classify_with_fallback(
        question: str,
    ) -> IntentDecision:
        """
        Expose deterministic keyword fallback for external callers.
        """

        return keyword_fallback(question)