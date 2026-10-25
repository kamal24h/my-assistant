# معماری یکپارچه تا فاز چهارم

```text
ERP UI / .NET Client
        | HTTP
        v
Python Coordinator (FastAPI + LangGraph) :8001
   |              |                 |
   | local_llm    | local_rag       | local_mcp
   v              v                 v
Ollama/Qwen     Existing RAG API   ERP MCP Server (external/not included)
                  :8000             :8002/mcp
                   |
         +---------+---------+
         |         |         |
       Qdrant  PostgreSQL  Redis
                   |
                RabbitMQ (optional, existing project configuration)
```

Coordinator فقط از APIهای HTTP سرویس RAG استفاده می‌کند و به Qdrant یا PostgreSQL مستقیماً متصل نمی‌شود. RAG پاسخ‌های خودش را طبق مسیر موجود ذخیره می‌کند؛ پاسخ‌های local LLM و MCP از endpoint داخلی جدید `assistant-turn` ذخیره می‌شوند. مسیر MCP فقط ابزارهای read-only را انتخاب می‌کند و اجرای واقعی نیازمند MCP Server متصل به ERP و enforce شدن RBAC در همان سمت است.
