# فاز ۶ — اتصال ERP MCP و اجرای کنترل‌شده عملیات تغییردهنده

## هدف

این فاز مسیر ERP MCP را از نمونه‌ی فقط‌خواندنی به یک قرارداد عملیاتی توسعه می‌دهد و چارچوب تأیید انسانی برای عملیات تغییردهنده فراهم می‌کند. MCP Server واقعی ERP در این مخزن پیاده‌سازی نشده است؛ نام ابزارها و schemaها باید با Swagger/API واقعی ERP و تیم مالک سرویس تطبیق داده شوند.

## معماری و مرزبندی مسئولیت‌ها

1. **Coordinator/LangGraph** فقط درخواست را دسته‌بندی می‌کند، ابزار مجاز را از فهرست محدود انتخاب می‌کند و در عملیات تغییردهنده یک پیشنهاد می‌سازد.
2. **MCP Client** فهرست ابزارها را دوباره از سرور می‌خواند، allowlist را بررسی می‌کند و `inputSchema` را اعتبارسنجی می‌کند.
3. **Redis Approval Store** درخواست تأییدشده‌نشده را با TTL ذخیره می‌کند؛ در دسترس نبودن Redis باعث توقف امن عملیات می‌شود.
4. **.NET Assistant API / SSO** باید هویت واقعی کاربر و نقش تأییدکننده را اعتبارسنجی کند و APIهای approval را به‌صورت server-to-server فراخوانی کند. کلید داخلی Coordinator نباید به مرورگر داده شود.
5. **ERP MCP Server** مرجع نهایی احراز هویت، tenant isolation، RBAC، اعتبارسنجی کسب‌وکار و اجرای تراکنش است. Coordinator جایگزین مجوزهای ERP نیست.

## ابزارها

### ابزارهای فقط‌خواندنی

- `ERP_MCP_READ_ONLY_TOOLS`: allowlist نام ابزارهای query.
- ابزارهای دارای `readOnlyHint=true` قابل قبول‌اند، مگر اینکه destructive علامت خورده باشند یا صریحاً `readOnlyHint=false` داشته باشند.

### ابزارهای تغییردهنده

- `ERP_MCP_WRITE_TOOLS`: allowlist صریح و جداگانه؛ ابزار write صرفاً با annotation یا انتخاب مدل فعال نمی‌شود.
- ابزارهایی با `destructiveHint=true` در این فاز رد می‌شوند. حذف/لغو مخرب باید سیاست و گردش‌کار مجزای خودش را داشته باشد.
- `inputSchema` اجباری است و arguments قبل از ذخیره و دوباره در زمان اجرا اعتبارسنجی می‌شوند.
- مدل اجازه اجرای مستقیم عملیات ندارد. درخواست write فقط یک رکورد `pending` ایجاد می‌کند.

نمونه‌ی پیشنهادی برای MCP Server (باید با API واقعی تطبیق داده شود):

```json
{
  "name": "purchase_request_create",
  "description": "ایجاد پیش‌نویس درخواست خرید در محدوده مجوز کاربر",
  "inputSchema": {
    "type": "object",
    "properties": {
      "item_code": { "type": "string", "minLength": 1, "maxLength": 64 },
      "quantity": { "type": "number", "exclusiveMinimum": 0 },
      "justification": { "type": "string", "maxLength": 1000 }
    },
    "required": ["item_code", "quantity", "justification"],
    "additionalProperties": false
  },
  "annotations": { "readOnlyHint": false, "destructiveHint": false }
}
```

## گردش‌کار تأیید

1. کاربر درخواست تغییردهنده می‌دهد.
2. Coordinator آن را به `erp_write` می‌فرستد، ابزار را فقط از `ERP_MCP_WRITE_TOOLS` انتخاب می‌کند و arguments را با schema اعتبارسنجی می‌کند.
3. رکورد `pending` در Redis با TTL پیش‌فرض ۱۵ دقیقه ذخیره می‌شود؛ **هیچ عملیات ERP در این مرحله اجرا نمی‌شود**.
4. .NET API با SSO/RBAC تأییدکننده، جزئیات پیشنهاد را از endpoint داخلی می‌گیرد و برای کاربر مجاز نمایش می‌دهد.
5. پس از تأیید، Coordinator وضعیت را به `executing` تغییر می‌دهد، ابزار را دوباره از MCP فهرست و اعتبارسنجی می‌کند و با bearer token تأییدکننده اجرا می‌کند.
6. عملیات موفق، ردشده، ناموفق، منقضی یا با نتیجه نامشخص در Redis audit ثبت می‌شود. در خطای شبکه‌ای هنگام اجرای ابزار، وضعیت `outcome_unknown` می‌شود و اجرای خودکار مجدد ممنوع است تا ابتدا وضعیت ERP بررسی شود.

## Endpointهای جدید

- `GET /health/approvals`: سلامت اتصال Redis.
- `GET /api/v1/erp/approvals/{approval_id}?tenantId=...`: جزئیات درخواست برای نمایش در UI تأیید؛ فقط از .NET API احراز هویت‌شده فراخوانی شود.
- `POST /api/v1/erp/approvals/{approval_id}/approve`: تأیید و اجرای ابزار.
- `POST /api/v1/erp/approvals/{approval_id}/reject`: رد درخواست.

تمام endpointهای approval به `X-API-Key` داخلی نیاز دارند. approve/reject همچنین bearer token تأییدکننده را لازم دارند. نقش تأییدکننده باید در .NET API/SSO بررسی شود؛ Coordinator به‌تنهایی مرجع RBAC سازمانی نیست.

نمونه body برای approve/reject:

```json
{
  "tenantId": "tenant-1",
  "approverUserId": "approver-42",
  "comment": "پس از بررسی تأیید شد"
}
```

## تنظیمات محیطی

```dotenv
ERP_MCP_URL=http://erp-mcp:8002/mcp
ERP_MCP_BEARER_TOKEN=
ERP_MCP_REQUIRE_USER_TOKEN=true
ERP_MCP_READ_ONLY_TOOLS=inventory_get;purchase_order_status_get
ERP_MCP_WRITE_TOOLS=purchase_request_create;purchase_order_draft_create
REDIS_URL=redis://redis:6379/0
APPROVAL_API_KEY=replace_with_a_long_random_internal_api_key
APPROVAL_TTL_SECONDS=900
APPROVAL_ALLOW_SELF_APPROVAL=false
```

`ERP_MCP_REQUIRE_USER_TOKEN=true` پیش‌فرض است؛ .NET API باید توکن SSO کاربر را در هدر `Authorization: Bearer ...` به Coordinator ارسال کند. توکن‌ها در Redis ذخیره نمی‌شوند. `APPROVAL_API_KEY` فقط بین سرویس‌های backend نگهداری شود.

## محدودیت‌های باقی‌مانده

- نام ابزارها و schemaهای نمونه، قرارداد نهایی ERP نیستند؛ برای فعال‌سازی write باید Swagger و سیاست‌های واقعی ERP بررسی شوند.
- MCP Server واقعی، نقش‌ها، tenant isolation و transaction/idempotency باید سمت ERP پیاده‌سازی شوند.
- قفل Redis جلوی تأیید هم‌زمان یک درخواست را می‌گیرد، اما idempotency تجاری باید در ERP نیز پشتیبانی شود.
- اگر فراخوانی ERP timeout شود، نتیجه ممکن است نامشخص باشد؛ قبل از retry، وضعیت سند در ERP را بررسی کنید.
- self-approval به‌صورت پیش‌فرض ممنوع است. بررسی نقش و مجوز تأییدکننده بر عهده لایه .NET/SSO است.
- اجرای واقعی با ERP، Redis و SSO در محیط مقصد باید انجام شود؛ تست‌های این بسته به‌تنهایی جایگزین تست end-to-end نیستند.
