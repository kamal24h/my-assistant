
تست ۱ — سؤال مبهم بدون تاریخچه
bash
curl -s -X POST http://127.0.0.1:8003/api/v1/assistant/chat \
  -H "X-API-Key: $ASSISTANT_API_KEY" -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"appId":"a","tenantId":"t","userId":"u","prompt":"این چیه؟"}'
انتظار: status: "clarification_required", selectedPath: "clarification_pending", answer شامل ۱-۲ سؤال تکمیلی.

تست ۲ — سؤال واضح
bash
curl -s -X POST http://127.0.0.1:8003/api/v1/assistant/chat \
  -H "X-API-Key: $ASSISTANT_API_KEY" -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"appId":"a","tenantId":"t","userId":"u","prompt":"رویه ثبت درخواست خرید در سیستم ERP چیست؟"}'
انتظار: status: "completed", selectedPath: "local_rag" (یا local_llm)، پاسخ مستقیم.

تست ۳ — ادامه‌ی مکالمه (بعد از clarification)
bash
# از conversationId که در تست ۱ گرفتی استفاده کن
curl -s -X POST http://127.0.0.1:8003/api/v1/assistant/chat \
  -H "X-API-Key: $ASSISTANT_API_KEY" -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"appId":"a","tenantId":"t","userId":"u","conversationId":"<conv-id>","prompt":"منظورم موجودی انبار است"}'
انتظار: status: "completed", selectedPath: "local_rag" یا local_mcp — یعنی این بار clarification نپرسید و از تاریخچه استفاده کرد.

تست ۴ — سؤال بسیار کوتاه
bash
curl -s -X POST http://127.0.0.1:8003/api/v1/assistant/chat \
  -H "X-API-Key: $ASSISTANT_API_KEY" -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"appId":"a","tenantId":"t","userId":"u","prompt":"کمک"}'
انتظار: status: "clarification_required".

تست ۵ — ERP write (نباید clarification بگیرد)
bash
curl -s -X POST http://127.0.0.1:8003/api/v1/assistant/chat \
  -H "X-API-Key: $ASSISTANT_API_KEY" -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"appId":"a","tenantId":"t","userId":"u","prompt":"یک درخواست خرید ثبت کن"}'
انتظار: status: "pending_approval", selectedPath: "erp_write_pending" — clarification نشد.

تست ۶ — خروجی کوتاه‌تر
bash
# سؤال کلی که قبلاً پاسخ طولانی می‌گرفت
curl -s -X POST http://127.0.0.1:8003/api/v1/assistant/chat \
  -H "X-API-Key: $ASSISTANT_API_KEY" -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"appId":"a","tenantId":"t","userId":"u","prompt":"موجودی انبار چطور محاسبه می‌شود؟"}'
انتظار: پاسخ حداکثر ۳ پاراگراف یا ۵۰۰ کلمه.