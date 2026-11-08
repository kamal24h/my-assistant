# src/coordinator/app/core/config.py
import os
from pydantic import BaseModel, Field


class CoordinatorSettings(BaseModel):
    # In Docker, service names are resolved through assistant_network.
    ollama_base_url: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    local_llm_model: str = Field(
        default_factory=lambda: os.getenv("LOCAL_LLM_MODEL", "qwen3.5:9b")
    )
    local_llm_temperature: float = Field(
        default_factory=lambda: float(os.getenv("LOCAL_LLM_TEMPERATURE", "0.2")),
        ge=0.0,
        le=2.0,
    )
    local_llm_num_predict: int = Field(
        default_factory=lambda: int(os.getenv("LOCAL_LLM_NUM_PREDICT", "350")),
        ge=1,
        le=8192,
    )
    rag_api_base_url: str = Field(
        default_factory=lambda: os.getenv("RAG_API_BASE_URL", "http://rag:8102")
    )
    rag_api_key: str = Field(
        default_factory=lambda: os.getenv("RAG_API_KEY", "")
    )
    rag_api_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("RAG_API_TIMEOUT_SECONDS", "60")),
        gt=0,
        le=300,
    )
    # --- Organization terminology / glossary ---
    terminology_file: str = Field(
        default_factory=lambda: os.getenv(
            "TERMINOLOGY_FILE", "/app/app/terminology/data/terms.json"
        )
    )
    terminology_max_matches: int = Field(
        default_factory=lambda: int(os.getenv("TERMINOLOGY_MAX_MATCHES", "12")),
        ge=1, le=50,
    )
    terminology_max_context_chars: int = Field(
        default_factory=lambda: int(os.getenv("TERMINOLOGY_MAX_CONTEXT_CHARS", "3000")),
        ge=256, le=12000,
    )

    router_num_predict: int = Field(
        default_factory=lambda: int(os.getenv("ROUTER_NUM_PREDICT", "32")),
        ge=1,
        le=256,
    )

    router_use_structured_output: bool = Field(
        default_factory=lambda: os.getenv("ROUTER_USE_STRUCTURED_OUTPUT", "true")
        .strip().lower() in {"1", "true", "yes", "on"}
    )
    
    # --- Streaming (SSE) ---
    sse_heartbeat_interval_seconds: float = Field(
        default_factory=lambda: float(os.getenv("SSE_HEARTBEAT_INTERVAL_SECONDS", "15")),
        gt=0, le=120,
    )
    sse_stream_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("SSE_STREAM_TIMEOUT_SECONDS", "300")),
        gt=0, le=3600,
    )
    # --- Clarification (پرسش تکمیلی برای سؤال مبهم) ---
    clarification_ttl_seconds: int = Field(
        default_factory=lambda: int(os.getenv("CLARIFICATION_TTL_SECONDS", "600")),
        ge=60, le=86400,
    )
    clarification_enabled: bool = Field(
        default_factory=lambda: os.getenv("CLARIFICATION_ENABLED", "true").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    clarification_min_prompt_chars: int = Field(
        default_factory=lambda: int(os.getenv("CLARIFICATION_MIN_PROMPT_CHARS", "10")),
        ge=1, le=200,
    )
    clarification_max_questions: int = Field(
        default_factory=lambda: int(os.getenv("CLARIFICATION_MAX_QUESTIONS", "2")),
        ge=1,
        le=3,
    )
    clarification_num_predict: int = Field(
        default_factory=lambda: int(os.getenv("CLARIFICATION_NUM_PREDICT", "256")),
        ge=64,
        le=512,
    )
    clarification_history_max_turns: int = Field(
        default_factory=lambda: int(os.getenv("CLARIFICATION_HISTORY_MAX_TURNS", "3")),
        ge=0,
        le=10,
    )
    openai_enabled: bool = Field(
        default_factory=lambda: os.getenv("OPENAI_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    )
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    openai_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("OPENAI_TIMEOUT_SECONDS", "25")), gt=0, le=120
    )
    openai_max_retries: int = Field(
        default_factory=lambda: int(os.getenv("OPENAI_MAX_RETRIES", "1")), ge=0, le=3
    )
    openai_max_tokens: int = Field(
        default_factory=lambda: int(os.getenv("OPENAI_MAX_TOKENS", "800")), ge=1, le=8192
    )
    openai_temperature: float = Field(
        default_factory=lambda: float(os.getenv("OPENAI_TEMPERATURE", "0.2")), ge=0, le=2
    )
    openai_max_input_chars: int = Field(
        default_factory=lambda: int(os.getenv("OPENAI_MAX_INPUT_CHARS", "4000")), ge=100, le=12000
    )
    openai_max_concurrency: int = Field(
        default_factory=lambda: int(os.getenv("OPENAI_MAX_CONCURRENCY", "4")), ge=1, le=32
    )
    openai_max_requests_per_minute: int = Field(
        default_factory=lambda: int(os.getenv("OPENAI_MAX_REQUESTS_PER_MINUTE", "30")), ge=1, le=600
    )

    erp_mcp_url: str = Field(
        default_factory=lambda: os.getenv("ERP_MCP_URL", "http://216.65.200.52:30001/mcp")
    )
    erp_mcp_timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("ERP_MCP_TIMEOUT_SECONDS", "30")),
        gt=0,
        le=180,
    )
    erp_mcp_bearer_token: str = Field(
        default_factory=lambda: os.getenv("ERP_MCP_BEARER_TOKEN", "")
    )
    erp_mcp_read_only_tools: str = Field(
        default_factory=lambda: os.getenv("ERP_MCP_READ_ONLY_TOOLS", "")
    )
    erp_mcp_write_tools: str = Field(
        default_factory=lambda: os.getenv("ERP_MCP_WRITE_TOOLS", "")
    )
    erp_mcp_require_user_token: bool = Field(
        default_factory=lambda: os.getenv("ERP_MCP_REQUIRE_USER_TOKEN", "true").strip().lower() in {"1", "true", "yes", "on"}
    )
    redis_url: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://redis:6379/0"))
    approval_api_key: str = Field(
        default_factory=lambda: os.getenv("APPROVAL_API_KEY", os.getenv("RAG_API_KEY", ""))
    )
    approval_ttl_seconds: int = Field(
        default_factory=lambda: int(os.getenv("APPROVAL_TTL_SECONDS", "900")), ge=60, le=86400
    )
    approval_allow_self_approval: bool = Field(
        default_factory=lambda: os.getenv("APPROVAL_ALLOW_SELF_APPROVAL", "false").strip().lower() in {"1", "true", "yes", "on"}
    )

    guardrails_enabled: bool = Field(
        default_factory=lambda: os.getenv("GUARDRAILS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    )
    guardrails_max_prompt_chars: int = Field(
        default_factory=lambda: int(os.getenv("GUARDRAILS_MAX_PROMPT_CHARS", "12000")), ge=100, le=20000
    )
    guardrails_max_output_chars: int = Field(
        default_factory=lambda: int(os.getenv("GUARDRAILS_MAX_OUTPUT_CHARS", "16000")), ge=100, le=30000
    )
    guardrails_max_tool_result_chars: int = Field(
        default_factory=lambda: int(os.getenv("GUARDRAILS_MAX_TOOL_RESULT_CHARS", "12000")), ge=500, le=50000
    )


settings = CoordinatorSettings()
