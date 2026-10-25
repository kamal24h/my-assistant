# P1 ingestion/versioning patch

## Changes

- `POST /api/v1/documents/create-text` keeps its existing full-app replacement semantics, but stages and indexes every incoming text document before deleting existing PostgreSQL rows. If staging/indexing fails, staged vectors are compensated and the old records/vectors are left in place.
- Full replacement rejects blank documents and duplicate `doc_name` values in the same request.
- Old Qdrant vectors are deleted by their old `doc_id` after the PostgreSQL commit; it intentionally does not delete by `app_id` after writing new vectors.
- `POST /api/v1/documents/create-text2` remains the versioned Upsert endpoint. Each document is processed independently and reports `created`, `updated`, `skipped`, or `failed`; a failed document does not stop later documents.
- The versioned endpoint does not demote the previous version until the new version has been indexed and committed in PostgreSQL.
- Failed/partial Qdrant writes are cleaned up by the new `doc_id`, even if the indexing function raised before returning a chunk count.
- The file upload endpoint (`POST /api/v1/documents/create`) also delays demoting the old version until after the new version was indexed and committed.

## Response contract for create-text2

Top-level `status`: `completed`, `partial`, or `failed`.

`summary` includes counts for `created`, `updated`, `skipped`, and `failed`.

Each document result includes `docName` and `status`; successful/unchanged results include IDs/version/chunk count, and failed results include an `error` message.

## Important limitations / follow-up

- PostgreSQL and Qdrant do not share a distributed transaction. If the post-commit Qdrant update/deletion fails, the code logs the error, but reconciliation/repair tooling is still needed to guarantee eventual consistency. Do not treat this patch as full distributed-transaction support.
- The existing full replacement endpoint removes document history by design. Use `/create-text2` when version history must be preserved.
- Syntax compilation was run on all 20 Python files. No live integration tests were run because they require the project's PostgreSQL, Qdrant, Ollama, and application configuration.
- Review `.env` separately and never share real credentials. Rotate any credentials that may have been exposed.
