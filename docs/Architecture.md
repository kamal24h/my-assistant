
                         ┌─────────────────────────────────────┐
                         │          Client (Web/Mobile)        │
                         └──────────────────┬──────────────────┘
                                            │
                                            │ HTTPS
                                            ▼
                         ┌─────────────────────────────────────┐
                         │        Assistant API (8003)         │
                         │  ─ Session / Conversation Mgmt      │
                         │  ─ Data Transformation (future)     │
                         │  ─ Document Management (forward)    │
                         └──┬─────────────────────────────┬────┘
                            │                             │
                   chat/stream/approvals              documents only
                            │                             │
                            ▼                             │
             ┌──────────────────────────────┐             │
             │    Coordinator (8001)        │             │
             │  ─ Orchestration             │             │
             │  ─ Routing / Tool Selection  │             │
             │  ─ Clarification / Approval  │             │
             │  ─ Conversation proxy        │             │
             └──┬────────┬────────┬───────┬─┘             │
                │        │        │       │               │
                ▼        ▼        ▼       ▼               ▼
              ┌────┐  ┌────┐  ┌────┐    ┌────┐      ┌─────────────┐
              │RAG │  │LLM │  │MCP │    │Open│      │  RAG (8000) │
              └────┘  └────┘  └────┘    │AI  │      │  documents  │
                │                       └────┘      └─────────────┘
                └───────── (فقط داخلی، بدون host port) ───┘