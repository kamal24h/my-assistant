# Terminology / Glossary

The glossary is a curated, application-aware vocabulary used by the Coordinator
and forwarded to Local RAG as auxiliary context and retrieval expansion terms.
It does not replace ERP data, document evidence, or authorization checks.

## Data file

Default path inside the Coordinator container:

`/app/app/terminology/data/terms.json`

Override with `TERMINOLOGY_FILE`. The resolver checks the file modification time
and reloads it after a valid update. If a replacement file is malformed, the last
known-good in-memory glossary is retained.

## Entry contract

| Field | Required | Meaning |
|---|---:|---|
| `term_id` | yes | Stable unique identifier, lowercase snake_case recommended |
| `canonical` | yes | Preferred display/search term |
| `aliases` | no | Synonyms, abbreviations, spelling variants |
| `definition` | no | Short approved business definition |
| `domain` | no | Business domain such as inventory or procurement |
| `app_ids` | no | ERP application IDs; empty means global |
| `entity_type` | no | Business entity/document/form category |
| `related_terms` | no | Related concepts useful for interpretation |
| `search_terms` | no | Additional retrieval expansion terms |
| `intent_hints` | no | Phrases describing common user intents; hints only |
| `form_id` | no | Exact ERP form identifier, only when confirmed |
| `status` | no | `active` or `inactive` |
| `priority` | no | Lower value wins when matches overlap |

## Operational rules

- Keep `term_id` stable across revisions; do not reuse IDs for a different concept.
- Add only terms confirmed by the ERP process owner/documentation team.
- Use `app_ids` to prevent a term from leaking into unrelated ERP applications.
- Do not populate `form_id` with guessed values.
- Set `status` to `inactive` instead of deleting a term that may be referenced in
  audit or test data.
- Definitions and intent hints are explanatory hints, not authoritative policy.
- Keep aliases specific. Broad words such as «درخواست» should not be aliases.
- Validate JSON before deployment. Invalid updates are logged and the last valid
  in-memory version remains active.

The included entries are examples only. Replace or approve them with your ERP's
actual terminology before production use.
