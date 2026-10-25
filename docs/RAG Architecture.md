Local RAG/
├── main.py
├── database.py
├── redis_client.py
├── ingest_service.py
│
├── api/
│   └── v1/
│       ├── conversations.py
│       ├── messages.py
│       └── documents.py          # نسخه تمیز قبلی
│
├── schemas/
│   ├── conversation.py
│   ├── message.py
│   └── document.py
│
└── services/
    ├── conversation_service.py
    ├── message_service.py
    ├── assistant_service.py
    └── document_service.py