# فاز هفتم — Guardrails در کل مسیر پردازش

## هدف

افزودن کنترل‌های دفاعی قطعی در ورودی، مسیریابی مدل، پاسخ خروجی و داده برگشتی از ERP MCP؛ بدون تغییر APIهای قبلی RAG و بدون وابستگی به مدل زبانی برای تصمیم‌های امنیتی پایه.

## پیاده‌سازی

- `coordinator/guardrails.py`: ارزیابی prompt، تشخیص نشانه‌های تزریق دستور، نشانه‌های داده سازمانی و شناسه‌های مستقیم، مسدودکردن درخواست صریح برای افشای پیام سیستمی/اطلاعات احراز هویت، ماسک‌کردن credentialهای شناخته‌شده در خروجی و پاک‌سازی فیلدهای حساس از payload ابزارهای ERP.
- `coordinator/main.py`: گره `input_guardrail` پیش از Router، اجبار به مسیر محلی برای promptهای سازمانی/حساس، پاسخ کنترل‌شده برای درخواست افشای اسرار، محدودسازی طول خروجی و محافظت از داده ERP پیش از خلاصه‌سازی.
- `api/v1/messages.py`: بررسی خروجی RAG پیش از ذخیره پاسخ در تاریخچه.
- `coordinator/openai_service.py`: مسیر OpenAI همچنان از sanitization ورودی استفاده می‌کند؛ routing policy مانع ارسال promptهای تشخیص‌داده‌شده به‌عنوان ERP/داخلی، دارای PII یا تزریق دستور به OpenAI می‌شود.
- `.env.example` و `docker-compose.yml`: تنظیمات قابل کنترل برای guardrails و سقف طول prompt/output/tool result.

## تنظیمات

```dotenv
GUARDRAILS_ENABLED=true
GUARDRAILS_MAX_PROMPT_CHARS=12000
GUARDRAILS_MAX_OUTPUT_CHARS=16000
GUARDRAILS_MAX_TOOL_RESULT_CHARS=12000
```

توصیه می‌شود در محیط تولید `GUARDRAILS_ENABLED=true` بماند. خاموش‌کردن این تنظیمات فقط برای آزمایش کنترل‌شده و با پذیرش ریسک مجاز است.

## محدودیت‌ها و موارد لازم پیش از تولید

1. این کنترل‌ها heuristic و دفاع در عمق هستند؛ تشخیص تزریق دستور یا اطلاعات شخصی کامل نیست.
2. مجوز واقعی، tenant isolation و اعتبار SSO باید در ERP API/MCP Server enforce شود؛ Coordinator جایگزین RBAC نیست.
3. دسترسی کاربر به اسناد باید هنگام retrieval در RAG enforce شود. guardrails جایگزین ACL فیلترشده در Qdrant/metadata نیست.
4. داده‌ای که از ERP یا اسناد می‌آید محتوای غیرقابل‌اعتماد است؛ دستورهای داخل آن نباید به‌عنوان دستور سیستمی اجرا شوند.
5. ماسک‌کردن credentialهای آشکار تضمین نمی‌کند که خروجی کاملاً فاقد اطلاعات محرمانه باشد؛ بازبینی DLP سازمانی و آزمون red-team لازم است.
6. تست کامل pytest و E2E با Ollama، RAG، Redis و ERP MCP واقعی باید در محیط استقرار اجرا شود.

## آزمون‌های پایه

- prompt شامل داده سازمانی نباید به OpenAI هدایت شود.
- prompt حاوی نشانه تزریق دستور باید از OpenAI دور بماند.
- درخواست افشای system prompt یا credential باید پاسخ کنترل‌شده بگیرد.
- کلید یا Bearer token شناخته‌شده در خروجی باید ماسک شود.
- payload ابزار ERP باید پیش از خلاصه‌سازی از فیلدهای secret-like پاک شود.
- عملیات تغییردهنده همچنان باید از فاز ۶ و گردش‌کار تأیید انسانی عبور کند.

## وضعیت بررسی این بسته

- `compileall` برای `coordinator/`, `api/` و تست‌ها موفق بود.
- اعتبارسنجی YAML مربوط به Docker Compose موفق بود.
- پنج تست مستقل `tests_coordinator/test_guardrails.py` اجرا و موفق شدند.
- مجموعه کامل تست Coordinator به‌علت نصب‌نبودن `langchain_core` در محیط ساخت، در مرحله collection اجرا نشد؛ باید داخل image/محیطی که `requirements-coordinator.txt` را نصب کرده است اجرا شود.
- آزمون یکپارچه با سرویس‌های در حال اجرا و MCP Server واقعی انجام نشده است.
