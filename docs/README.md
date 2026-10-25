A Smart Assistant for Custom Application Users consists of;
  - Local RAG for Application user guide documents,
  - Local LLM for Document Embeddings, Reasoning and Answer user Prompts.
  - External AI APIs for complex and analytical prompts.

I used Python for Coning language, Ollama for LLM runner, LangChain for AI framework, Qdrant for Vector DB, LangGraph for Agent Coordination,
Postgres for Permanent DB and source of truth, Redis for conversation and session caches,
RabbitMQ for async conversation persist publish.    
