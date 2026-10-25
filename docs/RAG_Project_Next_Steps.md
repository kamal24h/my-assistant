# پیشنهاد مراحل بعدی برای بهبود پروژه RAG

با توجه به وضعیت فعلی پروژه، پیشنهاد می‌شود به‌جای اضافه‌کردن APIهای بیشتر، پروژه مرحله‌به‌مرحله به یک **RAG production-ready** تبدیل شود.

## 1. تکمیل API ورود مستندات — اولویت خیلی بالا

- `POST /api/v1/documents/create-text`
- دریافت لیست مستندات
- `app_id + doc_name` به‌عنوان کلید منطقی
- Create / Update
- Version داخل `meta_info`
- Chunking و Embedding
- ذخیره در Qdrant
- حذف Vectorهای قبلی فقط بعد از موفقیت embedding جدید
- ثبت/به‌روزرسانی Document در PostgreSQL
- پردازش چند سند در یک درخواست
- نتیجه مستقل برای هر سند: Created / Updated / Failed / chunks_count / error

## 2. طراحی درست Pipeline مربوط به Chunking

Pipeline پیشنهادی:

```text
Raw Document
     ↓
Document Normalization
     ↓
Structure Detection
     ↓
Chunking
     ↓
Metadata Enrichment
     ↓
Embedding
     ↓
Qdrant
```

برای فارسی باید موارد زیر را مشخص کنیم:

- chunk size مناسب
- overlap مناسب
- حفظ headingها و paragraphها
- metadata هر chunk
- `chunk_index`
- `document_version`
- `document_id`

مثال:

```json
{
  "doc_id": "...",
  "doc_name": "راهنمای انبار",
  "app_id": "ERP-WMS",
  "version": "2.1",
  "chunk_index": 12,
  "language": "fa"
}
```

## 3. بهبود Metadata و Filtering در Qdrant

Retriever نباید فقط نزدیک‌ترین chunkها را برگرداند؛ باید بتواند metadata filter اعمال کند:

```text
app_id = ERP-WMS
AND department = warehouse
AND language = fa
```

Pipeline:

```text
User Query
     ↓
Metadata Filter
     ↓
Vector Search
     ↓
Top-K
```

## 4. ساخت Retrieval Pipeline حرفه‌ای‌تر

```text
Query
  ↓
Query preprocessing
  ↓
Embedding
  ↓
Qdrant Vector Search
  ↓
Top-K
  ↓
Reranking
  ↓
Context Selection
  ↓
LLM
```

پیشنهاد:

- Top-K اولیه مثلاً 10–20
- reranking
- انتخاب نهایی 4–6 chunk

## 5. ارزیابی کیفیت RAG

یک dataset کوچک بسازیم:

```text
Question
Expected Answer
Relevant Document
Relevant Chunk
```

مثلاً 50 سؤال فارسی واقعی از مستندات.

سپس بتوانیم مقایسه کنیم:

```text
Embedding Model A vs Embedding Model B
Chunk Size 500 vs Chunk Size 1000
Top-K 4 vs Top-K 10 + Reranker
```

## 6. مدیریت Jobهای سنگین

برای production بهتر است embedding برای batchهای بزرگ داخل request انجام نشود:

```text
FastAPI
   ↓
Create Ingestion Job
   ↓
Redis / Queue
   ↓
Background Worker
   ↓
Chunk
   ↓
Embedding
   ↓
Qdrant
   ↓
Update PostgreSQL
```

Redis موجود در پروژه می‌تواند در این معماری استفاده شود.

## 7. مدیریت خطا و Transaction

باید وضعیت پردازش سند مشخص باشد:

```text
Pending
Processing
Indexed
Failed
```

مثلاً در شرایطی که Qdrant موفق ولی PostgreSQL ناموفق است، وضعیت سیستم باید قابل تشخیص و بازیابی باشد.

## 8. Observability

موارد پیشنهادی:

- structured logging
- processing time
- embedding time
- Qdrant latency
- number of chunks
- failed documents
- query latency
- retrieved chunks
- LLM latency

## 9. Security

پس از تثبیت pipeline:

- API authentication
- authorization
- `app_id` isolation
- جلوگیری از دسترسی یک application به documentهای application دیگر
- sanitization
- محدودیت حجم document
- rate limiting
- audit log

خصوصاً **app_id isolation** نباید فقط به frontend واگذار شود.

## 10. سپس Agent / MCP / ERP Integration

در نهایت می‌توان وارد معماری بزرگ‌تر شد:

```text
                    ┌──────────────┐
                    │    User      │
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │ Assistant API│
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │  LangGraph   │
                    │ Coordinator  │
                    └──────┬───────┘
                           │
             ┌─────────────┼─────────────┐
             ↓             ↓             ↓
         Local RAG     Local LLM      ERP MCP
             │             │             │
             ↓             ↓             ↓
          Qdrant         Ollama      ERP APIs
```

فعلاً بهتر است وارد Agent و MCP نشویم و ابتدا RAG را محکم کنیم.

# ترتیب اجرایی پیشنهادی

| مرحله | کار | اولویت |
|---|---|---|
| 1 | Text Document API + Upsert/Version | 🔴 |
| 2 | بهبود Document/Chunk Metadata | 🔴 |
| 3 | Qdrant Metadata Filtering | 🔴 |
| 4 | بهبود Retrieval Pipeline | 🔴 |
| 5 | RAG Evaluation | 🔴 |
| 6 | Async Ingestion / Worker | 🟠 |
| 7 | Error Handling & Job Status | 🟠 |
| 8 | Logging & Observability | 🟠 |
| 9 | Security & Isolation | 🟠 |
| 10 | Reranking | 🟡 |
| 11 | Conversation Memory | 🟡 |
| 12 | LangGraph Coordinator | 🟡 |
| 13 | ERP MCP | 🟡 |
| 14 | Specialized Agents | 🟢 |

# قدم بعدی پیشنهادی

**مرحله 1 را کامل کنیم.**

فایل‌های فعلی `main.py`، `ingest_service.py` و `database.py` را مبنا قرار دهیم و نسخه تمیز:

```text
POST /api/v1/documents/create-text
```

را با قابلیت‌های زیر بسازیم:

- Batch
- Upsert
- Versioning
- Safe Qdrant replacement

بدون تغییر هیچ‌کدام از APIهای فعلی.

پس از آن مستقیماً سراغ **Metadata Filtering و طراحی صحیح schema متادیتای Qdrant** برویم؛ چون این دو، پایه کیفیت RAG هستند.
