# scripts/ensure_qdrant_indexes.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ingest.ingest_service import get_qdrant_client, ensure_payload_indexes
from core.config import settings

def main():
    client = get_qdrant_client()
    if not client.collection_exists(settings.collection_name):
        print(f"Collection '{settings.collection_name}' does not exist. Create it first via an ingest.")
        return
    ensure_payload_indexes(client)
    print("Payload indexes ensured.")
    # نمایش لیست ایندکس‌های فعلی
    info = client.get_collection(settings.collection_name)
    print("Current payload schema:", info.payload_schema)

if __name__ == "__main__":
    main()

# اجرای اسکریپت در داکر
# docker compose exec fastapi python scripts/ensure_qdrant_indexes.py