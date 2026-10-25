# scripts/reingest_current_documents.py
"""
یک‌بار اجرا شود تا به metadata وکتورهای موجود، فیلدهای نسخه‌بندی اضافه شود.
از set_payload استفاده می‌کند؛ embedding دوباره محاسبه نمی‌شود.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, FilterSelector

from config import settings
from database import SessionLocal, Document


def main():
    db = SessionLocal()
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
    )

    try:
        docs = db.query(Document).all()
        print(f"Found {len(docs)} documents in Postgres")

        for doc in docs:
            doc_id = str(doc.id)
            logical_doc_id = str(doc.logical_doc_id) if doc.logical_doc_id else doc_id
            version = doc.version or 1
            is_current = doc.is_current if doc.is_current is not None else True
            content_hash = doc.content_hash

            # روی Qdrant: با فیلتر doc_id تمام pointهای این ردیف را پیدا کن
            flt = Filter(
                must=[
                    FieldCondition(
                        key="metadata.doc_id",
                        match=MatchValue(value=doc_id),
                    )
                ]
            )

            payload = {
                "logical_doc_id": logical_doc_id,
                "doc_version": version,
                "is_current": is_current,
                "content_hash": content_hash,
                "app_id": doc.app_id,
                "doc_name": doc.doc_name,
            }

            # انتخاب تمام نقاط منطبق
            points, _next = client.scroll(
                collection_name=settings.collection_name,
                scroll_filter=flt,
                limit=10000,
                with_payload=False,
                with_vectors=False,
            )
            if not points:
                print(f"  [skip] {doc_id} ({doc.doc_name}) — no points found")
                continue

            point_ids = [p.id for p in points]
            client.set_payload(
                collection_name=settings.collection_name,
                payload=payload,
                points=point_ids,
            )
            print(f"  [ok]   {doc_id} ({doc.doc_name}) — {len(point_ids)} points updated")

        print("Re-ingest complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()