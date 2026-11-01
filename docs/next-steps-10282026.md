عالی. معماری را با فرض اینکه `assistant_api` به جای ASP.NET Core با **Python/FastAPI** توسعه داده می‌شود، مرور کردم. خلاصه‌ی تطابق فعلی و شکاف‌ها:

## ۱. تطابق معماری با کد فعلی

| لایه در دیاگرام | وضعیت در کد |
|---|---|
| User (Web/Desktop/Mobile) | خارج از scope |
| **Assistant API (.NET → Python)** | `src/assistant_api` — FastAPI gateway، ✅ موجود |
| **AI Coordinator** | `src/coordinator` — LangGraph، ✅ موجود |
| **ERP Integration / MCP Server (.NET)** | خارج از این ریپو (سمت ERP) |
| **ERP APIs (.NET)** | خارج از این ریپو |
| **Local RAG** | `src/rag_service` — Qdrant + embeddings، ✅ موجود |
| **Local LLM** | Ollama، ✅ موجود |
| **External OpenAI APIs** | `openai_service.py`، ✅ موجود |
| **Databases** | PostgreSQL + Redis، ✅ موجود |

## ۲. شکاف‌های معماری (بین دیاگرام و کد فعلی)

### الف) **Assistant API — جایگزینی .NET با Python**
دیاگرام می‌گوید Assistant API مسئول «REST API / SignalR (streaming)»، «Session & Conversation Management»، «Data transformation & formatting» است. اما `assistant_api/main.py` فعلی فقط یک **proxy نازک** است — هیچ‌کدام از این مسئولیت‌ها را ندارد:
- ❌ **Streaming (SignalR → SSE/WebSocket)**: ندارد. پاسخ فقط `JSON` برمی‌گردد. برای دیاگرام، باید SSE یا WebSocket اضافه شود.
- ❌ **Session Management**: ندارد. Coordinator مسئول مکالمه است.
- ❌ **Data transformation**: ندارد. payload را عیناً forward می‌کند.
- ✅ REST API: دارد.
- ✅ Auth forwarding: دارد (SSO bearer).

### ب) **Streaming در سراسر زنجیره**
دیاگرام `SignalR (streaming)` را برای Assistant API نشان می‌دهد، ولی:
- Assistant API → Coordinator: بدون streaming.
- Coordinator → Local LLM (Ollama): بدون streaming (فقط `chain.ainvoke`).
- Coordinator → RAG: بدون streaming.
- Coordinator → OpenAI: بدون streaming.

یعنی دیاگرام **streaming end-to-end** را وعده می‌دهد ولی کد فعلی همگی **request/response کامل** هستند. این یک شکاف بزرگ است.

### ج) **External OpenAI APIs — در دیاگرام به صورت مستقیم از Coordinator**
دیاگرام ✅ با کد هم‌راستاست (`openai_service.py`). ولی نکته‌ای در دیاگرام هست: «Complex Reasoning, Advanced Analysis, Specialized Tasks» — کد فعلی OpenAI را فقط برای routing عمومی استفاده می‌کند (`openai_node`). **استفاده‌ی اصلی** (reasoning پیچیده) هنوز پیاده نشده. یا حداقل در routing به اندازه‌ی کافی تفکیک نشده.

### د) **Databases — Postgres + Redis**
- ✅ Postgres: مکالمات، پیام‌ها، اسناد
- ✅ Redis: approval store + conversation cache
- ❌ دیاگرام «Session & Memory» را برای Databases نشان می‌دهد، ولی در کد Session در سطح Assistant API وجود ندارد (چون Assistant API نازک است). باید تصمیم بگیریم: Session در Assistant API (Python) مدیریت شود یا در Coordinator؟

### ه) **Local RAG — Vector DB**
دیاگرام `Vector Database (PostgreSQL / pgvector or other)` را در Data Layer جدا نشان می‌دهد، ولی کد فعلی **Qdrant** دارد. این discrepancy است:
- آیا باید به pgvector مهاجرت کنیم؟
- یا دیاگرام را با Qdrant هم‌راستا کنیم؟

پیشنهاد: **Qdrant نگه داریم** و دیاگرام را به‌روزرسانی کنیم. Qdrant انتخاب درستی برای این حجم است.

### و) **MCP Server**
- ✅ Coordinator → MCP (HTTP JSON-RPC): موجود در `mcp_client.py`
- ✅ Approval flow: موجود
- ⚠️ دیاگرام MCP Server را «ERP Integration (.NET)» نشان می‌دهد، که خارج از این ریپو است. پس این لایه از نظر معماری درست است، ولی **قرارداد (contract)** بین Coordinator و MCP Server باید مستند و تست شود:
  - tool list API
  - tool call API
  - auth (bearer token forwarding)
  - schema (inputSchema)

### ز) **Local LLM — Function Calling**
دیاگرام «Function Calling» و «Structured Output» را برای Local LLM نشان می‌دهد. کد فعلی:
- ✅ Ollama با `ChatOllama` (بدون tool calling خودکار)
- ⚠️ انتخاب tool در `select_erp_tool` با prompt، نه با function calling بومی Ollama
- ⚠️ Structured output محدود به JSON parse دستی است

می‌توان بعداً به Ollama tool calling یا structured output (مثلاً با `format="json"`) مهاجرت کرد.

## ۳. موارد باقی‌مانده برای توسعه

بر اساس شکاف‌ها، این فهرست را پیشنهاد می‌کنم:

### فاز ۱ — Assistant API (Python) کامل‌تر شود
1. **Streaming end-to-end (SSE)**: Assistant API → Coordinator → LLM. اول SSE از Assistant API، بعد Coordinator را streaming کنید. برای Local LLM با `ChatOllama.astream`، برای OpenAI با `stream=True`.
2. **Session management در Assistant API**: ذخیره‌ی `conversationId` در session (Redis یا JWT claim) برای پیگیری خودکار مکالمه.
3. **Data transformation**: نرمال‌سازی payload و پاسخ (تاریخ شمسی، واحد پول، localization).
4. **احراز هویت Assistant API**: توکن SSO را اعتبارسنجی کند (JWT signature, audience, issuer) — نه فقط forward.
5. **Rate limiting** در Assistant API برای محافظت از Coordinator.

### فاز ۲ — Coordinator و RAG
6. **OpenAI routing دقیق‌تر**: تفکیک «پیچیدگی» از «داده داخلی». الان `openai_node` فقط fallback است، ولی دیاگرام OpenAI را برای «Complex Reasoning» نشان می‌دهد. باید classification پیچیده‌تر شود (نه فقط keyword-based).
7. **Function calling بومی Ollama**: به جای prompt-based `select_erp_tool`، از `tools=[...]` بومی Ollama استفاده شود. این دقیق‌تر و سریع‌تر است.
8. **Structured output**: استفاده از `format="json"` Ollama برای پاسخ‌های structured (مثلاً لیست سفارش‌ها).
9. **MCP contract documentation**: مستندسازی tool list/call schema و auth flow.
10. **Reranker optimization**: فعلاً مدل `BAAI/bge-reranker-v2-m3` روی CPU اجرا می‌شود و کند است. اگر GPU موجود است، به GPU منتقل شود. یا مدل کوچک‌تر.

### فاز ۳ — Observability & Operations
11. **Structured logging** (BL-9 در backlog)
12. **Metrics** (Prometheus): latency, routing distribution, tool success rate, LLM error rate
13. **Tracing** (OpenTelemetry): correlation_id از Assistant API تا ERP MCP
14. **Healthcheck دقیق‌تر** برای همه سرویس‌ها

### فاز ۴ — امنیت و هم‌راستایی با دیاگرام
15. **Qdrant API key اجباری** (BL-5)
16. **Redis password** (BL-6)
17. **JWT validation در Assistant API** (بند ۴ فاز ۱)
18. **PII redaction بهتر** (BL-2)
19. **Rate limiting** (بند ۵ فاز ۱)

### فاز ۵ — مستندات و تست
20. **تست‌های خودکار** (BL-8)
21. **مستندات معماری** با دیاگرام به‌روز (بل-۱۱ + این تصویر)
22. **CI/CD** (BL-10)

## ۴. discrepancy دیاگرام و کد که باید صریح تصمیم بگیریم

| دیاگرام | کد فعلی | تصمیم |
|---|---|---|
| Vector Database: **PostgreSQL / pgvector or other** | **Qdrant** | Qdrant نگه داریم یا migrate؟ پیشنهاد: Qdrant |
| Local RAG: **Embeddings + Vector DB** (یک باکس) | `fastapi` (RAG API) + Qdrant (جدا) | هم‌راستاست، فقط در دیاگرام جدا نشان داده شود |
| Assistant API: **.NET** | **Python/FastAPI** | دیاگرام به‌روزرسانی شود |
| Session & Conversation Management در Assistant API | در Coordinator / Postgres | تصمیم: Session کجا مدیریت شود؟ |
| Streaming (SignalR) | ندارد | باید به SSE (WebSocket هم گزینه) مهاجرت شود |

## ۵. پیشنهاد اولویت‌دار

اگر بخواهیم مرحله‌به‌مرحله جلو برویم:

**مرحله ۱ (Assistant API):** SSE streaming از Assistant API به Coordinator و از Coordinator به LLM. این بیشترین اثر روی UX دارد و در دیاگرام هم صریحاً آمده.

**مرحله ۲ (Session):** Conversation session در Assistant API (Redis) برای پیگیری خودکار.

**مرحله ۳ (Auth):** JWT validation در Assistant API. توکن SSO را به Coordinator forward کن، ولی خودت هم verify کن (audience, issuer, exp).

**مرحله ۴ (Function calling بومی Ollama):** `select_erp_tool` را از prompt-based به `tools=[...]` مهاجرت بده.

**مرحله ۵ (Observability):** structured logging + metrics + tracing.

**مرحله ۶ (تست و CI):** تست‌های خودکار و pipeline.

## ۶. سؤال‌هایی که باید تصمیم بگیری

1. **Streaming**: SSE یا WebSocket? (پیشنهاد: SSE — ساده‌تر، برای chat کافی است)
2. **Session**: در Assistant API (Redis) یا Coordinator (Postgres) یا هر دو?
3. **JWT validation**: آیا Assistant API باید خودش verify کند یا فقط forward؟
4. **Qdrant vs pgvector**: نگه داریم یا migrate؟
5. **Ollama function calling**: مهاجرت کنیم یا prompt-based کافی است؟

اگر این‌ها را تصمیم بگیری، می‌توانم برای هر مرحله پچ دقیق بدهم. پیشنهادم: از **مرحله ۱ (SSE streaming)** شروع کنیم چون بیشترین اثر را دارد و در دیاگرام هم صریحاً آمده.