
I've reviewed the full project. Here's my summary and the observations you should know before we decide what to do next.

## What the project is

A containerized, hybrid **ERP Smart Assistant** with four application layers on a shared `assistant_network`:

| Service | Role |
|---|---|
| `assistant-api` (port 8003) | Public gateway; forwards to coordinator, forwards SSO `Authorization` |
| `coordinator` (8001) | LangGraph router + guardrails + approvals + MCP + optional OpenAI |
| `fastapi` / rag_service (8000) | Documents, conversations, messages, RAG pipeline, persistence |
| `ollama`, `qdrant`, `postgres`, `redis` | Infrastructure |

The coordinator graph is: `input_guardrail → (blocked | route) → {local_llm, local_rag, local_mcp, erp_write, openai} → END`, with human approval for write operations backed by Redis.

## Issues I noticed

**Blocking / correctness bugs**

1. **`assistant_turns.py` validation regex rejects most callers.** `selectedPath` is constrained to `^(local_llm|local_mcp)$`, but the coordinator persists `"local_llm_fallback"`, `"erp_write_pending"`, `"erp_write_executed"`, `"guardrails_blocked"`, and `"local_rag"`/`"openai"` never reach it but the others do. Every OpenAI fallback, ERP write, and guardrail-blocked turn will **422 and raise `RagApiError`**, turning successful LLM answers into 502s. This is the most serious bug.

2. **Conversations router has no auth** (`#dependencies=[Depends(require_api_key)]` commented out). Anyone on the network can read/create conversations and list them by `tenantId`/`userId` query params. Combined with the gateway not forwarding API keys to RAG, this is inconsistent.

3. **`main.py` (coordinator) is a stub.** It only re-exports `app` from `workflow.py`. So the module-level settings, health endpoints, and routes all live in `workflow.py` — importing `app` works, but `uvicorn app.main:app` vs `main:app` matters; the Dockerfile must target the right module. Worth confirming `CMD` matches.

4. **`guardrails.py` `_ENTERPRISE_PATTERNS` + `classify_path` interaction.** `force_local=True` is computed but `classify_path` only uses it to demote `openai`. The keyword fallback already returns `local_llm` for most enterprise wording. That's fine, but `assess_input` flags `pii_detected` for any 10–16 digit number, which will catch order numbers/amounts and force local — likely intended, but worth confirming.

5. **`config.py` hardcodes credentials as defaults**: `postgres_password = "blahblahblah"`. Should be `Optional[str] = None` with fail-fast, or only in `.env`.

6. **`docker-compose.yml`:**
   - `postgres` port `5432:5432` exposed publicly (should be internal-only).
   - `qdrant` 6333/6334 exposed publicly.
   - `redis` 6379 exposed publicly.
   - `fastapi` binds `127.0.0.1:8000` (good) but `coordinator` and `assistant-api` too (good). Infra should match.
   - `ollama` `gpus: all` + `NVIDIA_VISIBLE_DEVICES` is fine but requires nvidia runtime.

7. **`assistant_turns.py` has no `conversation_id`/`userId` consistency check against the record** in the approval history path — it builds a fresh `ChatRequest` with `requestId`/`conversationId` from the stored record, which is fine, but `persist_non_rag_turn` doesn't validate that `req.conversationId` belongs to `req.tenantId`/`req.userId` (the RAG side does via `get_conversation`).

8. **`_ensure_conversation`** POSTs to `/api/v1/conversations` **without** `X-API-Key` even though `conversations.py` currently has no auth — if you re-enable auth there, this breaks. Also no `userId` validation error path.

9. **`select_erp_tool`** parses model JSON with `find`/`rfind` on braces — fragile if the model emits multiple JSON objects or a JSON array first. It does validate against the allowlist afterward (good), and `validate_tool_arguments` uses jsonschema (good).

10. **`local_mcp_node`** re-checks `selected["name"] not in {tool.get("name") for tool in tools}` but `select_erp_tool` already validates. Harmless redundancy.

11. **`erp_write_node`** calls `validate_tool_arguments` but `select_erp_tool` doesn't; the approval path later re-validates in `call_write_tool`. Fine, but note arguments are validated twice.

12. **`sanitization.py`** phone regex `(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)` will mangle dates/times in Persian text before sending to OpenAI. Acceptable given "defense in depth," but it can distort a legitimate general question.

13. **`reranker_service.py`** uses `langchain_classic` (a separate/odd package) and `HuggingFaceCrossEncoder`. The `requirements.txt` lists `langchain_classic` — verify that package exists on PyPI under that name; the common one is `langchain-classic` (hyphenated, newer) or `langchain` itself. This may break `pip install`.

14. **`config.py` (rag_service)** default `qdrant_api_key` is `None` but compose sets `QDRANT__SERVICE__API_KEY=${QDRANT_API_KEY}`. If `QDRANT_API_KEY` is empty, Qdrant may run without auth — acceptable for private net, but note the client passes `None`.

15. **`ingest_service.py`**: duplicate `chunk_ids` computation (first builds then overwrites). Dead code; harmless.

16. **`create-text` (replace) vs `create-text2` (upsert)** — the replace endpoint deletes all `Document` rows for the app then re-adds; if `db.commit()` succeeds but the per-old-doc Qdrant cleanup loop fails, stale vectors remain with `is_current=True` potentially, since new docs are added with `is_current=True` and old ones deleted from Postgres but the old Qdrant points had `is_current` from prior ingest. Since retrieval filters on `is_current=True` + `app_id`, stale old vectors would be returned. **This is a real correctness risk** in `create-text`.

17. **`output_guardrails.py`** is a duplicated subset of coordinator `guardrails.py` (documented as intentional, but drift-prone).

18. **`approval_store.save`** for terminal states sets TTL 7 days — fine. But `create` uses `nx=True`; a retried `approval_id` collision raises. Fine.

19. **`openai_service.py`** creates a new `AsyncOpenAI` client per call (acceptable) but `_openai_semaphore`/`_request_times` are module-global — per-process only, as documented.

20. **`messages.py`** does not call `guard_output` on the RAG answer until after generation (it does). Good. But `assistant_turns` persistence path also applies `guard_output` in coordinator before persist — double-guarding is fine.

21. **`workflow.py` `/api/v1/assistant/chat`** — the gateway already validates `X-API-Key`; coordinator's `chat` does **not** re-validate `ASSISTANT_API_KEY`. That's by design (internal), but the coordinator port is exposed on `127.0.0.1:8001` — fine for same-host.

22. **`erp_write_node`** builds `ChatRequest(requestId=..., conversationId=..., appId=..., tenantId=..., userId=..., prompt=...)` without `messageId`/`metadata` — `extra="forbid"` so it's fine, but omitting `messageId` means the persisted turn gets a new message id. OK.

23. **`compose` `fastapi` volume `./docs:/app/docs`** — if the image expects different path, fine; just confirm.

24. **Health endpoints** (`/health/llm`, `/health/rag`, `/health/mcp`) are unauthenticated and reveal model names/URLs — acceptable for internal, but note.

25. **`conversation.py` schema** `ConversationDetailOut.messages` default `[]` mutable — minor Pydantic anti-pattern (Pydantic v2 handles it, but prefer `Field(default_factory=list)`).

## What I'd suggest prioritizing

If you want my recommendation, in order:

1. **Fix `assistant_turns.py` `selectedPath` regex** — this is actively breaking real requests. Change to a permissive `str` or add all coordinator paths.
2. **Decide auth policy for `conversations.py`** and align `_ensure_conversation` to send `X-API-Key`.
3. **Close infra ports** (postgres/redis/qdrant) to loopback or internal-only.
4. **Fix `create-text` stale-vector risk** (mark old vectors `is_current=False` before delete, or delete Qdrant first).
5. **Remove hardcoded DB password default.**
6. **Verify `langchain_classic` dependency name.**

Tell me which of these you want to tackle, and whether you want me to (a) just propose patches, (b) produce full replacement files, or (c) walk through one issue at a time. Also confirm whether the coordinator Dockerfile `CMD` points to `main:app` or `app.graphs.workflow:app`, since `main.py` is only a re-export shim.