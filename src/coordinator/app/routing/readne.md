نحوه استفاده در Coordinator
بعد از ساخت Local LLM:
from app.routing.intent_classifier import IntentClassifierintent_classifier = IntentClassifier(    llm=local_llm,    confidence_threshold=0.65,    clarification_threshold=0.45,)



و هنگام پردازش درخواست:
decision = await intent_classifier.classify(    question=user_message,    conversation_context=conversation_context,)logger.info(    "Intent=%s | Routes=%s | Confidence=%.2f",    decision.intent,    decision.routes,    decision.confidence,)



دو نکته مهم برای نسخه فعلی پروژه
1. Fallback را معادل تشخیص مطمئن در نظر نگیر. اگر مدل در دسترس نباشد، keyword_fallback فقط یک تخمین محافظه‌کارانه است. بهتر است در لاگ‌ها مشخص باشد تصمیم از مدل آمده یا از Fallback؛ در نسخه فعلی این موضوع هنوز به IntentDecision اضافه نشده است.
2. Confidence مدل زبانی کالیبره نیست. مقدار 0.85 الزاماً به معنی ۸۵ درصد صحت نیست. آستانه‌های 0.65 و 0.45 را بعد از آزمایش روی پرسش‌های واقعی کاربران تنظیم کن. همچنین تأیید و مجوز عملیات ERP مستقل از این امتیاز باقی می‌ماند.
پیشنهاد من: قبل از اتصال این Router به کل گراف، ابتدا آن را با حداقل ۵۰ پرسش واقعی فارسی آزمایش کن؛ به‌ویژه پرسش‌هایی که نام یکسانی از موجودیت ERP دارند، اما هدفشان متفاوت است.


توصیه مهم: این Prompt را با Qwen محلی ابتدا روی مجموعه‌ای از پرسش‌های واقعی فارسی ERP آزمایش کن. به‌خصوص سه دسته زیر باید به‌درستی از هم تفکیک شوند:
پرسش	مسیر مورد انتظار
فاکتور فروش چگونه صادر می‌شود؟	local_rag
فاکتور فروش شماره ۱۲۳ چه وضعیتی دارد؟	local_mcp
فاکتور فروش شماره ۱۲۳ را ابطال کن	erp_write

این سه‌گانه معیار خوبی برای سنجش کیفیت اولیه Router است.

نکته معماری: متد normalized_routes() عمداً اجازه نمی‌دهد مدل زبانی مثلاً برای DOCUMENT_QUERY مسیر local_mcp را انتخاب کند. البته این کنترل فقط محدودسازی Route است؛ مجوز دسترسی، تأیید عملیات و کنترل امنیتی باید همچنان در لایه‌های مستقل خودشان انجام شوند.

محتوای کامل فایل `src/coordinator/app/routing/keyword_fallback.py`:

```
from __future__ import annotations    r"دستورالعمل",    r"آیین\s*نامه",    r"طبق\s+مستند",    r"در\s+مستند",    r"چه\s+کسی\s+مجاز",    r"قوانین\s+(?:شرکت|سازمان)",    r"فرآیند|فرایند",)def keyword_fallback(question: str) -> IntentDecision:    """    Conservative fallback for when the semantic model is unavailable.    Priority:    1. Empty input    2. Small talk    3. Document/procedure questions    4. Explicit ERP write actions    5. Actual ERP data queries    6. Default to Local RAG    """    text = _normalize_fa(question)    if not text:        return IntentDecision(            intent="AMBIGUOUS",            routes=["clarification"],            confidence=0.0,            reasoning="درخواست خالی است.",            needs_clarification=True,            clarification_question="لطفاً درخواست خود را توضیح دهید.",        )    # Small talk → Local LLM    if _is_small_talk(text):        return IntentDecision(            intent="SMALL_TALK",            routes=["local_llm"],            confidence=0.99,            reasoning="پیام از نوع گفت‌وگوی کوتاه است.",        )    # Procedural wording takes precedence over ERP entity words.    # Example: "فاکتور فروش چگونه صادر می‌شود؟" → Local RAG    if any(re.search(pattern, text) for pattern in _DOC_PATTERNS):        return IntentDecision(            intent="DOCUMENT_QUERY",            routes=["local_rag"],            confidence=0.88,            reasoning="پرسش درباره روش، مراحل یا دستورالعمل است.",        )    # Explicit ERP write request → ERP Write    if any(re.search(pattern, text) for pattern in _WRITE_PATTERNS):        return IntentDecision(            intent="ERP_ACTION",            routes=["erp_write"],            confidence=0.86,            reasoning="فعل صریح برای تغییر یا اجرای عملیات ERP وجود دارد.",        )    # Actual ERP record/status query → MCP    if any(re.search(pattern, text) for pattern in _DATA_PATTERNS):        return IntentDecision(            intent="ERP_DATA_QUERY",            routes=["local_mcp"],            confidence=0.86,            reasoning="پرسش درباره وضعیت یا مقدار یک رکورد واقعی ERP است.",        )    # Default → Local RAG
```

نکته مهم: این تابع صرفاً Fallback است و نباید جایگزین Semantic Router شود. همچنین ترتیب بررسی الگوها عمدی است: ابتدا سؤالات رویه‌ای بررسی می‌شوند تا مثلاً «چگونه فاکتور فروش را حذف کنم؟» اشتباهاً به مسیر عملیات ERP نرود. این درخواست باید از مستندات پاسخ بگیرد، نه اینکه فاکتوری را حذف کند.

پیاده‌سازی را به‌صورت یک Intent-Based Router انجام می‌دهیم؛ یعنی ابتدا هدف معنایی درخواست تشخیص داده می‌شود و بعد مسیر اجرا انتخاب می‌شود. در این طراحی، عبارت‌هایی مثل «فاکتور فروش»، «مشتری» یا «سفارش خرید» به‌تنهایی باعث ارجاع درخواست به MCP نمی‌شوند.

چهار فایل را در مسیر زیر قرار بده:

```
src/coordinator/app/
└── routing/
    ├── __init__.py
    ├── intent_schemas.py
    ├── intent_prompts.py
    ├── intent_classifier.py
    └── keyword_fallback.py
```

`__init__.py` فقط برای قابل import بودن پکیج است. چهار فایل اصلی را آماده کرده‌ام. منطق تشخیص شامل این مسیرهاست:

- `DOCUMENT_QUERY` → مستندات و Local RAG
- `ERP_DATA_QUERY` → داده‌های جاری یا سوابق ERP و MCP
- `ERP_ACTION` → عملیات تغییردهنده اطلاعات و مسیر تأیید
- `MIXED_QUERY` → ترکیب RAG و MCP
- `SMALL_TALK` و `GENERAL_KNOWLEDGE` → Local LLM
- `AMBIGUOUS` → درخواست شفاف‌سازی

It seems like I can’t do more advanced data analysis right now. Please try again later.

در حال حاضر نتوانستم ابزار ساخت فایل را اجرا کنم؛ بنابراین نمی‌توانم لینک دانلود ZIP معتبر ارائه بدهم. اما تغییرات لازم در `workflow.py` را می‌توانم مشخص کنم تا مسیر اتصال Router به گراف برایت روشن باشد.

## ۱. تغییرات در State

در فایل `state.py` یا محل تعریف State گراف، این فیلدها را اضافه کن:

```
from typing import Any, TypedDictclass AssistantState(TypedDict, total=False):    # سایر فیلدهای فعلی پروژه    intent: str    intent_confidence: float    intent_reasoning: str    intent_entities: dict[str, Any]    selected_routes: list[str]    needs_clarification: bool    clarification_question: str | None
```

## ۲. ساخت IntentClassifier

در جایی که مدل محلی Qwen را ایجاد می‌کنی، یک نمونه از کلاس بساز:

```
from app.routing.intent_classifier import IntentClassifierintent_classifier = IntentClassifier(    llm=local_llm,    confidence_threshold=0.65,    clarification_threshold=0.45,)
```

نکته: `local_llm` باید همان Chat Model متصل به Ollama باشد که در حال حاضر در Coordinator استفاده می‌کنی. اگر نسخه یا تنظیمات ChatOllama از `with_structured_output` پشتیبانی نکند، کد به Keyword Fallback برمی‌گردد؛ اما بهتر است این قابلیت را با نسخه نصب‌شده آزمایش کنی.

## ۳. جایگزینی Node فعلی route

در `workflow.py`، به‌جای منطق فعلی انتخاب مسیر بر اساس Keyword، از این Node استفاده کن:

```
async def intent_classifier_node(state: AssistantState) -> dict:    question = state.get("question", "")    decision = await intent_classifier.classify(        question=question,        conversation_context=state.get("conversation_context", ""),    )    return {        "intent": decision.intent,        "intent_confidence": decision.confidence,        "intent_reasoning": decision.reasoning,        "intent_entities": decision.entities,        "selected_routes": decision.normalized_routes(),        "needs_clarification": decision.needs_clarification,        "clarification_question": decision.clarification_question,    }
```

اگر نام فیلد سؤال در State فعلی تو `question` نیست، همان نام موجود را جایگزین کن.

## ۴. تغییر مسیرهای گراف

تابع انتخاب مسیر را به این شکل تغییر بده:

```
def route_by_intent(state: AssistantState) -> str:    routes = state.get("selected_routes", [])    if state.get("needs_clarification"):        return "clarification"    if not routes:        return "local_rag"    if len(routes) > 1:        return "planning"    return routes[0]
```

سپس در گراف:

```
workflow.add_node("intent_classifier", intent_classifier_node)workflow.add_conditional_edges(    "intent_classifier",    route_by_intent,    {        "local_llm": "local_llm",        "local_rag": "local_rag",        "local_mcp": "local_mcp",        "erp_write": "erp_write",        "clarification": "clarification",        "planning": "planning",    },)
```

و اتصال Nodeها را به شکل زیر تغییر بده:

```
workflow.add_edge("input_guardrail", "intent_classifier")
```

یعنی مسیر قبلی:

```
input_guardrail → route → ...
```

به مسیر جدید تبدیل شود:

```
input_guardrail
       |
       v
intent_classifier
       |
       v
   route_by_intent
       |
       +------ local_llm
       |
       +------ local_rag
       |
       +------ local_mcp
       |
       +------ erp_write
       |
       +------ clarification
       |
       +------ planning
```

## ۵. یک نکته مهم درباره MIXED_QUERY

در این نسخه، اگر Router دو مسیر `local_rag` و `local_mcp` تشخیص دهد، آن را به `planning` می‌فرستیم. این Node باید هر دو مسیر را اجرا کند و نتیجه را برای پاسخ نهایی ترکیب کند.

صرفاً اجرای یکی از آن دو کافی نیست؛ مثلاً برای درخواست:

«سفارش‌های خرید تأخیردار را پیدا کن و طبق دستورالعمل شرکت بررسی کن.»

باید:

1. MCP سفارش‌های خرید تأخیردار را استخراج کند.
2. RAG دستورالعمل مرتبط را بازیابی کند.
3. نتیجه این دو در مرحله نهایی ترکیب شود.

یک نکته مهم برای اعمال دقیق تغییرات: کد بالا الگوی اتصال است، نه Patch تضمین‌شده برای نسخه فعلی پروژه؛ چون جزئیات واقعی `workflow.py` و State فعلی را در این پیام ندارم. فایل ZIP آخر پروژه را دوباره بفرست تا تغییرات را دقیقاً روی همان نسخه، با حفظ Nodeها، نام فیلدها، مسیرهای فعلی و منطق Guardrail و Approval اعمال کنم.


مشکل را دقیقاً درست تشخیص داده‌ای. مسئله اصلی تابع فعلی این است که وجود یک کلمه یا عبارت را با قصد کاربر (User Intent) یکسان فرض می‌کند.

در ERP این رویکرد به‌سرعت به مشکل می‌خورد؛ چون یک اصطلاح مانند «فاکتور فروش» می‌تواند در چند نوع سؤال با معنای کاملاً متفاوت استفاده شود.

مثلاً:

| سؤال کاربر                            | مسیر صحیح                                              |
| ------------------------------------- | ------------------------------------------------------ |
| فاکتور فروش چگونه صادر می‌شود؟        | `local_rag`                                            |
| مراحل تأیید فاکتور فروش چیست؟         | `local_rag`                                            |
| چه کسی مجاز به ابطال فاکتور فروش است؟ | `local_rag`                                            |
| فاکتور فروش شماره ۱۲۳ چه وضعیتی دارد؟ | `local_mcp`                                            |
| آخرین فاکتور فروش مشتری X چیست؟       | `local_mcp`                                            |
| چطور می‌توانم فاکتور فروش ثبت کنم؟    | احتمالاً `local_rag` یا `local_mcp` با توجه به درخواست |
| یک فاکتور فروش برای مشتری X ثبت کن    | `erp_write` یا مسیر عملیاتی                            |
| تفاوت فاکتور فروش و پیش‌فاکتور چیست؟  | `local_rag`                                            |

بنابراین پیشنهاد من این است که دیگر Routing را بر اساس کلمات کلیدی انجام ندهی؛ بلکه آن را به یک Intent-Based Semantic Router تبدیل کنی.

البته لازم نیست برای این کار یک Agent پیچیده و پرهزینه بسازی. می‌توانیم با LangGraph، یک مرحله تشخیص Intent با خروجی ساختاریافته ایجاد کنیم و سپس مسیر مناسب را انتخاب کنیم.

## ۱. اول باید انواع Intent را از هم تفکیک کنیم

برای دستیار ERP تو پیشنهاد می‌کنم حداقل این Intentها را داشته باشیم:

| Intent              | مفهوم                                                  | مسیر            |
| ------------------- | ------------------------------------------------------ | --------------- |
| `SMALL_TALK`        | سلام، تشکر و مکالمات ساده                              | `local_llm`     |
| `GENERAL_KNOWLEDGE` | پرسش عمومی و غیرمرتبط با دانش داخلی ERP                | `local_llm`     |
| `DOCUMENT_QUERY`    | سؤال درباره مستندات، قوانین، فرایندها و راهنماها       | `local_rag`     |
| `ERP_DATA_QUERY`    | پرسش درباره اطلاعات واقعی و ثبت‌شده در ERP             | `local_mcp`     |
| `ERP_ACTION`        | درخواست ثبت، ویرایش، حذف یا اجرای عملیات               | `erp_write`     |
| `MIXED_QUERY`       | سؤالی که هم به مستندات و هم به داده‌های زنده نیاز دارد | چند مسیر        |
| `AMBIGUOUS`         | درخواست مبهم یا فاقد اطلاعات کافی                      | `clarification` |

نکته مهم: `MIXED_QUERY` را جدی بگیر. مثلاً:

«سفارش‌های خرید تأخیردار را پیدا کن و بر اساس دستورالعمل خرید شرکت بررسی کن که چه اقداماتی باید انجام شود.»

این سؤال هم به اطلاعات زنده ERP نیاز دارد و هم به مستندات سازمانی. انتخاب صرفاً یکی از دو مسیر اشتباه است.

همچنین `ERP_ACTION` باید از `ERP_DATA_QUERY` جدا باشد. خواندن اطلاعات فاکتور با ثبت یا ابطال آن دو سطح دسترسی و ریسک متفاوت دارند.

## ۲. معماری پیشنهادی برای Intent Detection

پیشنهاد من استفاده از یک Router سه‌مرحله‌ای است:

User Prompt

متن ورودی کاربر + Context مکالمه

Stage 1 — Rule-based Detection

تشخیص موارد قطعی مانند سلام، درخواست صریح ثبت یا شناسه مشخص رکورد

Stage 2 — Semantic Intent Classifier

Local Qwen + Structured Output

تشخیص معنای واقعی سؤال

Stage 3 — Confidence & Policy Check

بررسی اطمینان، ابهام، مجوزها و نیاز به چند مسیر

local_rag

مستندات

local_mcp

داده‌های ERP

local_llm

پرسش عمومی

erp_write

عملیات ERP

multi_route

ترکیب چند مسیر

clarification

رفع ابهام

مزیت این معماری این است که:

- کلمات کلیدی فقط برای تشخیص نشانه‌های صریح استفاده می‌شوند.
- تصمیم اصلی بر اساس معنای جمله است.
- در موارد مبهم، مدل مجبور به حدس زدن نیست.
- می‌توان چند مسیر را برای یک درخواست انتخاب کرد.

## ۳. مهم‌ترین تغییر: خروجی Router را از یک Literal ساده به یک Schema تبدیل کن

تابع فعلی:

```
def _keyword_fallback(    question: str) -> Literal["local_rag", "local_llm", "local_mcp"]:
```

برای معماری جدید کافی نیست؛ چون فقط یک مسیر را برمی‌گرداند.

پیشنهاد من:

```
from typing import Literalfrom pydantic import BaseModel, Fieldclass IntentDecision(BaseModel):    intent: Literal[        "SMALL_TALK",        "GENERAL_KNOWLEDGE",        "DOCUMENT_QUERY",        "ERP_DATA_QUERY",        "ERP_ACTION",        "MIXED_QUERY",        "AMBIGUOUS",    ]    routes: list[        Literal[            "local_rag",            "local_llm",            "local_mcp",            "erp_write",        ]    ] = Field(default_factory=list)    confidence: float = Field(        ge=0.0,        le=1.0    )    reasoning: str = Field(        description="دلیل کوتاه انتخاب Intent"    )    entities: dict = Field(        default_factory=dict    )
```

مثلاً خروجی برای سؤال:

«فرایند تأیید فاکتور فروش چگونه است؟»

به شکل مفهومی:

```
{
  "intent": "DOCUMENT_QUERY",
  "routes": ["local_rag"],
  "confidence": 0.97,
  "reasoning": "The user asks about an organizational procedure.",
  "entities": {
    "document_type": "sales_invoice"
  },
  "needs_clarification": false,
  "clarification_question": null
}
```

و برای:

«فاکتور فروش شماره ۱۲۳ در چه وضعیتی است؟»

```
{
  "intent": "ERP_DATA_QUERY",
  "routes": ["local_mcp"],
  "confidence": 0.98,
  "reasoning": "The user requests the current status of a specific ERP record.",
  "entities": {
    "document_type": "sales_invoice",
    "document_number": "123"
  },
  "needs_clarification": false,
  "clarification_question": null
}
```

دقت کن که `reasoning` صرفاً توضیح کوتاه قابل ثبت در لاگ است؛ نباید به مدل اجازه دهیم با یک توضیح طولانی و غیرقابل‌کنترل، تصمیم را جایگزین کند.

## ۴. Prompt تشخیص Intent؛ مهم‌ترین بخش پیاده‌سازی

من برای Router یک System Prompt مستقل در نظر می‌گیرم. این Prompt باید روی مفهوم سؤال تمرکز کند، نه کلمات آن.

پیشنهاد:

# ERP Assistant – Intent Classification System Prompt

You are an Intent Classification Engine for an Enterprise ERP Assistant.

Your responsibility is to identify the user's actual intent and select the appropriate processing route.

You must classify the meaning and purpose of the entire request, not individual keywords.

## Available Intents

1. SMALL_TALK\
   Greetings, thanks, conversational messages and simple social interactions.
2. GENERAL_KNOWLEDGE\
   General questions that do not require internal company information, ERP data or organizational documentation.
3. DOCUMENT_QUERY\
   Questions about company procedures, policies, workflows, instructions, manuals, business rules, product documentation and ERP usage guidelines.
4. ERP_DATA_QUERY\
   Requests for actual, current or historical records stored in ERP, including invoices, orders, customers, inventory, production records and financial transactions.
5. ERP_ACTION\
   Explicit requests to create, update, delete, submit, approve, cancel or execute an operation in ERP.
6. MIXED_QUERY\
   Requests requiring both organizational documentation and actual ERP records, or multiple specialized processing routes.
7. AMBIGUOUS\
   Requests whose intended purpose cannot be reliably determined without additional information.

## Critical Classification Rules

- A business term or ERP entity name does NOT determine the intent by itself.
- Mentioning an invoice, purchase order, customer, inventory or production document does NOT automatically mean an ERP data request.
- Questions about how a process works, how a document is created, organizational responsibilities, approval procedures and business rules must be classified as DOCUMENT_QUERY.
- Questions about the actual status, amount, history, ownership or details of a specific ERP record must be classified as ERP_DATA_QUERY.
- Requests to explain how to perform an operation must NOT be classified as ERP_ACTION.
- Only explicit requests to execute an ERP operation should be classified as ERP_ACTION.
- When both procedural knowledge and live ERP data are required, classify as MIXED_QUERY.
- Do not infer access to ERP records merely because the user mentions an ERP entity.
- Use conversation context to resolve references such as "آن فاکتور"، "همان سفارش" and "مشتری قبلی".
- Do not invent missing identifiers, entities or business information.
- When essential information is missing, use AMBIGUOUS and request clarification.
- General knowledge must not be used as a substitute for internal company documentation.

## Routing Rules

- SMALL_TALK → local_llm
- GENERAL_KNOWLEDGE → local_llm
- DOCUMENT_QUERY → local_rag
- ERP_DATA_QUERY → local_mcp
- ERP_ACTION → erp_write
- MIXED_QUERY → select all required routes in their logical execution order.
- AMBIGUOUS → no execution route until clarification is obtained.

## Output Requirements

Return only the structured output matching the supplied IntentDecision schema.

The confidence score must reflect confidence in the user's intent, not confidence in the factual answer.

Never execute tools or ERP operations during intent classification.

این Prompt را با Local Qwen اجرا کن. برای Routing معمولاً نیازی نیست OpenAI را درگیر کنیم.

## ۵. پیاده‌سازی Classifier با LangChain

ساختار پیشنهادی:

```
src/coordinator/app/
│
├── routing/
│   ├── __init__.py
│   ├── intent_classifier.py
│   ├── intent_prompts.py
│   ├── intent_schemas.py
│   └── keyword_fallback.py
```

در `intent_classifier.py`:

```
from app.routing.intent_schemas import IntentDecisionfrom app.routing.intent_prompts import INTENT_SYSTEM_PROMPTclass IntentClassifier:    def __init__(self, llm):        self.llm = llm.with_structured_output(            IntentDecision        )    async def classify(        self,        question: str,        conversation_context: str = "",    ) -> IntentDecision:        result = await self.llm.ainvoke([            {                "role": "system",                "content": INTENT_SYSTEM_PROMPT,            },            {                "role": "user",                "content": (                    f"Conversation context:\n"                    f"{conversation_context}\n\n"                    f"Current user request:\n{question}"                ),            },        ])        return result
```

این نمونه فرض می‌کند مدل انتخابی از `with_structured_output` پشتیبانی می‌کند؛ سازگاری آن را باید با نسخه و تنظیمات `ChatOllama` پروژه خودت تست کنیم.

نکته مهم: `conversation_context` باید خلاصه و محدود باشد؛ کل تاریخچه مکالمه را در هر درخواست به Classifier نده.

### مدیریت Confidence

پیشنهاد اولیه من:

| Confidence   | رفتار                                            |
| ------------ | ------------------------------------------------ |
| 0.85 تا 1    | اجرای مسیر تشخیص داده‌شده                        |
| 0.65 تا 0.84 | بررسی Rule و Context؛ در صورت نیاز Clarification |
| کمتر از 0.65 | درخواست رفع ابهام                                |

این اعداد نقطه شروع هستند و باید با مجموعه سؤالات واقعی کاربران تنظیم شوند.

یک استثنای مهم: برای `ERP_ACTION`، حتی Confidence بالا به معنی مجوز اجرا نیست. تأیید کاربر، اعتبارسنجی پارامترها و کنترل دسترسی همچنان اجباری هستند.

## ۶. آیا Keyword Fallback را حذف کنیم؟

خیر. اما نقش آن باید تغییر کند.

تابع فعلی را به‌عنوان تصمیم‌گیر اصلی استفاده نکن. آن را برای موارد قطعی و تشخیص نشانه‌های صریح نگه دار.

برای مثال:

| عبارت                                  | نتیجه قابل اتکا            |
| -------------------------------------- | -------------------------- |
| سلام، ممنون                            | `local_llm`                |
| ثبت کن، ایجاد کن، حذف کن               | نشانه احتمالی `ERP_ACTION` |
| شماره فاکتور ۱۲۳ چه وضعیتی دارد؟       | `local_mcp`                |
| مراحل ثبت فاکتور چیست؟                 | `local_rag`                |
| طبق دستورالعمل، سفارش‌های من کدام‌اند؟ | `MIXED_QUERY`              |

حتی این نشانه‌ها هم باید در کنار ساختار جمله بررسی شوند. مثلاً «چطور فاکتور را حذف کنم؟» درخواست اجرای حذف نیست؛ پرسش درباره دستورالعمل است.

قاعده طلایی: Keywordها برای تشخیص الگوهای قطعی خوب‌اند، اما برای تعیین Intent پیچیده کافی نیستند.

## ۷. تغییر در LangGraph Workflow

در معماری فعلی، به جای اینکه `route_node` مستقیماً با Keyword تصمیم بگیرد، بهتر است یک Node مستقل به نام `intent_classifier` داشته باشیم.

ساختار پیشنهادی:

```
START
  |
  v
input_guardrail
  |
  v
intent_classifier
  |
  v
policy_check
  |
  +---- SMALL_TALK --------> local_llm
  |
  +---- GENERAL_KNOWLEDGE -> local_llm
  |
  +---- DOCUMENT_QUERY ----> document_agent
  |
  +---- ERP_DATA_QUERY ----> erp_data_agent
  |
  +---- ERP_ACTION --------> erp_action_agent
  |
  +---- MIXED_QUERY -------> planning_agent
  |                             |
  |                             +--> document_agent
  |                             |
  |                             +--> erp_data_agent
  |                             |
  |                             +--> answer_synthesis
  |
  +---- AMBIGUOUS ---------> clarification
                                |
                                v
                              END
```

در این طراحی:

- `intent_classifier` فقط تشخیص می‌دهد.
- `policy_check` مجوز و محدودیت‌های دسترسی را بررسی می‌کند.
- Agent تخصصی کار را انجام می‌دهد.
- Supervisor نتیجه را جمع‌آوری می‌کند.

برای درخواست‌های Mixed، بهتر است اجرای مسیرها در یک Workflow کنترل‌شده باشد، نه اینکه یک Agent آزادانه هر تعداد ابزار خواست فراخوانی کند.

## ۸. مجموعه تستی که حتماً باید داشته باشی

من پیشنهاد می‌کنم حداقل ۵۰ سؤال واقعی و فارسی برای ارزیابی Router تهیه کنی.

چند نمونه مهم:

| سؤال                                                      | Intent مورد انتظار |
| --------------------------------------------------------- | ------------------ |
| فاکتور فروش چیست؟                                         | DOCUMENT_QUERY     |
| چطور فاکتور فروش صادر کنم؟                                | DOCUMENT_QUERY     |
| مراحل تأیید فاکتور چیست؟                                  | DOCUMENT_QUERY     |
| فاکتور ۱۲۳ تأیید شده؟                                     | ERP_DATA_QUERY     |
| مبلغ آخرین فاکتور مشتری احمدی چقدر است؟                   | ERP_DATA_QUERY     |
| فاکتور فروش را برای مشتری X ثبت کن                        | ERP_ACTION         |
| چه کسی اجازه ابطال فاکتور دارد؟                           | DOCUMENT_QUERY     |
| فاکتورهای تأییدنشده را پیدا کن                            | ERP_DATA_QUERY     |
| فاکتورهای تأییدنشده را پیدا کن و مطابق آیین‌نامه بررسی کن | MIXED_QUERY        |
| چطور سفارش خرید ثبت می‌شود؟                               | DOCUMENT_QUERY     |
| سفارش خرید من در چه وضعیتی است؟                           | ERP_DATA_QUERY     |
| سفارش خرید جدید ثبت کن                                    | ERP_ACTION         |
| موجودی کالا را چطور کنترل می‌کنیم؟                        | DOCUMENT_QUERY     |
| موجودی فعلی کالای X چقدر است؟                             | ERP_DATA_QUERY     |
| موجودی کالا را بررسی و با حداقل موجودی مجاز مقایسه کن     | MIXED_QUERY        |
| سلام، وقت بخیر                                            | SMALL_TALK         |

معیارهایی که باید اندازه بگیری:

- Intent Accuracy
- Route Accuracy
- False MCP Rate
- False RAG Rate
- Action Misclassification Rate
- Clarification Rate

به‌خصوص `False MCP Rate` برای مشکل فعلی تو مهم است؛ یعنی چند درصد سؤال‌هایی که درباره فرایند هستند اشتباهاً به MCP می‌روند.

## ۹. توصیه نهایی من برای پروژه تو

من یک تصمیم معماری مشخص پیشنهاد می‌کنم:

پیشنهاد نهایی

Hybrid Semantic Router

1. Rule-based برای موارد قطعی و ساده.
2. Local Qwen برای تشخیص معنایی Intent.
3. Pydantic Structured Output برای خروجی استاندارد.
4. Policy Engine برای کنترل مجوزها و عملیات حساس.
5. LangGraph Conditional Routing برای انتخاب مسیر.
6. Clarification برای موارد مبهم.
7. Multi-route Workflow برای درخواست‌های ترکیبی.

یک نکته دیگر که برای پروژه‌ات اهمیت زیادی دارد: چون Qwen را برای RAG فارسی هم استفاده می‌کنی، بهتر است Router را با Prompt و مجموعه تست اختصاصی ارزیابی کنی. اگر دقت آن برای تشخیص Intent کافی نبود، می‌توانیم مدل کوچک‌تر و تخصصی‌تری را برای Classification در نظر بگیریم؛ اما فعلاً نیازی به اضافه کردن مدل جدید نیست.

پیشنهاد من برای قدم بعدی: قبل از توسعه Agentهای جدید، ابتدا همین Intent Router را پیاده‌سازی کنیم. چون اگر Routing درست نباشد، حتی بهترین Agentهای تخصصی هم در درخواست اشتباه فراخوانی می‌شوند.

می‌توانم در مرحله بعد، بر اساس ساختار واقعی نسخه فعلی `my-assistant`، چهار فایل `intent_classifier.py`، `intent_prompts.py`، `intent_schemas.py` و `keyword_fallback.py` را پیاده‌سازی کنم و تغییرات لازم در `workflow.py` و State گراف را هم به‌صورت یکپارچه آماده کنم.