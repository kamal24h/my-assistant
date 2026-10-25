# به‌روزرسانی Phase 7 بر اساس opt-assist(2)

این بسته از آخرین `opt-assist(2).zip` ساخته شده و قابلیت‌های معماری ERP Smart Assistant تا فاز ۷ را نگه می‌دارد.

## تغییرات واردشده از opt-assist
- نسخه‌های جدید `services/rag_service.py` و `services/reranker_service.py`
- نسخه‌های جدید Conversation/Message service، Redis cache، Document API، ingestion و فرم resolver
- حفظ تغییرات مربوط به feedback: پاسخ‌های liked=False از تاریخچه حذف می‌شوند و liked=True با پیشوند مشخص به تاریخچه می‌روند
- اضافه‌شدن اسکریپت `ensure_qdrant_indexes.py` و مستندات Answer Gateway
- حفظ Reranking و preload مدل در startup

## نقاط ادغام ضروری
- Coordinator و endpoint `assistant-turn` حفظ شده‌اند تا مسیرهای Local LLM و Local MCP بتوانند در همان تاریخچه ذخیره شوند.
- Docker Compose جدید opt-assist حفظ شده و سرویس Coordinator فاز ۷ و متغیرهای API key به آن اضافه شده‌اند.
- Guardrails فاز ۷ در مسیر پاسخ RAG حفظ شده‌اند.
- اگر Qdrant هیچ سندی برنگرداند، RAG یک پاسخ ثابت و کنترل‌شده برمی‌گرداند و LLM را با context خالی صدا نمی‌زند.

## محدودیت‌های اعتبارسنجی
کامپایل و بررسی ایستای ساختارها انجام شده است. اجرای کامل pytest و آزمون End-to-End نیازمند محیط واقعی PostgreSQL، Qdrant، Redis، Ollama و ERP MCP است. این بسته ادعای تست زنده با سرویس‌های مذکور ندارد.

## راه‌اندازی
1. از `.env.example` نمونه بگیر و تنظیمات معتبر محیط فعلی را وارد کن؛ فایل `.env` واقعی را با این بسته جایگزین نکن.
2. مطمئن شو Docker network خارجی `assistant_network` ساخته شده است.
3. برای سرویس FastAPI و Coordinator مقدار یکسانی برای `API_KEY` و `RAG_API_KEY` تنظیم کن.
4. نام ابزارهای MCP را تا زمان تطبیق با MCP واقعی در allowlist فعال نکن.
