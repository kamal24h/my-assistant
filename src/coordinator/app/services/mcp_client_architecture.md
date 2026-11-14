
# توضیح کامل `MCP Client` در این پروژه‌

## نقش کلی

`MCP Client` (`src/coordinator/app/services/mcp_client.py`) یک **پل ارتباطی بین Coordinator و ERP MCP Server** است. این سرویس:

1. **با MCP Server (خارجی) از طریق پروتکل MCP Streamable HTTP صحبت می‌کند.**
2. **ابزارهای خواندنی و نوشتنی ERP را کشف و فیلتر می‌کند.**
3. **ابزارها را با argumentهای معتبر فراخوانی می‌کند.**
4. **SSO token کاربر را به MCP منتقل می‌کند** (تا MCP خودش RBAC و tenant isolation را اعمال کند).
5. **خطاهای شبکه/پروتکل را به کدهای معنادار تبدیل می‌کند.**

---

## ۱. معماری ارتباط

```
┌──────────────────────────────────────────────────────────────────┐
│ Coordinator (workflow.py)                                        │
│                                                                  │
│  local_mcp_node          erp_write_node          planning_node   │
│       │                       │                       │          │
│       ▼                       ▼                       ▼          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  ErpMcpClient (mcp_client.py)                               │ │
│  │                                                             │ │
│  │  - list_read_only_tools()   → tools/list (read allowlist)   │ │
│  │  - list_write_tools()       → tools/list (write allowlist)  │ │
│  │  - call_tool()              → tools/call (read)             │ │
│  │  - call_write_tool()        → tools/call (write)            │ │
│  │  - health()                 → tools/list (all)              │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
└─────────────────────────────┼────────────────────────────────────┘
                              │
                              │ HTTPS (MCP Streamable HTTP)
                              │ + Authorization: Bearer <SSO>
                              │ + X-ERP-Tenant-Id / X-ERP-User-Id
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ ERP MCP Server (External ASP.NET Core Kestrel)                    │
│                                                                   │
│  - initialize (handshake)                                         │
│  - tools/list   (کشف ابزارها)                                    │
│  - tools/call   (اجرای ابزار)                                    │
│                                                                   │
│  - MCP خودش: SSO validation, RBAC, tenant isolation               │
│  - MCP خودش: ارتباط با ERP APIs (REST/Swagger)                   │
└───────────────────────────────────────────────────────────────────┘
```

**نکته‌ی کلیدی:** MCP Client **تصمیم نمی‌گیرد** که کدام ابزار با چه argumentهایی اجرا شود — این کار **LLM (در `select_erp_tool`) و Coordinator (در `local_mcp_node` / `erp_write_node`)** است. MCP Client فقط **پروتکل MCP را پیاده می‌کند** و **سیاست allowlist** را اعمال می‌کند.

---

## ۲. پروتکل MCP (Model Context Protocol) — Streamable HTTP

**MCP** یک پروتکل استاندارد (از Anthropic) برای ارتباط LLM با ابزارها است. **Streamable HTTP** یکی از transportهای MCP است (جایگزین SSE قدیمی).

### جریان یک درخواست MCP

هر درخواست MCP یک **JSON-RPC 2.0** است:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_order_status",
    "arguments": {"order_number": "SO-12345"}
  }
}
```

**پاسخ:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{"type": "text", "text": "..."}],
    "structuredContent": {"order_number": "SO-12345", "status": "shipped"}
  }
}
```

**یا خطا:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {"code": -32602, "message": "Invalid params"}
}
```

### جریان کامل در `mcp_client.py`

برای **هر** فراخوانی ابزار (`call_tool` / `call_write_tool`)، MCP Client این مراحل را طی می‌کند:

```
1. POST /mcp  → initialize (handshake)
   ← response شامل Mcp-Session-Id (در header)

2. POST /mcp  → notifications/initialized
   (بدون id، فقط notification)

3. POST /mcp  → tools/list
   ← لیست همه‌ی ابزارها (name, description, inputSchema, annotations)

4. [فیلتر allowlist] → فقط ابزارهای مجاز
   - read: readOnlyHint=true یا در ERP_MCP_READ_ONLY_TOOLS
   - write: در ERP_MCP_WRITE_TOOLS

5. [validate arguments] → jsonschema روی inputSchema
   (اگر argument نامعتبر → McpClientError: erp_mcp_tool_arguments_invalid)

6. POST /mcp  → tools/call (name, arguments)
   ← نتیجه یا خطا

7. [بررسی isError] → اگر isError=true → McpClientError: erp_mcp_tool_failed

8. return {"content": [...], "structuredContent": {...}}
```

**نکته:** مراحل ۱-۴ برای **هر** `call_tool` دوباره اجرا می‌شوند (چون MCP session ممکن است بین درخواست‌ها expire شود). **این overhead است** (۲-۳ درخواست HTTP اضافه) — **بهینه‌سازی در آینده:** cache کردن `tools/list` برای ۵ دقیقه.

---

## ۳. مکانیزم Allowlist (سیاست امنیتی)

MCP Client **هیچ ابزاری را بدون allowlist اجرا نمی‌کند.** این **قلب امنیت** است.

### برای ابزارهای خواندنی (`list_read_only_tools`)

```python
def _allowed_tools(self, tools):
    configured = self._configured_names(settings.erp_mcp_read_only_tools)
    safe = []
    for tool in tools:
        name = tool["name"]
        annotations = tool.get("annotations") or {}
        explicitly_allowed = name in configured
        marked_read_only = annotations.get("readOnlyHint") is True
        explicitly_not_read_only = annotations.get("readOnlyHint") is False
        destructive = annotations.get("destructiveHint") is True

        if (name and not destructive and not explicitly_not_read_only
            and (explicitly_allowed or marked_read_only)):
            safe.append(tool)
    return safe
```

**قواعد:**
- `readOnlyHint=true` → **مجاز** (بدون نیاز به allowlist).
- `readOnlyHint=false` → **غیرمجاز** (حتی اگر در allowlist باشد).
- `destructiveHint=true` → **غیرمجاز** (حتی اگر readOnlyHint=true باشد — contradiction).
- `readOnlyHint` نامشخص + در `ERP_MCP_READ_ONLY_TOOLS` → **مجاز** (allowlist).
- `readOnlyHint` نامشخص + نه در allowlist → **غیرمجاز**.

**نتیجه:** ابزار خواندنی فقط اگر **صریحاً** read-only باشد یا در allowlist باشد.

### برای ابزارهای نوشتنی (`list_write_tools`)

```python
def _allowed_write_tools(self, tools):
    configured = self._configured_names(settings.erp_mcp_write_tools)
    safe = []
    for tool in tools:
        name = tool["name"]
        annotations = tool.get("annotations") or {}
        if (name in configured
            and annotations.get("readOnlyHint") is not True
            and annotations.get("destructiveHint") is not True
            and isinstance(tool.get("inputSchema"), dict)):
            safe.append(tool)
    return safe
```

**قواعد (سخت‌گیرانه‌تر):**
- **باید در `ERP_MCP_WRITE_TOOLS` باشد** (حتی اگر readOnlyHint=false باشد، کافی نیست).
- **نباید** `readOnlyHint=true` باشد.
- **نباید** `destructiveHint=true` باشد.
- **باید** `inputSchema` معتبر داشته باشد (برای validation).

**نتیجه:** ابزار نوشتنی فقط اگر **صریحاً** در allowlist باشد (مدیر باید آن را اضافه کند). **LLM نمی‌تواند ابزار جدید بسازد.**

**این لایه، جلوی "LLM یک ابزار خطرناک را انتخاب کند" را می‌گیرد.** حتی اگر LLM بگوید `delete_all_customers`، اگر در `ERP_MCP_WRITE_TOOLS` نباشد، رد می‌شود.

---

## ۴. انتقال هویت کاربر (SSO)

**نکته‌ی حیاتی:** MCP Server مسئول **RBAC و tenant isolation** است. **MCP Client فقط SSO token را forward می‌کند.**

```python
def _headers(self, tenant_id, user_id):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-03-26",
    }
    if self.authorization:
        headers["Authorization"] = self.authorization   # ← SSO token کاربر
    elif settings.erp_mcp_bearer_token:
        headers["Authorization"] = f"Bearer {settings.erp_mcp_bearer_token}"   # ← fallback (service token)
    if self._session_id:
        headers["Mcp-Session-Id"] = self._session_id
    if tenant_id:
        headers["X-ERP-Tenant-Id"] = tenant_id   # ← hint (MCP باید خودش استخراج کند)
    if user_id:
        headers["X-ERP-User-Id"] = user_id       # ← hint
    return headers
```

**نکات:**
- **`Authorization: Bearer <SSO>`** — از کلاینت (Assistant API) → Coordinator → MCP Client → MCP.
- **`ERP_MCP_BEARER_TOKEN`** — یک **service token** برای health check (وقتی کاربر SSO ندارد، مثل `health()`).
- **`X-ERP-Tenant-Id` و `X-ERP-User-Id`** — **فقط hint**. MCP **باید** خودش این‌ها را از SSO token استخراج کند (چون header قابل جعل است). **این یک قرارداد امنیتی است.**

**پس:** اگر کاربر A سعی کند به سفارش کاربر B دسترسی پیدا کند، MCP (با SSO validation) رد می‌کند. **MCP Client نمی‌تواند این را دور بزند** (چون SSO token کاربر A را forward می‌کند، نه B).

---

## ۵. جداسازی Read vs Write

**MCP Client دو متد جداگانه دارد:**

| متد | allowlist | کاربرد |
|---|---|---|
| `list_read_only_tools()` / `call_tool()` | `ERP_MCP_READ_ONLY_TOOLS` + `readOnlyHint` | `local_mcp_node`، `planning_node` |
| `list_write_tools()` / `call_write_tool()` | `ERP_MCP_WRITE_TOOLS` (strict) | `erp_write_node`، `approve_erp_operation` |

**چرا جدا؟**
- **`local_mcp_node`** (خواندن) → کاربر فقط می‌خواهد اطلاعات ببیند. **ابزار خواندنی کافی است.**
- **`erp_write_node`** (نوشتن) → نیاز به **approval** (انسان در حلقه). **MCP Client فقط ابزار نوشتنی را از allowlist قبول می‌کند، و Coordinator approval flow را اجرا می‌کند.**

**نتیجه:** حتی اگر LLM در `local_mcp_node` یک ابزار نوشتنی انتخاب کند، **MCP Client آن را رد می‌کند** (چون `list_read_only_tools` فقط read-only برمی‌گرداند).

---

## ۶. Validation Arguments (jsonschema)

**قبل از `tools/call`، MCP Client argumentها را با `inputSchema` ابزار validate می‌کند:**

```python
def validate_tool_arguments(tool, arguments):
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        raise McpClientError("erp_mcp_tool_schema_missing")
    try:
        validate(instance=arguments, schema=schema)
    except ValidationError:
        raise McpClientError("erp_mcp_tool_arguments_invalid")
```

**مثال:** اگر ابزار `get_order_status`، `inputSchema` = `{"type": "object", "properties": {"order_number": {"type": "string", "pattern": "^SO-[0-9]+$"}}, "required": ["order_number"]}` داشته باشد، و LLM argument `{"order_number": "invalid"}` بدهد، **MCP Client رد می‌کند** (قبل از ارسال به MCP).

**مزیت:** کاهش درخواست‌های نامعتبر به MCP + خطاهای واضح‌تر.

**نکته:** MCP **هم** argumentها را validate می‌کند (defense in depth). **MCP Client فقط لایه‌ی اول است.**

---

## ۷. مدیریت Session (MCP Streamable HTTP)

**MCP Streamable HTTP از `Mcp-Session-Id` برای maintain کردن session بین درخواست‌ها استفاده می‌کند.**

```python
def __init__(self, ...):
    self._session_id = None   # ← per-client instance

# در _post:
sid = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id")
if sid:
    self._session_id = sid
```

**نکته:** `ErpMcpClient` **per-request** ساخته می‌شود (در `local_mcp_node`: `ErpMcpClient(authorization=...)`). **پس session بین درخواست‌های مختلف به اشتراک گذاشته نمی‌شود.** **این برای Streamable HTTP امن‌تر است** (چون هر کاربر session جدا دارد).

**در `call_tool` / `list_*`، `self._session_id = None` قبل از شروع** (تا از session قبلی استفاده نشود).

---

## ۸. Parsing پاسخ (JSON vs SSE)

**MCP Streamable HTTP می‌تواند پاسخ را به دو صورت بدهد:**

- **JSON** (`application/json`): پاسخ یک JSON-RPC object.
- **SSE** (`text/event-stream`): پاسخ یک stream از `data:` خطوط.

**MCP Client هر دو را پشتیبانی می‌کند:**

```python
if "text/event-stream" in content_type:
    for line in response.text.splitlines():
        if line.startswith("data:"):
            raw = line[5:].strip()
            if raw:
                candidate = json.loads(raw)
                if "result" in candidate or "error" in candidate:
                    return candidate
    raise McpClientError("invalid_erp_mcp_response")
else:
    payload_out = response.json()
    if not isinstance(payload_out, dict):
        raise McpClientError("invalid_erp_mcp_response")
    return payload_out
```

**مثال SSE:**
```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}

```

**چرا SSE؟** MCP Streamable HTTP می‌تواند برای **long-running tool calls** از SSE استفاده کند (streaming نتایج). **MCP Client فقط اولین `data:` با `result`/`error` را می‌خواند** (کافی برای این پروژه).

---

## ۹. Health Check

**`health()`** برای بررسی سلامت MCP:

```python
async def health(self):
    self._session_id = None
    try:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            tools = await self._list_tools_with_client(client, "health-check", "health-check", "all")
        return isinstance(tools, list)
    except McpClientError:
        return False
```

**نکته:** `health()` از `list_tools_with_client(..., "all")` استفاده می‌کند (بدون allowlist) — **چون فقط بررسی اتصال است، نه اجرای ابزار.** **`health()` می‌تواند از `ERP_MCP_BEARER_TOKEN` (service token) استفاده کند** (اگر `ERP_MCP_REQUIRE_USER_TOKEN=false` باشد یا service token تنظیم شده باشد).

---

## ۱۰. جدول خطاها (`McpClientError.code`)

| کد | علت | راه‌حل |
|---|---|---|
| `erp_mcp_user_token_required` | `ERP_MCP_REQUIRE_USER_TOKEN=true` و `Authorization` خالی | کلاینت باید SSO بفرستد (یا `false` کن) |
| `erp_mcp_unavailable` | `ConnectTimeout` / `ConnectError` / `HTTPError` | MCP از دسترس نیست (فایروال/شبکه) |
| `invalid_erp_mcp_response` | پاسخ غیر JSON / غیر SSE | MCP باگ دارد |
| `erp_mcp_rpc_failed` | پاسخ JSON-RPC با `error` | MCP خطا داده (argument نامعتبر، ...) |
| `erp_mcp_tool_not_allowed` | ابزار در allowlist نیست | ابزار را در `.env` اضافه کن |
| `erp_mcp_tool_arguments_invalid` | argument با `inputSchema` نمی‌خواند | LLM argument را درست بده |
| `erp_mcp_tool_schema_missing` | `inputSchema` وجود ندارد | MCP باگ دارد |
| `erp_mcp_tool_failed` | `isError=true` در پاسخ | MCP خطا داده (ERP خطا، ...) |
| `invalid_erp_mcp_tools_response` | `tools/list` پاسخ معتبر نیست | MCP باگ دارد |
| `no_read_only_erp_tools_available` | هیچ ابزار read-only موجود نیست | MCP tools ندارند / allowlist خالی |
| `no_matching_erp_tool` | LLM ابزار مناسبی انتخاب نکرد | LLM/ابزارها را بررسی کن |

**`no_read_only_erp_tools_available`** و **`no_matching_erp_tool`** در `workflow.py` raise می‌شوند (نه در `mcp_client.py`) — ولی هر دو `McpClientError` هستند.

---

## ۱۱. مثال جریان کامل (وضعیت سفارش)

**کاربر:** «وضعیت سفارش SO-12345 چیه؟»

```
1. Client → Assistant API → Coordinator /chat (با Authorization: Bearer SSO)
2. Coordinator: intent_classifier → ERP_DATA_QUERY
3. Coordinator: local_mcp_node
   a. ErpMcpClient(authorization=Bearer SSO)
   b. list_read_only_tools()
      - POST /mcp → initialize (handshake)
      - POST /mcp → tools/list
      - filter: read-only allowlist (مثلاً get_order_status)
   c. select_erp_tool(prompt, tools) → LLM انتخاب می‌کند:
      {"name": "get_order_status", "arguments": {"order_number": "SO-12345"}}
   d. call_tool("get_order_status", {"order_number": "SO-12345"})
      - POST /mcp → initialize
      - POST /mcp → tools/list (دوباره)
      - validate arguments
      - POST /mcp → tools/call
      - response: {"structuredContent": {"order_number": "SO-12345", "status": "shipped"}}
4. Coordinator: summarize_erp_result → LLM (external یا local) → پاسخ فارسی
5. Coordinator → Assistant API → Client
```

**SSO token در تمام مسیر (Assistant → Coordinator → MCP Client → MCP) forward می‌شود.** MCP خودش RBAC را اعمال می‌کند.

---

## ۱۲. چه چیزی MCP Client **انجام نمی‌دهد**؟

| کار | مسئول |
|---|---|
| انتخاب ابزار | LLM (`select_erp_tool`) |
| ساخت argumentها | LLM (`select_erp_tool`) |
| تصمیم‌گیری approval | Coordinator (`erp_write_node`) |
| اجرای approval | Coordinator (`approve_erp_operation`) |
| RBAC / tenant isolation | **MCP Server** (با SSO validation) |
| ارتباط با ERP APIs | **MCP Server** (REST/Swagger) |
| ذخیره conversation | RAG Service (Postgres) |

**MCP Client فقط:**
- پروتکل MCP را پیاده می‌کند.
- allowlist را اعمال می‌کند.
- argumentها را validate می‌کند.
- SSO را forward می‌کند.
- خطاها را normalize می‌کند.

---

## ۱۳. محدودیت‌های فعلی (برای آینده)

| # | محدودیت | بهبود پیشنهادی |
|---|---|---|
| 1 | هر `call_tool` دوباره `initialize` + `tools/list` می‌زند (overhead) | cache `tools/list` برای ۵ دقیقه (per tenant+user) |
| 2 | `health()` از `list_tools_with_client("all")` استفاده می‌کند (بدون allowlist) | health check سبک‌تر (مثلاً `POST /mcp` با `ping`) |
| 3 | `McpClientError` فقط `code` دارد (بدون `http_status` یا `original_error`) | افزودن `__cause__` و `status` برای debug |
| 4 | `ErpMcpClient` per-request ساخته می‌شود (بدون connection pooling) | `httpx.AsyncClient` در `lifespan` ساخته شود |
| 5 | Allowlist از env خوانده می‌شود (بدون hot reload) | allowlist در DB/Redis با TTL |
| 6 | `X-ERP-Tenant-Id` / `X-ERP-User-Id` (hint) قابل جعل است | MCP باید مستقل از این‌ها، از SSO استخراج کند (که الان همین کار را می‌کند) |
| 7 | `McpClientError` در `workflow.py` به `502` تبدیل می‌شود | `502` برای همه‌ی کدها مناسب نیست (مثلاً `erp_mcp_tool_not_allowed` باید `403` باشد) |

---

## ۱۴. جمع‌بندی

**MCP Client = لایه‌ی امن و استاندارد بین Coordinator و ERP MCP Server:**

- ✅ پروتکل MCP Streamable HTTP را پیاده می‌کند.
- ✅ allowlist سخت‌گیرانه (read/write جدا).
- ✅ argument validation (jsonschema).
- ✅ SSO token کاربر را forward می‌کند (RBAC در MCP).
- ✅ خطاها را به کدهای معنادار تبدیل می‌کند.
- ✅ Session management (per-request).
- ✅ JSON و SSE response پشتیبانی.

**MCP Client = "پل" بدون تصمیم‌گیری.** تصمیم‌ها در LLM (انتخاب ابزار) و Coordinator (approval) و MCP (RBAC) هستند.

**اگر مسئول شبکه مشکل connectivity را حل کند، MCP Client بدون تغییر کار می‌کند.**