# Backlog — ERP Smart Assistant

این فایل مواردی را نگه می‌دارد که در بررسی باگ‌ها شناسایی شدند ولی به دلایل فنی یا تصمیم‌گیری، در فاز فعلی رفع نشدند. هر آیتم با شناسه، توضیح کوتاه، فایل مرتبط، و اولویت نسبی ثبت می‌شود.

## اولویت بالا (High)

### BL-1 — مهاجرت از `langchain-community` پیش از sunset
- **توضیح:** هشدار DeprecationWarning هنگام import `langchain_community.cross_encoders` نشان می‌دهد این پکیج بازنشسته می‌شود. در آینده‌ی نزدیک ممکن است از PyPI حذف یا بدون نگهداری شود.
- **فایل‌های مرتبط:** `src/rag_service/requirements.txt`، `src/rag_service/services/reranker_service.py`، `src/rag_service/ingest/ingest_service.py`
- **جایگزین‌ها:** `langchain_huggingface` برای `HuggingFaceCrossEncoder` (همین حالا در `requirements.txt` هست). برای loaders (`UnstructuredWordDocumentLoader`, `PyPDFLoader`)، پکیج‌های مستقل (`langchain-unstructured`, `langchain-pypdf`) در حال ظهور هستند.
- **اقدام:** پیش از sunset، به پکیج‌های مستقل مهاجرت کن. تست import و RAG pipeline را دوباره بزن.

## اولویت متوسط (Medium)

### BL-2 — هشدار و همگام‌سازی الگوهای guardrails
- **توضیح:** `src/coordinator/app/core/guardrails.py` و `src/rag_service/core/output_guardrails.py` الگوهای مشترک دارند ولی در دو جا تکرار شده‌اند. drift-prone.
- **فایل‌های مرتبط:** هر دو فایل بالا
- **اقدام:** در آینده به یک پکیج مشترک (مثلاً `shared/guardrails`) منتقل شوند. تا آن زمان، هنگام تغییر هر الگو، هر دو فایل هم‌زمان به‌روزرسانی شوند.

### BL-3 — `documents.py` بدون auth (تصمیم معماری)
- **توضیح:** در حال حاضر `documents.py` هیچ auth ندارد. اگر تصمیم «auth در لایه‌ی ERP» است، این کافی است. اگر نه، یک شکاف جدی است.
- **فایل‌های مرتبط:** `src/rag_service/api/v1/documents.py`
- **اقدام:** تصمیم صریح ثبت شود. اگر auth لازم است، `require_api_key` به router اضافه شود و callers هم هدر بفرستند.

### BL-4 — رویداد `message.turn.completed` و صف‌های RabbitMQ
- **توضیح:** در `conversation_service.py`، رویداد `message.turn.completed` به exchange `LogAi` با routing key `message.created` می‌رود. صف‌های `like_queue` و `conv_feedback` هم به `FeedBackLike` و `FeedBackScore` اصلاح شدند (مورد ۱۴ بالا). ولی باید با تیم ERP تأیید شود که:
  - `event_type` (`message.turn.completed`) همان است که مصرف‌کننده انتظار دارد.
  - routing key درست است.
  - ساختار payload (`build_message_payload`) مطابق انتظار است.
- **فایل‌های مرتبط:** `src/rag_service/core/message_broker.py`، `src/rag_service/core/config.py`
- **اقدام:** هم‌راستایی با مصرف‌کننده‌ی سمت ERP.

### BL-5 — `QDRANT_API_KEY` همیشه ست و کلاینت همیشه آن را بفرستد
- **توضیح:** اگر `QDRANT_API_KEY` در `.env` تعریف نشده باشد، Qdrant بدون auth بالا می‌آید. پس از باگ ۴ پورتش expose نیست، ولی برای سخت‌سازی بیشتر بهتر است همیشه auth داشته باشد.
- **فایل‌های مرتبط:** `docker-compose.yml` (سرویس qdrant)، `src/rag_service/core/config.py`، `src/rag_service/ingest/ingest_service.py`، `src/rag_service/services/rag_service.py`
- **اقدام:** `QDRANT_API_KEY` را در `.env` اجباری کن و در `config.py` fail-fast بگذار. کلاینت همیشه `api_key=settings.qdrant_api_key` بفرستد.

### BL-6 — Redis با رمز (`--requirepass`)
- **توضیح:** Redis فعلاً بدون رمز است. پورتش پس از باگ ۴ expose نیست، ولی برای defense-in-depth بهتر است رمز داشته باشد.
- **فایل‌های مرتبط:** `docker-compose.yml` (سرویس redis)، `src/rag_service/core/config.py`، `src/rag_service/core/redis_client.py`، `src/coordinator/app/core/config.py`، `src/coordinator/app/services/approval_store.py`
- **اقدام:** `redis-server --requirepass ${REDIS_PASSWORD}` و هم‌راستایی URL در هر دو سرویس.

### BL-7 — Healthcheck برای redis و qdrant در compose
- **توضیح:** فقط `postgres` healthcheck دارد. برای redis و qdrant هم اضافه کن تا `depends_on` بتواند `condition: service_healthy` استفاده کند.
- **فایل‌های مرتبط:** `docker-compose.yml`
- **اقدام:** healthcheck برای `redis` (`redis-cli ping`) و `qdrant` (`curl /healthz`). سپس `depends_on` سرویس‌های وابسته را به `condition: service_healthy` تغییر بده.

## اولویت پایین (Low)

### BL-8 — تست‌های خودکار
- **توضیح:** پروژه هیچ تست خودکاری ندارد. حداقل برای بخش‌های حساس باید تست واحد باشند.
- **فایل‌های مرتبط:** `src/coordinator/app/core/guardrails.py`، `src/coordinator/app/services/approval_store.py`، `src/coordinator/app/services/mcp_client.py`، `src/coordinator/app/graphs/workflow.py`، `src/rag_service/services/conversation_service.py`
- **اقدام:** `pytest` اضافه شود. حداقل تست‌های:
  - guardrails (injection, PII, secret)
  - approval store (create, get, save, lock, audit, TTL)
  - mcp_client (validate_tool_arguments, _allowed_tools, _allowed_write_tools)
  - workflow routing decisions (classify_path, _keyword_fallback, _is_erp_write_request)
  - conversation_service (create, complete_turn, get_recent_chat_history با liked)

### BL-9 — Logging ساخت‌یافته
- **توضیح:** لاگ‌های فعلی متنی‌اند. برای observability بهتر، structured JSON logging با correlation_id.
- **فایل‌های مرتبط:** همه‌ی سرویس‌ها
- **اقدام:** `python-json-logger` یا مشابه، و افزودن `request_id`/`conversation_id` به context.

### BL-10 — CI/CD
- **توضیح:** هیچ pipeline‌ای برای build/test/deploy نیست.
- **اقدام:** حداقل یک pipeline که `docker compose build` را اجرا کند و تست‌های BL-8 را بزند.

### BL-11 — مستندات معماری
- **توضیح:** README یا docs برای معماری (نقشه‌ی سرویس‌ها، مسیر داده، تصمیمات auth).
- **اقدام:** فایل `docs/ARCHITECTURE.md`.

### BL-12 — تصمیم روی `/create-text` در برابر `/create-text2`
- **توضیح:** هر دو endpoint semantics متفاوت دارند (replace vs upsert). هر دو کار می‌کنند.
- **فایل‌های مرتبط:** `src/rag_service/api/v1/documents.py`
- **اقدام:** اگر در آینده یکی از مصرف‌کننده‌ها ارجحیت پیدا کرد، دیگری حذف شود.

### BL-13 — `previous_version_id` nullable و ondelete
- **توضیح:** `Document.previous_version_id` با `ondelete="SET NULL"` تعریف شده. اگر ردیف قبلی حذف شود، `previous_version_id` تهی می‌شود ولی `version` باقی می‌ماند. برای زنجیره‌ی نسخه‌ها ممکن است مشکل ایجاد کند در سناریوهای خاص.
- **فایل‌های مرتبط:** `src/rag_service/core/database.py`
- **اقدام:** بازبینی زنجیره‌ی نسخه‌ها در آینده.

### BL-14 — `messages.py` auth (تصمیم معماری)
- **توضیح:** مثل BL-3، `messages.py` هم auth ندارد. اگر تصمیم «auth در لایه‌ی ERP» است، OK.
- **فایل‌های مرتبط:** `src/rag_service/api/v1/messages.py`
- **اقدام:** تصمیم صریح ثبت شود.

### BL-15 — `assistant_turns.py` auth (تصمیم معماری)
- **توضیح:** این endpoint الان auth اجباری دارد (`require_api_key`). اگر تصمیم «auth در لایه‌ی ERP» شامل این هم می‌شود، باید حذف شود.
- **فایل‌های مرتبط:** `src/rag_service/api/v1/assistant_turns.py`
- **اقدام:** تصمیم صریح. (در مورد ۱۹ بالا پیشنهاد شد حذف شود.)

## یادداشت‌های جانبی

- **مورد ۲۱ (create-text vs create-text2):** در BL-12 ثبت شد.
- **`point_id` مرده در `ingest_service.py`:** در مورد ۱۰ حذف شد.
- **درخواست هم‌راستایی با تیم ERP:** BL-4 نیازمند تأیید سمت ERP است.
- **`langchain-community` sunset:** BL-1.