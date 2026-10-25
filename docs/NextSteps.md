بله. با توجه به وضعیت فعلی پروژه، من پیشنهاد می‌کنم از اینجا به بعد به‌جای اضافه‌کردن APIهای بیشتر، پروژه را مرحله‌به‌مرحله به یک **RAG production-ready** تبدیل کنیم.

ترتیب پیشنهادی من این است:

### 1. تکمیل API ورود مستندات — اولویت خیلی بالا

همین بخشی که الان روی آن کار کردیم را کامل کنیم:

* `POST /api/v1/documents/create-text`
* دریافت **لیست مستندات**
* `app_id + doc_name` به‌عنوان کلید منطقی
* Create / Update
* Version داخل `meta_info`
* Chunking
* Embedding
* ذخیره در Qdrant
* حذف Vectorهای قبلی **فقط بعد از موفقیت embedding جدید**
* ثبت/به‌روزرسانی Document در PostgreSQL
* امکان پردازش چند سند در یک درخواست
* نتیجه مستقل برای هر سند:

  * Created
  * Updated
  * Failed
  * chunks_count
  * error

این مرحله پایه‌ی بقیه سیستم است.

---

### 2. طراحی درست Pipeline مربوط به Chunking

الان `chunk_size=1000` و `overlap=200` ثابت است.

پیشنهاد می‌کنم این را به یک pipeline قابل تنظیم تبدیل کنیم:

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

برای فارسی هم باید مشخص کنیم:

* chunk size مناسب
* overlap مناسب
* حفظ headingها
* حفظ paragraphها
* metadata هر chunk
* `chunk_index`
* `document_version`
* `document_id`

مثلاً:

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

این موضوع بعداً روی کیفیت RAG خیلی تأثیر دارد.

---

### 3. بهبود Metadata و Filtering در Qdrant

این را حتی مهم‌تر از تغییر LLM می‌دانم.

Retriever نباید فقط بگوید:

> نزدیک‌ترین 4 chunk را بده.

باید بتواند مثلاً بگوید:

```text
app_id = ERP-WMS
AND department = warehouse
AND language = fa
```

یعنی:

```text
User Query
     ↓
Metadata Filter
     ↓
Vector Search
     ↓
Top-K
```

در پروژه ERP شما این موضوع بسیار مهم است، چون بعداً ممکن است هزاران یا میلیون‌ها chunk داشته باشید.

---

### 4. ساخت Retrieval Pipeline حرفه‌ای‌تر

بعد از metadata filtering:

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

در نسخه فعلی احتمالاً هنوز:

```text
Vector Search → Top 4 → LLM
```

داریم.

مرحله بعدی می‌تواند اضافه‌کردن:

* Top-K اولیه مثلاً 10–20
* reranking
* انتخاب نهایی 4–6 chunk

باشد.

---

### 5. ارزیابی کیفیت RAG

این مرحله را خیلی توصیه می‌کنم قبل از رفتن به Agentها انجام بدهیم.

یک dataset کوچک بسازیم:

```text
Question
Expected Answer
Relevant Document
Relevant Chunk
```

مثلاً 50 سؤال فارسی واقعی از مستندات.

بعد بتوانیم مقایسه کنیم:

```text
Embedding Model A
        vs
Embedding Model B

Chunk Size 500
        vs
Chunk Size 1000

Top-K 4
        vs
Top-K 10 + Reranker
```

بدون این مرحله ممکن است تغییرات معماری فقط «احساساً» بهتر به نظر برسند.

---

### 6. مدیریت Jobهای سنگین

در حال حاضر اگر یک درخواست شامل مثلاً 100 سند باشد، embedding احتمالاً داخل request انجام می‌شود.

برای production بهتر است:

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

در اینجا Redis که همین الان در requirements دارید می‌تواند استفاده شود.

برای MVP می‌توانیم ابتدا ساده پیاده کنیم و بعد به Celery/RQ یا یک worker سبک برویم.

---

### 7. مدیریت خطا و Transaction

یکی از مهم‌ترین موارد برای production.

مثلاً:

```text
Embedding موفق
     ↓
Qdrant موفق
     ↓
PostgreSQL FAILED
```

یا:

```text
Qdrant indexing نیمه‌کاره
```

باید وضعیت سند مشخص باشد:

```text
Pending
Processing
Indexed
Failed
```

و بهتر است این وضعیت در DB ذخیره شود.

---

### 8. Observability

بعد از اینکه pipeline درست شد:

* structured logging
* processing time
* embedding time
* Qdrant latency
* number of chunks
* failed documents
* query latency
* retrieved chunks
* LLM latency

اضافه کنیم.

برای پروژه‌ای که قرار است بعداً به ERP واقعی وصل شود، این بخش خیلی مهم است.

---

### 9. Security

بعد از تثبیت pipeline:

* API authentication
* authorization
* `app_id` isolation
* جلوگیری از دسترسی یک application به documentهای application دیگر
* sanitization
* محدودیت حجم document
* rate limiting
* audit log

خصوصاً **app_id isolation** را نباید فقط به frontend واگذار کنیم.

---

### 10. سپس Agent / MCP / ERP Integration

و در نهایت همان معماری بزرگ‌تری که قبلاً طراحی کردیم:

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

ولی **فعلاً وارد Agent و MCP نشویم**. ابتدا RAG را محکم کنیم.

---

## ترتیب اجرایی که من پیشنهاد می‌کنم

اگر بخواهیم واقعاً پروژه را باهم توسعه بدهیم، من این roadmap را پیشنهاد می‌کنم:

| مرحله | کار                                | اولویت |
| ----- | ---------------------------------- | ------ |
| 1     | Text Document API + Upsert/Version | 🔴     |
| 2     | بهبود Document/Chunk Metadata      | 🔴     |
| 3     | Qdrant Metadata Filtering          | 🔴     |
| 4     | بهبود Retrieval Pipeline           | 🔴     |
| 5     | RAG Evaluation                     | 🔴     |
| 6     | Async Ingestion / Worker           | 🟠     |
| 7     | Error Handling & Job Status        | 🟠     |
| 8     | Logging & Observability            | 🟠     |
| 9     | Security & Isolation               | 🟠     |
| 10    | Reranking                          | 🟡     |
| 11    | Conversation Memory                | 🟡     |
| 12    | LangGraph Coordinator              | 🟡     |
| 13    | ERP MCP                            | 🟡     |
| 14    | Specialized Agents                 | 🟢     |

### پیشنهاد من برای قدم بعدی

**همین الان مرحله 1 را کامل کنیم.**

یعنی فایل‌های فعلی `main.py`، `ingest_service.py` و `database.py` را مبنا قرار دهیم و یک نسخه تمیز از:

```text
POST /api/v1/documents/create-text
```

بسازیم که **Batch + Upsert + Versioning + Safe Qdrant replacement** را داشته باشد، بدون اینکه هیچ‌کدام از APIهای فعلی تغییر کنند.

بعد از آن مستقیماً برویم سراغ **Metadata Filtering و طراحی صحیح schema متادیتای Qdrant**؛ چون این دو، پایه‌ی کیفیت RAG شما هستند.





# **پیشنهاد قدم بعدی (به ترتیب اولویت)**
🔴 فوری: اصلاح جابه‌جایی create-text و create-text2 (باگ منطقی جدی).

🔴 فوری: اصلاح ترتیب حذف در create-text — اول اسناد جدید را بنویس، بعد قدیمی را حذف کن (یا از Qdrant staging استفاده کن).

🔴 فوری: Failed-per-doc در batch — هر سند در try/except جدا.

🟠 مهم: payload index در Qdrant برای metadata.app_id, metadata.is_current, metadata.logical_doc_id, metadata.doc_name. این ساده‌ترین و مؤثرترین بهبود performance است.

🟠 مهم: افزودن department و language به metadata chunk و فیلترشان در RAG — roadmap مرحله ۳.

🟠 مهم: Reranking — حتی یک cross-encoder سبک مثل bge-reranker-base که با Ollama یا sentence-transformers اجرا شود، کیفیت را چشمگیر بالا می‌برد (مرحله ۴/۱۰).

🟠 مهم: فعال کردن require_api_key روی روترها — یک خط تغییر در main.py.

🟡 در ادامه: Async ingestion با RabbitMQ — چون RabbitMQ و Redis از قبل دارید، این کار ساده است و request را سریع می‌کند.

🟡 در ادامه: dataset ارزیابی RAG — ۵۰ سؤال واقعی + معیار Recall@K و Faithfulness. بدون این، نمی‌فهمی تغییرات (chunk size، reranker، embedding) واقعاً بهتر کرده یا نه.




