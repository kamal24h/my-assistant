
                         ┌─────────────────────────────────────┐
                         │          Client (Web/Mobile)        │
                         └──────────────────┬──────────────────┘
                                            │
                                            │ HTTPS
                                            ▼
                         ┌─────────────────────────────────────┐
                         │        Assistant API (8100)         │
                         │  ─ Session / Conversation Mgmt      │
                         │  ─ Data Transformation (future)     │
                         │  ─ Document Management (forward)    │
                         └──┬─────────────────────────────┬────┘
                            │                             │
                   chat/stream/approvals              documents only
                            │                             │
                            ▼                             │
             ┌──────────────────────────────┐             │
             │    Coordinator (8101)        │             │
             │  ─ Orchestration             │             │
             │  ─ Routing / Tool Selection  │             │
             │  ─ Clarification / Approval  │             │
             │  ─ Conversation proxy        │             │
             └──┬────────┬────────┬───────┬─┘             │
                │        │        │       │               │
                ▼        ▼        ▼       ▼               ▼
              ┌────┐  ┌────┐  ┌────┐    ┌────┐      ┌─────────────┐
              │RAG │  │LLM │  │MCP │    │Open│      │  RAG (8102) │
              └────┘  └────┘  └────┘    │AI  │      │  documents  │
                │                       └────┘      └─────────────┘
                └───────── (فقط داخلی، بدون host port) ───┘