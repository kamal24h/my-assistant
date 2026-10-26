# ingest_service.py
import hashlib
import uuid
from typing import Any, Dict, List, Optional

from langchain_community.document_loaders import (
    UnstructuredWordDocumentLoader,
    PyPDFLoader,
)
from langchain_core.documents import Document as LangChainDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance, VectorParams, Filter, FieldCondition, MatchValue,
    PointIdsList,
)

from core.config import settings


# ---------- UUIDv5 برای point_id deterministic ----------
POINT_ID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # NAMESPACE_URL


def make_point_id(logical_doc_id: str, version: int) -> str:
    """
    تولید point_id یکتا و deterministic برای هر (logical_doc_id, version).
    باعث می‌شود ingest دوباره همان نسخه، به overwrite منجر شود (dedup).
    """
    return str(uuid.uuid5(POINT_ID_NAMESPACE, f"{logical_doc_id}:{version}"))


def compute_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------- Qdrant / Embeddings helpers ----------

def get_qdrant_client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
    )


def get_embeddings() -> OllamaEmbeddings:
    return OllamaEmbeddings(
        model=settings.embedding_model,
        base_url=settings.ollama_url,
    )


PERSIAN_AWARE_SEPARATORS = [
    "\n\n",
    "\n",
    ". ",
    "؟ ",
    "? ",
    "! ",
    "؛ ",
    "، ",
    " ",
    "",
]


def get_text_splitter():
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=PERSIAN_AWARE_SEPARATORS,
        add_start_index=True,
    )


def ensure_collection_exists(client: QdrantClient, embeddings: OllamaEmbeddings):
    if client.collection_exists(settings.collection_name):
        return

    sample_vector = embeddings.embed_query("init")
    client.create_collection(
        collection_name=settings.collection_name,
        vectors_config=VectorParams(
            size=len(sample_vector),
            distance=Distance.COSINE,
        ),
    )


def _get_vector_store():
    client = get_qdrant_client()
    embeddings = get_embeddings()
    ensure_collection_exists(client, embeddings)

    return QdrantVectorStore(
        client=client,
        collection_name=settings.collection_name,
        embedding=embeddings,
    )


def _add_documents_in_batches(
    vector_store: QdrantVectorStore,
    documents: List[LangChainDocument],
    ids: List[str],
):
    for index in range(0, len(documents), settings.embed_batch_size):
        batch = documents[index : index + settings.embed_batch_size]
        batch_ids = ids[index : index + settings.embed_batch_size]
        vector_store.add_documents(batch, ids=batch_ids)


def _split_and_enrich(
    documents: List[LangChainDocument],
    base_metadata: Dict[str, Any],
):
    splitter = get_text_splitter()
    chunks = splitter.split_documents(documents)
    for chunk in chunks:
        chunk.metadata.update(base_metadata)
    return chunks


# ---------- استخراج متن خام (برای hash و ingest) ----------

def extract_text_from_file(file_path: str, doc_type: str) -> str:
    normalized_type = doc_type.lower()
    if normalized_type == "pdf":
        loader = PyPDFLoader(file_path)
    elif normalized_type in ("doc", "docx"):
        loader = UnstructuredWordDocumentLoader(file_path)
    else:
        raise ValueError(f"نوع سند '{doc_type}' پشتیبانی نمی‌شود.")

    docs = loader.load()
    return "\n\n".join(d.page_content for d in docs)


# ---------- Ingest ----------

def process_and_index_document(
    file_path: str,
    doc_id: str,
    logical_doc_id: str,
    version: int,
    content_hash: str,
    is_current: bool,
    doc_name: str,
    doc_type: str,
    department: str,
    app_id: str,
    metadata: Dict[str, Any],
) -> int:
    normalized_type = doc_type.lower()
    if normalized_type == "pdf":
        loader = PyPDFLoader(file_path)
    elif normalized_type in ("doc", "docx"):
        loader = UnstructuredWordDocumentLoader(file_path)
    else:
        raise ValueError(f"نوع سند '{doc_type}' پشتیبانی نمی‌شود.")

    raw_documents = loader.load()
    if not raw_documents:
        return 0

    base_metadata = {
        **(metadata or {}),
        "doc_id": doc_id,                 # ردیف فعلی documents
        "logical_doc_id": logical_doc_id, # کل سند
        "doc_version": version,
        "is_current": is_current,
        "content_hash": content_hash,
        "doc_name": doc_name,
        "department": department,
        "app_id": app_id,        
    }

    chunks = _split_and_enrich(raw_documents, base_metadata)
    if not chunks:
        return 0

    vector_store = _get_vector_store()

    # point_id deterministic برای هر (logical_doc_id, version)
    point_id = make_point_id(logical_doc_id, version)
    # همه chunk ها id یکتا می‌خواهند؛ از point_id مشتق می‌کنیم.
    chunk_ids = [f"{point_id}" if i == 0 else f"{point_id}-{i}" for i in range(len(chunks))]
    # ولی Qdrant فقط UUID یا int قبول می‌کند. پس UUIDv5 دوم بسازیم:
    chunk_ids = [
        str(uuid.uuid5(POINT_ID_NAMESPACE, f"{logical_doc_id}:{version}:chunk:{i}"))
        for i in range(len(chunks))
    ]
    for chunk, chunk_id in zip(chunks, chunk_ids):
        chunk.metadata["chunk_id"] = chunk_id
        chunk.metadata["chunk_hash"] = compute_content_hash(chunk.page_content or "")

    _add_documents_in_batches(vector_store, chunks, chunk_ids)
    return len(chunks)


def process_and_index_text_document(
    doc_text: str,
    doc_id: str,
    logical_doc_id: str,
    version: int,
    content_hash: str,
    is_current: bool,
    doc_name: str,
    app_id: str,
    metadata: Dict[str, Any],
) -> int:
    if not doc_text or not doc_text.strip():
        return 0

    document = LangChainDocument(page_content=doc_text, metadata={})
    base_metadata = {
        **(metadata or {}),
        "doc_id": doc_id,
        "logical_doc_id": logical_doc_id,
        "doc_version": version,
        "is_current": is_current,
        "content_hash": content_hash,
        "doc_name": doc_name,
        "app_id": app_id,        
    }

    chunks = _split_and_enrich([document], base_metadata)
    if not chunks:
        return 0

    vector_store = _get_vector_store()

    chunk_ids = [
        str(uuid.uuid5(POINT_ID_NAMESPACE, f"{logical_doc_id}:{version}:chunk:{i}"))
        for i in range(len(chunks))
    ]
    for chunk, chunk_id in zip(chunks, chunk_ids):
        chunk.metadata["chunk_id"] = chunk_id
        chunk.metadata["chunk_hash"] = compute_content_hash(chunk.page_content or "")

    _add_documents_in_batches(vector_store, chunks, chunk_ids)
    return len(chunks)


# ---------- Delete ----------

def delete_document_vectors_by_doc_id(doc_id: str):
    """
    حذف وکتورهای یک ردیف documents (یک نسخه خاص).
    """
    client = get_qdrant_client()
    if not client.collection_exists(settings.collection_name):
        return

    client.delete(
        collection_name=settings.collection_name,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="metadata.doc_id",
                    match=MatchValue(value=doc_id),
                )
            ]
        ),
    )


def delete_document_vectors_by_logical_id(logical_doc_id: str):
    """
    حذف وکتورهای همه نسخه‌های یک سند منطقی.
    """
    client = get_qdrant_client()
    if not client.collection_exists(settings.collection_name):
        return

    client.delete(
        collection_name=settings.collection_name,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="metadata.logical_doc_id",
                    match=MatchValue(value=logical_doc_id),
                )
            ]
        ),
    )


def delete_document_vectors(doc_id: str):
    """برای سازگاری با کد قبلی."""
    return delete_document_vectors_by_doc_id(doc_id)
  

def mark_version_not_current(logical_doc_id: str, version: int) -> None:
    """
    فلگ metadata.is_current وکتورهای یک نسخه خاص را False می‌کند.
    برای همگام‌سازی Qdrant با Postgres هنگام ساخت نسخه جدید لازم است.
    """
    
    client = get_qdrant_client()
    if not client.collection_exists(settings.collection_name):
        return

    client.set_payload(
        collection_name=settings.collection_name,
        payload={"is_current": False},
        key="metadata",
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="metadata.logical_doc_id",
                    match=MatchValue(value=logical_doc_id),
                ),
                FieldCondition(
                    key="metadata.doc_version",
                    match=MatchValue(value=version),
                ),
            ]
        ),
    )


def mark_version_current(logical_doc_id: str, version: int) -> None:
    client = get_qdrant_client()
    if not client.collection_exists(settings.collection_name):
        return

    client.set_payload(
        collection_name=settings.collection_name,
        payload={"is_current": True},
        key="metadata",
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="metadata.logical_doc_id",
                    match=MatchValue(value=logical_doc_id),
                ),
                FieldCondition(
                    key="metadata.doc_version",
                    match=MatchValue(value=version),
                ),
            ]
        ),
    )


def delete_document_vectors_by_app_id(app_id: str) -> None:
    """
    حذف همه وکتورهای یک app_id (همه اسناد، همه نسخه‌ها).
    """
    client = get_qdrant_client()
    if not client.collection_exists(settings.collection_name):
        return

    client.delete(
        collection_name=settings.collection_name,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="metadata.app_id",
                    match=MatchValue(value=app_id),
                )
            ]
        ),
    )
