# بروزرسانی فاز ۷ بر پایه opt-assist

این بسته از پروژه یکپارچه ERP Smart Assistant فاز ۷ به‌عنوان پایه استفاده می‌کند و تغییرات RAG موجود در `opt-assist-P1-patch.zip` را نیز ادغام می‌کند.

## تغییرات ادغام‌شده
- حفظ Coordinator فاز ۷: LangGraph، Local LLM، Local RAG، OpenAI، ERP MCP، approvals و guardrails.
- انتقال نسخه جدید Document API و قابلیت‌های Batch/Upsert/Versioning از opt-assist.
- انتقال reranking service و وابستگی‌های آن.
- ادغام `form_resolver.py` و `data/menu_forms.json` و بازگرداندن `formId` در `meta_info` پاسخ RAG.
- حفظ guard_output فاز ۷ در endpoint پیام RAG.
- ادغام بهبودهای ثبت feedback/RabbitMQ و شناسه chunk/hash در ingest.
- افزودن preload اختیاری reranker در startup؛ شکست preload مانع بالا آمدن API نمی‌شود.

## امنیت و پیکربندی
- فایل `.env` عمداً در بسته نیست؛ فایل `.env.example` فاز ۷ را با تنظیمات محیط فعلی ادغام کنید و secrets واقعی را نگه دارید.
- ابزارهای واقعی MCP، RBAC سمت ERP و تست end-to-end باید در محیط واقعی اعتبارسنجی شوند.

## اعتبارسنجی این بسته
- بررسی نحوی فایل‌های Python و ساختار YAML انجام شده است.
- اجرای کامل pytest و اجرای سرویس‌ها با دیتابیس/Qdrant/Ollama/MCP واقعی در این محیط انجام نشده است.
