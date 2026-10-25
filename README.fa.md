# دستیار هوشمند ERP — بسته یکپارچه تا پایان فاز هفتم

این بسته، آخرین پروژه Local RAG ارسالی را به‌عنوان سرویس پایه حفظ می‌کند و Coordinator فازهای ۱ تا ۶ را به همان Compose اضافه می‌کند. APIهای قبلی RAG حذف یا تغییر مسیر داده نشده‌اند؛ فقط endpoint جدید `assistant-turn` برای ذخیره پاسخ‌های تولیدشده توسط Local LLM و ERP MCP اضافه شده است.

## ساختار

- `api/`, `schemas/`, `services/`: سرویس RAG موجود
- `coordinator/`: FastAPI + LangGraph؛ مسیرهای `local_llm`, `local_rag`, `local_mcp` و `openai`
- `tests_coordinator/`: تست‌های Coordinator
- `docs/MCP_TOOLS_CONTRACT.md`: قرارداد پیشنهادی برای MCP Server واقعی ERP
- `docker-compose.yml`: Compose یکپارچه

## شروع

1. این پوشه را در مسیر پروژه قرار بده. فایل `.env.example` را به `.env` کپی کن و مقادیر امن را تنظیم کن. اگر `.env` فعلی داری، آن را حفظ کن و فقط متغیرهای لازم را با دقت merge کن؛ آن را با نمونه جایگزین نکن.
2. مقدار `API_KEY` باید یک کلید داخلی طولانی و تصادفی باشد. `RAG_API_KEY` باید دقیقاً همان مقدار باشد. این کلید برای endpoint ذخیره مکالمات LLM/MCP استفاده می‌شود.
3. شبکه Docker خارجی مورد استفاده پروژه را بساز، اگر از قبل وجود ندارد:

```bash
docker network create assistant_network
```

4. در صورت نیاز نام مدل و تنظیمات را در `.env` تنظیم کن؛ سپس:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f coordinator
```

5. سلامت سرویس‌ها را بررسی کن:

```bash
curl http://localhost:8001/health
curl http://localhost:8001/health/llm
curl http://localhost:8001/health/rag
curl http://localhost:8001/health/mcp
```

`/health/mcp` تا وقتی MCP Server واقعی با پروتکل سازگار در دسترس نباشد، عمداً healthy نمی‌شود.

## تست درخواست

```bash
curl -X POST http://localhost:8001/api/v1/assistant/chat \
  -H 'Content-Type: application/json' \
  -d '{"appId":"ERP","tenantId":"tenant-1","userId":"user-1","prompt":"طبق مستندات داخلی، روند ثبت درخواست خرید چیست؟"}'
```

برای سؤال عمومی، انتظار می‌رود `selectedPath=local_llm` باشد؛ برای سؤال مستندمحور `local_rag`؛ و برای اطلاعات زنده ERP مانند موجودی فعلی، `local_mcp`، مشروط به وجود ابزار مجاز و فعال در MCP Server.

## ذخیره تاریخچه

- مسیر `local_rag` از endpoint فعلی `POST /api/v1/conversations/{id}/messages` استفاده می‌کند و در همان‌جا پاسخ را ذخیره می‌کند.
- مسیرهای `local_llm` و `local_mcp` از endpoint جدید `POST /api/v1/conversations/{id}/assistant-turn` استفاده می‌کنند تا پیام و پاسخ با `selectedPath` و `sources` در PostgreSQL/Redis/RabbitMQ طبق منطق موجود سرویس ذخیره شوند.
- فهرست و بازیابی مکالمه‌ها همچنان از APIهای فعلی Conversations انجام می‌شود.

## وضعیت ERP MCP

در این بسته MCP Client سمت Coordinator وجود دارد، اما MCP Server واقعی ERP و نام ابزارهای عملیاتی هنوز وابسته به Swagger/API واقعی ERP است. نمونه نام‌هایی مانند `inventory_get` در قرارداد فقط مثال‌اند. در `.env` باید ابزارهای فقط‌خواندنی مورد تأیید را در `ERP_MCP_READ_ONLY_TOOLS` تنظیم کنی یا ابزارهای MCP را با `readOnlyHint=true` و بدون `destructiveHint=true` ارائه دهی. سرور MCP باید خودش احراز هویت و مجوز tenant/user را برای هر فراخوانی enforce کند؛ headerهای شناسه کاربر در این پروژه به‌تنهایی قابل اعتماد نیستند.

## اعتبارسنجی

- Python compile check: انجام می‌شود هنگام ساخت بسته.
- تست‌های pytest: فایل‌های تست موجودند؛ اجرای واقعی تست‌ها در محیط هدف لازم است.
- آزمون end-to-end با Ollama، PostgreSQL، Qdrant و MCP Server واقعی در این محیط اجرا نشده است.

## امنیت و نگهداری

- فایل `.env` اصلی عمداً در ZIP قرار نگرفته است تا اطلاعات محرمانه منتشر نشود.
- API کلید داخلی برای endpoint ذخیره پاسخ‌های Coordinator اجباری است. سایر APIهای قدیمی RAG همان رفتار فعلی خود را حفظ کرده‌اند؛ پیش از استقرار تولیدی، احراز هویت و RBAC همه endpointها را بررسی کن.
- سرویس MCP در Compose تعریف نشده چون پیاده‌سازی واقعی ERP MCP هنوز ارائه نشده است.


## فاز پنجم — OpenAI و Model Router

- OpenAI به‌صورت پیش‌فرض خاموش است (`OPENAI_ENABLED=false`). برای فعال‌سازی آگاهانه، `OPENAI_ENABLED=true` و `OPENAI_API_KEY` را در `.env` تنظیم کن. کلید واقعی را در مخزن کد یا ZIP قرار نده.
- `OPENAI_MODEL` مدل مورد استفاده را تعیین می‌کند؛ تنظیمات timeout، retry و سقف خروجی نیز در `.env.example` آمده‌اند.
- مسیر OpenAI فقط برای درخواست عمومی/استدلالی است. پرسش‌های تشخیص‌داده‌شده به‌عنوان داده ERP یا مستندات داخلی به مسیر محلی هدایت می‌شوند. متن پیش از ارسال از چند الگوی رایج ایمیل و شناسه/شماره ماسک می‌شود؛ این کار تضمین ناشناس‌سازی کامل نیست و باید پیش از تولید با سیاست داده سازمان بازبینی شود.
- در صورت شکست درخواست OpenAI، Coordinator تلاش می‌کند پاسخ را با Local LLM تولید کند. اگر Local LLM نیز در دسترس نباشد، درخواست با خطای کنترل‌شده پایان می‌یابد.
- `GET /health/openai` فقط تنظیمات را بررسی می‌کند و درخواست billable به OpenAI نمی‌فرستد.
- مسیرهای Local RAG و ERP MCP در این فاز حذف نشده‌اند. همچنان باید MCP Server واقعی و سیاست دسترسی ERP در محیط هدف اعتبارسنجی شود.

برای بررسی وضعیت OpenAI:

```bash
curl http://localhost:8001/health/openai
```

## فاز ششم — ERP MCP و تأیید عملیات تغییردهنده

فاز ششم مسیر write را اضافه می‌کند، اما اجرای مستقیم ابزارهای تغییردهنده توسط مدل ممنوع است. اگر کاربر عملیاتی مانند «ثبت درخواست خرید» بخواهد، Coordinator ابزار را از allowlist صریح `ERP_MCP_WRITE_TOOLS` انتخاب می‌کند، schema ورودی را اعتبارسنجی می‌کند و یک درخواست `pending` در Redis می‌سازد. عملیات ERP فقط بعد از تأیید از مسیر backend اجرا می‌شود.

### تنظیمات جدید

- `ERP_MCP_WRITE_TOOLS`: فهرست صریح ابزارهای تغییردهنده مجاز؛ ابزارهای `destructiveHint=true` در این فاز رد می‌شوند.
- `ERP_MCP_REQUIRE_USER_TOKEN=true`: هدر Bearer کاربر باید از .NET API/SSO به Coordinator و سپس MCP منتقل شود.
- `REDIS_URL`: محل ذخیره موقت درخواست‌های تأیید و audit؛ در صورت نبود Redis، عملیات write متوقف می‌شود.
- `APPROVAL_API_KEY`: کلید داخلی برای endpointهای تأیید؛ فقط در backend نگهداری شود و به مرورگر نرسد.
- `APPROVAL_TTL_SECONDS=900`: زمان انقضای پیش‌فرض درخواست تأیید.
- `APPROVAL_ALLOW_SELF_APPROVAL=false`: جلوگیری از تأیید درخواست توسط همان درخواست‌کننده.

### مسیرهای جدید

- `GET /health/approvals`
- `GET /api/v1/erp/approvals/{approval_id}?tenantId=...`
- `POST /api/v1/erp/approvals/{approval_id}/approve`
- `POST /api/v1/erp/approvals/{approval_id}/reject`

endpointهای approval باید فقط از .NET Assistant API احراز هویت‌شده فراخوانی شوند. .NET باید نقش تأییدکننده را با SSO/RBAC بررسی کند و کلید داخلی را به کلاینت نهایی ندهد. Coordinator به‌تنهایی مرجع نقش‌های سازمانی نیست.

### محدودیت ادغام با ERP

MCP Server واقعی و ابزارهای نهایی ERP در این ZIP ساخته نشده‌اند، زیرا Swagger/API واقعی ERP در اختیار این بسته نیست. قرارداد و چارچوب سمت Coordinator آماده است؛ برای اجرای end-to-end باید تیم ERP ابزارهای واقعی، schemaها، مجوزها، tenant isolation و idempotency تراکنش‌ها را در MCP Server پیاده‌سازی کند. اگر پاسخ ابزار با خطای شبکه قطع شود، وضعیت `outcome_unknown` ثبت می‌شود و عملیات خودکار تکرار نمی‌شود.


## فاز هفتم — Guardrails سرتاسری

فاز هفتم کنترل‌های دفاعی را پیش از Router، هنگام کار با خروجی ERP MCP و قبل از ذخیره/ارسال پاسخ اعمال می‌کند. تنظیمات در `.env.example` با پیش‌فرض فعال آمده‌اند:

- `GUARDRAILS_ENABLED=true`
- `GUARDRAILS_MAX_PROMPT_CHARS=12000`
- `GUARDRAILS_MAX_OUTPUT_CHARS=16000`
- `GUARDRAILS_MAX_TOOL_RESULT_CHARS=12000`

در این نسخه، درخواست‌های صریح برای افشای پیام سیستمی یا credential پاسخ کنترل‌شده می‌گیرند؛ promptهای دارای نشانه تزریق دستور، PII یا داده سازمانی به OpenAI فرستاده نمی‌شوند؛ خروجی‌های دارای credentialهای شناخته‌شده ماسک می‌شوند؛ و فیلدهای حساس payload ابزار ERP پیش از خلاصه‌سازی حذف/ماسک می‌شوند. این‌ها کنترل‌های heuristic هستند و جایگزین RBAC، ACL اسناد، DLP سازمانی یا بررسی امنیتی نیستند.

جزئیات، محدودیت‌ها و سناریوهای آزمون در `docs/Phase7_Guardrails.fa.md` آمده است.


## بروزرسانی بر پایه opt-assist

تغییرات پروژه RAG و Document API ادغام‌شده‌اند. جزئیات در `docs/Phase7_opt-assist_merge.fa.md` آمده است. فایل `.env` در ZIP قرار ندارد؛ تنظیمات را با حفظ مقادیر محیط فعلی ادغام کنید.
