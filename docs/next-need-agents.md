به نظرم الان زمان مناسبی است که از یک دستیار مبتنی بر چند مسیر پردازشی (RAG، LLM، MCP و OpenAI) به یک دستیار هوشمند چندعاملی (Multi-Agent ERP Assistant) حرکت کنی.

اما یک نکته معماری مهم وجود دارد: برای ERP با جامعه کاربری بالقوه حدود ۲۵ هزار نفر، پیشنهاد نمی‌کنم تعداد Agentها را صرفاً برای چندعاملی شدن زیاد کنیم. هر Agent باید مسئولیت مشخص، ورودی و خروجی کنترل‌شده و ابزارهای محدود داشته باشد.

من ارزیابی را بر اساس معماری و آخرین وضعیت پیاده‌سازی‌ای که از پروژه `AI-Coordinator-ERP-System` داریم انجام می‌دهم؛ یعنی:

- .NET Assistant API
- Python FastAPI Coordinator
- LangGraph به‌عنوان Orchestrator
- LangChain برای اتصال به مدل‌ها و ابزارها
- Local RAG و Local LLM
- OpenAI برای پردازش‌های پیچیده
- ERP MCP برای تعامل با ERP
- Redis برای State و مدیریت مکالمات
- Guardrails و Approval برای عملیات حساس

یک تمایز مهم: همه این اجزا Agent نیستند. برای مثال RAG یک قابلیت بازیابی دانش است، MCP یک لایه دسترسی به ابزارهاست و Router یک جزء تصمیم‌گیر در Workflow است.

## ۱. ارزیابی Agentهای فعلی

در نسخه‌ای که آخرین بار بررسی کردیم، Workflow مرکزی وجود دارد، اما هنوز همه مسئولیت‌ها به Agentهای مستقل و تخصصی تبدیل نشده‌اند.

بنابراین بهتر است وضعیت را به این صورت ببینیم:

| مؤلفه                      | وضعیت                     | ماهیت               |
| -------------------------- | ------------------------- | ------------------- |
| Coordinator / Orchestrator | پیاده‌سازی شده            | مدیریت جریان        |
| Router                     | پیاده‌سازی شده            | انتخاب مسیر         |
| Local RAG                  | پیاده‌سازی شده            | بازیابی دانش        |
| Local LLM                  | پیاده‌سازی شده            | تولید پاسخ          |
| OpenAI                     | در نسخه Phase 7 اضافه شده | استدلال پیچیده      |
| ERP MCP Client             | در نسخه Phase 7 اضافه شده | دسترسی به ابزارها   |
| Guardrails                 | اضافه شده                 | کنترل ورودی و خروجی |
| Approval                   | اضافه شده                 | تأیید عملیات حساس   |
| Clarification              | بخشی از جریان موجود       | رفع ابهام           |

این جدول وضعیت معماری و اجزای پیاده‌سازی را نشان می‌دهد، نه اینکه همه این موارد Agent مستقل LangChain باشند.

نتیجه: در حال حاضر هسته اصلی یک سیستم Orchestrated Assistant را داری، نه هنوز یک مجموعه کامل از Domain Agentهای مستقل.

### تفکیک دقیق اجزای فعلی در کد

در `workflow.py` گراف به این شکل تعریف شده است:

```
graph.add_node("input_guardrail", input_guardrail_node)graph.add_node("blocked", blocked_node)graph.add_node("route", route_node)graph.add_node("local_llm", local_llm_node)graph.add_node("openai", openai_node)graph.add_node("local_rag", local_rag_node)graph.add_node("local_mcp", local_mcp_node)graph.add_node("erp_write", erp_write_node)
```

بنابراین پنج مسیر اصلی اجرایی داری:

## ساختار فعلی Workflow

Input Guardrails

بررسی ورودی و جلوگیری از سوءاستفاده

Router / Coordinator

انتخاب مسیر پردازش

Local RAG

دانش مستندات

Local LLM

پرسش عمومی

ERP MCP

اطلاعات زنده ERP

OpenAI

استدلال پیچیده

ERP Write / Approval

آماده‌سازی عملیات و تأیید قبل از اجرا

Response / Persistence

بازگشت پاسخ و ذخیره مکالمه

نکته مهم این است که `local_llm` و `openai` فعلاً بیشتر زنجیره‌های تولید پاسخ هستند، نه Agentهای مستقل با چرخه تصمیم‌گیری و فراخوانی ابزار.

همچنین `local_mcp` یک مسیر انتخاب ابزار و اجرای آن دارد، اما هنوز یک ERP Domain Agent با چرخه مستقل تفکر، اجرای چند ابزار و ارزیابی نتیجه نیست.

این تفاوت از نظر طراحی مهم است. در مستندات فعلی LangChain، Agent به‌طور معمول مدل، ابزارها و یک چرخه تکرارشونده تصمیم‌گیری و اجرای ابزار دارد؛ درحالی‌که LangGraph امکان ترکیب این Agentها با Workflowهای قطعی را فراهم می‌کند.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://langchain-ai.github.io\&sz=32)

Docs by LangChain+2



## ۲. چه Agentهایی پیشنهاد می‌کنم اضافه کنی؟

من هشت قابلیت را بررسی می‌کنم، اما همه آن‌ها نباید به شکل Agent مستقل پیاده‌سازی شوند.

[Demystifying RAG Architecture for Enterprise Data: A Technical Blueprint - DEV Community](https://images.openai.com/static-rsc-4/dyesJjq9OPMyE4r5ynyGlXXsV5so8b0NK6qN_6xHHIfkdkgaZ610V9t_PugDTnMFDF6ZjYgb16ghENGuLSII4gC2_JHTtkxlyIs6-2noDKixrSQ_w_GwIM2b8DkRd6YRpiSstTb2rhTv5lYEgs_JIFxumxCwKjhsnLjpQRtKJp4?purpose=inline)

۱. Document Intelligence Agent

اولویت بسیار بالا

عامل تخصصی اسناد و دانش سازمانی

مسئول فهم سؤال، تشخیص نوع مستند موردنیاز، بازنویسی Query، جست‌وجوی چندمرحله‌ای، بررسی منابع و تولید پاسخ مستند.

قابلیت‌ها:

- Query Rewriting
- Hybrid Retrieval
- Multi-query Search
- Reranking
- Evidence Extraction
- Citation Generation

ارزش: افزایش دقت پاسخ‌های مستنداتی و کاهش پاسخ‌های بدون پشتوانه.

[ASK Technology - IT Solutions & Services](https://images.openai.com/static-rsc-4/cNuY-Zg8la0UPqF8_5hty8rXKY8DuF2nD1px5vOQtwLG1g5R5RXdxGA8AvKRQH8lWVvUGQChVTZ-Fygr9zRmM-e0s3ZRvU9z4yHbmmZevLKYzn1n9TqMH3mggN5kZWkTeM8ICgy9RVG00EUKoGuv81_q8CzdO0pCJO9Z0mpPRps?purpose=inline)

۲. ERP Data Agent

اولویت بسیار بالا

عامل تخصصی اطلاعات عملیاتی ERP

نسخه تکامل‌یافته مسیر `local_mcp`.

قابلیت‌ها:

- انتخاب ابزار MCP متناسب با سؤال
- تشخیص شناسه‌ها و پارامترهای موردنیاز
- اجرای چند Query وابسته
- مقایسه اطلاعات دریافتی
- بررسی کامل بودن نتایج
- تولید پاسخ همراه با منبع و زمان دریافت داده

ارزش: پاسخ‌گویی به سؤالات پیچیده مانند وضعیت سفارش، موجودی و سوابق مشتری با چند فراخوانی ابزار.

[AI Agents for Automation: The Complete Guide | by Kanerika Inc | Medium](https://images.openai.com/static-rsc-4/k8FfGcbeK2DM7eoTgkaR5jFshPNeJxgDXWAOYE5ujzf3xVsRBUadijaBWtMRfotmohtOJuDYWO71IZq8irv74AHo0Xrq5KlOjHepDRqQ46vrbP73eouCY0H_uPlQN12P4VNhnNkW6iBprWpiqjLTJyeAz6JBMMVmR4AUef6hDjs?purpose=inline)

۳. ERP Action Agent

اولویت بسیار بالا

عامل اجرای عملیات ERP

تکامل مسیر `erp_write`.

قابلیت‌ها:

- فهم درخواست عملیاتی
- استخراج اطلاعات موردنیاز فرم
- تشخیص فیلدهای ناقص
- اعتبارسنجی ورودی‌ها
- ساخت برنامه اجرای عملیات
- درخواست تأیید کاربر
- اجرای ابزار مجاز MCP
- بررسی نتیجه اجرای عملیات

ارزش: تبدیل دستیار از ابزار پاسخ‌گویی به دستیار انجام کارهای سازمانی.

نکته امنیتی: این Agent نباید بتواند Approval را دور بزند یا خودش مجوز اجرای عملیات را صادر کند.

[Flat illustration AI assistant analyzing business dashboard businessman reviews rising chart analytics intelligence data analysis performance insight decision making](https://images.openai.com/static-rsc-4/YzoE_5N65xX_tlgegXXAxos2kh_01dKHT-UGETA1YTm2q1FTPNnoPRzWOMwppLYEWvPCaDC5zprSW4Gc0Z_USGBUgp-Y-EjsKw6iYS67aIWA0UgY3QfaogT9iu3Nusqs8P0NCUG8legyKIO7D9uxoduR78fyFCVamK67kkSZ9D1VB9F8ptK34_reUqjMT2e8?purpose=inline)

۴. Business Analytics Agent

اولویت بالا

عامل تحلیل اطلاعات سازمانی

برای سؤالاتی فراتر از یک Query ساده:

- مقایسه فروش ماهانه
- تحلیل روند موجودی
- بررسی تأخیر سفارش‌ها
- تحلیل عملکرد تولید
- مقایسه دوره‌های زمانی
- تهیه گزارش مدیریتی

این Agent از ابزارهای خواندنی MCP استفاده می‌کند و نباید دسترسی مستقیم به دیتابیس ERP داشته باشد.

ارزش: تبدیل داده‌های خام ERP به تحلیل قابل استفاده برای مدیران.

[Exploring AI Coworking with Codex and Claude | Tim O'Neill posted on the topic | LinkedIn](https://images.openai.com/static-rsc-4/DqTaxaYYLvE4PokxKNiMVTRSWfSBQsZc6BfTmqwiilzE58BGgQTHnO2hlRaDMoret6YAbS6fa64zgeidIvsRZDjvGiZiYgS1PSKBCK6_2ic-skyGxaFgawfwDhp4gHYfqfhuud_ebjKg_eMTinT0i1tAIaZwZd_vQB3639fYcJ8?purpose=inline)

۵. Planning & Task Agent

اولویت بالا

عامل برنامه‌ریزی و تجزیه وظایف

برای درخواست‌های چندمرحله‌ای:

مثلاً کاربر می‌گوید:

«وضعیت سفارش‌های باز را بررسی کن، سفارش‌های تأخیردار را مشخص کن و گزارشی از آن‌ها بده.»

این Agent:

- درخواست را به چند وظیفه تقسیم می‌کند.
- وابستگی بین وظایف را مشخص می‌کند.
- Agentهای لازم را فراخوانی می‌کند.
- نتایج را جمع‌آوری می‌کند.
- گزارش نهایی را می‌سازد.

ارزش: مدیریت درخواست‌هایی که به چند منبع اطلاعاتی نیاز دارند.

[AI citation checker with source verification, reference validation, citation analysis, document review](https://images.openai.com/static-rsc-4/TnkNXVScirMID1miPxtxUQEjxGMoKxLpbyEss0nM3hIu6o8G_NlYRqKeFM1PttsvAKmKgJ4w1RXiK9Rousb58UkyyOSBEsUKGwM9-dyzidnbNR1Rw28wzI1M_ZMcMBsUfjPGh4ZkDRfaMJnseh0uSuG5RtS43GqH_vSWDOlNxqDFAbXgivOkEcGZieLTbMEE?purpose=inline)

۶. Answer Verification Agent

اولویت بالا

عامل ارزیابی و کنترل کیفیت پاسخ

قبل از ارسال پاسخ:

- ادعاهای پاسخ را با منابع تطبیق می‌دهد.
- اعداد را با خروجی ERP مقایسه می‌کند.
- پاسخ‌های بدون شواهد را شناسایی می‌کند.
- تناقض بین منابع را تشخیص می‌دهد.
- در صورت نیاز، درخواست تولید مجدد می‌دهد.

ارزش: کاهش توهم مدل و افزایش اعتمادپذیری.

این مورد برای مسیر RAG اهمیت ویژه‌ای دارد.

[Memory Systems for Conversational RAG | Elegant Software Solutions](https://images.openai.com/static-rsc-4/iQEDWn8EOxkt03rzY9nN8KI38tSucWj__kSG-e3GOuYPLOye-3up2CTCW6wQXI40u4rVZTco8aarOirQp-gW6O20h5PofuCoVpXxp_jzh3oQUilUSsDr7lI1cm888clwWXe9_V4rtlvCXspvPKq3YjJ04bdcwZwPyukmFfxNFhI?purpose=inline)

۷. Context & Memory Agent

اولویت متوسط

عامل مدیریت زمینه و مکالمات

- فهم ارجاعات به پیام‌های قبلی
- تشخیص موضوع فعال مکالمه
- نگهداری شناسه‌های سفارش و مشتری در زمینه مکالمه
- خلاصه‌سازی مکالمات طولانی
- مدیریت Clarificationهای چندمرحله‌ای

ارزش: طبیعی‌تر شدن مکالمه و کاهش نیاز به تکرار اطلاعات.

البته ذخیره‌سازی State و Memory باید عمدتاً با سازوکارهای قطعی انجام شود، نه تصمیم آزاد مدل.

[What is a Data Mesh: Principles and Architecture | Stardog](https://images.openai.com/static-rsc-4/z5v96T7eStzlQdLsq38tILdAVBirwddilKF_Dpr34QkNWPveoAq0AkjOAVlMMeQKjJvvi1fHlr-TleeE9M7fSAEODkvPzvOt-cfy4GsvHJxDKGDu7hRtVqtNKnmLiRYhBb-jtFucjxRAqsX7-DFU6nzP7aLstIx8eoTAfHrP5BI?purpose=inline)

۸. Terminology & Semantic Agent

اولویت متوسط

عامل مدیریت اصطلاحات و مفاهیم ERP

با توجه به طرح واژه‌نامه‌ای که برای پروژه داشتیم:

- تشخیص اصطلاحات اختصاصی ERP
- تبدیل مترادف‌ها به مفهوم استاندارد
- تشخیص نام ماژول، فرم و فیلد
- رفع ابهام اصطلاحات
- تزریق تعریف اصطلاحات به Context مدل

ارزش: فهم بهتر زبان واقعی کاربران و اصطلاحات تخصصی نرم‌افزار.

پیشنهاد من این است که Resolver و Normalizer آن ابتدا یک سرویس قطعی باشند و فقط در موارد مبهم از LLM کمک بگیرند.

## ۳. آیا باید Agentهای تخصصی هر واحد سازمانی را هم داشته باشیم؟

بله، ولی پیشنهاد می‌کنم آن‌ها را در مرحله بعد اضافه کنی.

برای ERP تو، این مجموعه می‌تواند بسیار ارزشمند باشد:

| Agent تخصصی       | مسئولیت                                 |
| ----------------- | --------------------------------------- |
| Inventory Agent   | انبار، موجودی، رسید و حواله             |
| Purchasing Agent  | درخواست خرید، سفارش خرید، تأمین‌کنندگان |
| Sales Agent       | مشتری، فروش، سفارش و فاکتور             |
| Production Agent  | برنامه‌ریزی تولید، سفارش ساخت، ظرفیت    |
| Finance Agent     | حسابداری، اسناد مالی، دریافت و پرداخت   |
| HR Agent          | پرسنلی، حضور و غیاب، حقوق و دستمزد      |
| Maintenance Agent | تعمیرات، نگهداری و سوابق تجهیزات        |

این‌ها باید Sub-Agentهای واقعی باشند؛ یعنی هرکدام Prompt، ابزارهای مجاز، Schema ورودی و خروجی و محدودیت دسترسی مستقل داشته باشند.

مثلاً Inventory Agent نباید به ابزارهای مالی دسترسی داشته باشد.

اما یک نکته: اگر برای هر واحد سازمانی Agent بسازی، لزوماً کیفیت بهتر نمی‌شود. اگر ابزارهای یک حوزه کم و ساده باشند، همان ERP Data Agent با انتخاب ابزار مناسب کافی است.

## ۴. معماری پیشنهادی من برای نسخه تکامل‌یافته

من معماری Supervisor + Specialized Subagents را پیشنهاد می‌کنم.

در این معماری، Coordinator مسئول مدیریت Agentها است و هر Agent فقط در محدوده تخصص خودش کار می‌کند.

## Target Multi-Agent Architecture

.NET Assistant API

Authentication · Conversation · Streaming

LangGraph Supervisor / Coordinator

Routing · Planning · State Management · Delegation

Document Agent

RAG · Reranking · Evidence

ERP Data Agent

Read-only MCP Tools

ERP Action Agent

Write · Validation · Approval

Analytics Agent

Reports · Trends · Analysis

Planning Agent

Task Decomposition

Verification Agent

Evidence · Quality Control

Context Agent

Memory · Clarification

Terminology Service

Glossary · Normalization

Shared Infrastructure

Local Qwen · OpenAI · RAG API · ERP MCP · PostgreSQL · Qdrant · Redis

نمای مفهومی؛ همه این Agentها نباید در هر درخواست اجرا شوند.

در این طراحی، OpenAI و Local LLM دیگر لزوماً مسیرهای مستقل کسب‌وکاری نیستند؛ بلکه مدل‌های قابل استفاده توسط Agentهای مختلف هستند.

مثلاً:

- Document Agent می‌تواند با Qwen اجرا شود.
- Planning Agent در صورت پیچیدگی می‌تواند از OpenAI استفاده کند.
- ERP Data Agent برای انتخاب ابزار از مدل محلی استفاده کند.
- Answer Verification Agent می‌تواند با مدل محلی اجرا شود و فقط در موارد دشوار به مدل قوی‌تر ارجاع دهد.

این تفکیک باعث می‌شود منطق کسب‌وکار به ارائه‌دهنده مدل وابسته نباشد.

الگوی Supervisor در مستندات LangChain نیز برای همین وضعیت مناسب است: Supervisor Agentهای تخصصی را به‌عنوان ابزار فراخوانی می‌کند و نتایج را تجمیع می‌کند.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub+2



## ۵. چه چیزهایی را Agent نکنیم؟

این بخش به نظرم به اندازه اضافه کردن Agent اهمیت دارد.

| قابلیت                    | پیشنهاد پیاده‌سازی           |
| ------------------------- | ---------------------------- |
| Input Guardrails          | Middleware / Node قطعی       |
| Output Guardrails         | Middleware / Node قطعی       |
| Terminology Normalization | Service                      |
| Query Embedding           | RAG Service                  |
| Vector Retrieval          | RAG Service                  |
| Reranking                 | RAG Service                  |
| Authentication            | .NET / Security Service      |
| Authorization             | Policy Service               |
| Approval                  | Human-in-the-loop Workflow   |
| Retry و Fallback          | Middleware                   |
| Conversation Persistence  | Service                      |
| Routing                   | LangGraph Node یا Supervisor |

برای مثال، من ترجیح می‌دهم بررسی مجوز کاربر برای مشاهده اطلاعات مالی را به یک Agent هوشمند نسپارم. این تصمیم باید توسط Policy قطعی گرفته شود.

LangChain نیز برای کنترل‌هایی مثل Retry، Model Fallback، محدودیت فراخوانی ابزار، Human-in-the-loop و مدیریت Context، Middlewareهای اختصاصی دارد.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://reference.langchain.com\&sz=32)

LangChain Reference+1



## ۶. اولویت پیاده‌سازی پیشنهادی

من این ترتیب را برای پروژه تو مناسب‌تر می‌دانم:

| مرحله    | قابلیت                      | اولویت |
| -------- | --------------------------- | ------ |
| Phase 8  | Document Intelligence Agent | P0     |
| Phase 9  | ERP Data Agent              | P0     |
| Phase 10 | Answer Verification Agent   | P0     |
| Phase 11 | ERP Action Agent            | P1     |
| Phase 12 | Planning Agent              | P1     |
| Phase 13 | Business Analytics Agent    | P1     |
| Phase 14 | Context & Memory Agent      | P2     |
| Phase 15 | Domain Agents               | P2     |

در این برنامه، Terminology Service را نیز باید در ابتدای Phase 8 به RAG و Coordinator متصل کنیم.

### معیار موفقیت هر فاز

فقط پیاده‌سازی Agent کافی نیست. برای هر Agent باید مجموعه تست اختصاصی داشته باشیم:

- دقت تشخیص وظیفه
- دقت انتخاب ابزار
- صحت پارامترهای ابزار
- میزان پاسخ‌های بدون شواهد
- کیفیت پاسخ نهایی
- زمان پاسخ
- تعداد فراخوانی مدل
- هزینه هر درخواست
- نرخ خطا و بازیابی از خطا

به‌خصوص برای Document Agent باید مجموعه‌ای از پرسش‌های واقعی مستندات سازمانی داشته باشیم و قبل و بعد از پیاده‌سازی، کیفیت را مقایسه کنیم.

## ۷. پیشنهاد فنی برای پیاده‌سازی در پروژه فعلی

من پیشنهاد نمی‌کنم `workflow.py` را یک‌باره بازنویسی کنیم.

بهتر است ساختار Coordinator را تدریجی به این شکل توسعه دهیم:

```
src/coordinator/app/
│
├── agents/
│   ├── document/
│   │   ├── agent.py
│   │   ├── prompts.py
│   │   └── schemas.py
│   │
│   ├── erp_data/
│   │   ├── agent.py
│   │   ├── prompts.py
│   │   └── schemas.py
│   │
│   ├── erp_action/
│   │   ├── agent.py
│   │   ├── prompts.py
│   │   └── schemas.py
│   │
│   ├── analytics/
│   ├── planning/
│   ├── verification/
│   └── context/
│
├── terminology/
│   ├── models.py
│   ├── resolver.py
│   ├── normalizer.py
│   └── context_builder.py
│
├── graphs/
│   ├── workflow.py
│   ├── state.py
│   ├── routing.py
│   └── nodes/
│
├── services/
│   ├── llm_factory.py
│   ├── rag_client.py
│   ├── mcp_client.py
│   ├── approval_store.py
│   └── clarification_store.py
│
└── core/
    ├── config.py
    ├── schemas.py
    └── guardrails.py
```

این ساختار پیشنهادی است و لازم نیست تمام پوشه‌ها از روز اول ایجاد شوند.

نکته مهم دیگر این است که Agentها بهتر است تا حد امکان Stateless باشند و State مکالمه توسط Supervisor و Checkpointer مدیریت شود. برای ادامه مکالمه، توقف در انتظار تأیید و بازیابی بعد از خطا، Persistence در LangGraph اهمیت زیادی دارد.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://langchain-ai.github.io\&sz=32)

Docs by LangChain+1



## ۸. تصمیم معماری که پیشنهاد می‌کنم

برای پروژه تو سه انتخاب داریم:

۱. ساختار چندعاملی را چگونه مدیریت کنیم؟

Supervisor + Specialized Subagents (پیشنهاد من)

یک Agent مرکزی با ابزارهای متعدد

چند Supervisor سلسله‌مراتبی برای واحدهای ERP

۲. اولین Agent تخصصی را از کجا شروع کنیم؟

Document Intelligence Agent

ERP Data Agent

Answer Verification Agent

ERP Action Agent

۳. مدل‌های زبانی چگونه استفاده شوند؟

Hybrid: Qwen محلی + OpenAI در موارد ضروری

تمام Agentها با Local LLM

استفاده گسترده از OpenAI

ثبت تصمیم و طراحی فاز بعد

جمع‌بندی نظر من: برای این پروژه، مهم‌ترین جهش کیفی از اضافه کردن تعداد زیادی Agent حاصل نمی‌شود؛ از سه قابلیت حاصل می‌شود: Document Intelligence دقیق، ERP Data Agent قابل اعتماد و Answer Verification.

بعد از آن ERP Action و Planning را اضافه می‌کنیم تا دستیار بتواند علاوه بر پاسخ‌گویی، کارهای واقعی کاربران را نیز با کنترل و تأیید مناسب انجام دهد.

من معماری Supervisor + Subagents را با حفظ کامل ساختار فعلی .NET، Coordinator، RAG و MCP توصیه می‌کنم. این مسیر هم توسعه مرحله‌ای را ممکن می‌کند و هم از بازنویسی غیرضروری پروژه جلوگیری می‌کند.