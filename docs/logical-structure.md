ERP-Assistant/
│
├── rag-service/                         # سرویس فعلی RAG
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── conversations.py         # API مدیریت مکالمات
│   │       ├── documents.py             # API مدیریت مستندات
│   │       └── messages.py              # API پیام‌ها و پاسخ RAG
│   │
│   ├── schemas/
│   │   ├── conversation.py              # مدل داده مکالمه
│   │   ├── document.py                  # مدل داده مستند
│   │   └── message.py                   # مدل داده پیام
│   │
│   ├── services/
│   │   ├── conversation_service.py      # منطق مکالمات
│   │   ├── message_service.py           # منطق پیام‌ها
│   │   └── rag_service.py               # بازیابی و تولید پاسخ
│   │
│   ├── docs/
│   │   ├── Architecture.md
│   │   ├── NextSteps.md
│   │   ├── RAG_Project_Next_Steps.md
│   │   ├── sampleRequestForCreateText.json
│   │   └── cfg/
│   │       └── rag_assistant_nginx.conf
│   │
│   ├── .env                             # تنظیمات و اسرار محلی
│   ├── .gitignore
│   ├── config.py
│   ├── database.py                      # PostgreSQL
│   ├── redis_client.py                  # Redis
│   ├── ingest_service.py                # ورود و پردازش مستندات
│   ├── message_broker.py
│   ├── main.py                          # ورودی FastAPI
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── requirements.txt
│
├── coordinator/                         # دستیار مرکزی هوشمند
│   │
│   ├── coordinator/
│   │   ├── __init__.py
│   │   ├── main.py                      # FastAPI + گراف LangGraph
│   │   ├── config.py                    # تنظیمات و آدرس سرویس‌ها
│   │   └── schemas.py                   # قرارداد ورودی و خروجی API
│   │
│   ├── tests/
│   │   └── test_coordinator.py          # تست‌های Coordinator
│   │
│   ├── Dockerfile                       # ساخت ایمیج Coordinator
│   ├── docker-compose.coordinator.yml   # اتصال به شبکه RAG
│   ├── requirements-coordinator.txt     # وابستگی‌های Coordinator
│   └── README.fa.md                     # راهنمای اجرا
│
└── README.md                            # راهنمای کلی پروژه (پیشنهادی)


Docker Network: assistant_network
│
├── Coordinator       :8001
├── RAG FastAPI       :8000
├── Ollama            :11434
├── Qdrant            :6333
├── PostgreSQL        :5432
└── Redis

