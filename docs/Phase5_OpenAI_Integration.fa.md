# فاز ۵ — اتصال کنترل‌شده OpenAI

## هدف
افزودن مسیر اختیاری OpenAI برای درخواست‌های عمومی و استدلالی، بدون حذف یا وابسته‌کردن مسیرهای Local LLM، Local RAG و ERP MCP.

## تغییرات این فاز
- افزودن گره `openai` به LangGraph و برچسب `openai` به Model Router.
- استفاده از OpenAI SDK ناهمگام با تنظیم مدل از متغیر محیطی.
- پیش‌فرض خاموش (`OPENAI_ENABLED=false`) و عدم ارسال کلید یا داده‌های `metadata` به OpenAI.
- ماسک‌کردن الگوهای رایج ایمیل، شماره تلفن و شناسه‌های عددی قبل از درخواست خارجی.
- سقف طول ورودی، سقف خروجی، timeout، retry محدود، سقف هم‌زمانی و rate limit ساده در سطح هر process.
- fallback به Local LLM در صورت خطای OpenAI یا ورودی بیش‌ازحد طولانی.
- ثبت پاسخ و مسیر انتخاب‌شده در Conversation Store فعلی.
- endpoint تنظیمات `GET /health/openai` بدون ارسال درخواست billable.

## سیاست مسیریابی
1. سؤال‌هایی که به اطلاعات زنده ERP وابسته‌اند، به `local_mcp` هدایت می‌شوند.
2. سؤال‌های مستندمحور و سازمانی به `local_rag` هدایت می‌شوند.
3. اگر OpenAI فعال و کلید تنظیم شده باشد، Router می‌تواند درخواست عمومی و پیچیده را به `openai` بفرستد.
4. سایر درخواست‌ها به `local_llm` می‌روند.
5. خطای OpenAI باعث تلاش مجدد نامحدود نمی‌شود؛ پس از retry محدود، مسیر محلی استفاده می‌شود.

## تنظیمات
مقادیر در `.env.example` آمده‌اند. حداقل متغیرهای لازم برای فعال‌سازی عبارت‌اند از:

```dotenv
OPENAI_ENABLED=true
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
OPENAI_TIMEOUT_SECONDS=25
OPENAI_MAX_RETRIES=1
OPENAI_MAX_TOKENS=800
OPENAI_MAX_INPUT_CHARS=4000
OPENAI_MAX_CONCURRENCY=4
OPENAI_MAX_REQUESTS_PER_MINUTE=30
```

## آزمون‌ها و محدودیت‌های اعتبارسنجی
- `compileall` و parse فایل Compose در محیط توسعه بررسی می‌شوند.
- اجرای واقعی pytest و آزمون end-to-end نیازمند نصب وابستگی‌ها و اجرای سرویس‌های محیط مقصد است.
- الگوهای ماسک‌سازی تضمین ناشناس‌سازی کامل نیستند. قبل از تولید باید سیاست DLP سازمان، طبقه‌بندی داده و الزامات حقوقی بررسی شوند.
- rate limit این فاز درون‌حافظه‌ای و برای هر process است؛ در اجرای چند worker/container مشترک نیست. برای محدودیت دقیق سراسری، بودجه دلاری یا quota سازمانی، باید در فاز سخت‌سازی به Redis یا سرویس مرکزی cost accounting متصل شود.
