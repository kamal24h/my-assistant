"""Load and resolve glossary terms against user text."""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from app.terminology.context_builder import build_terminology_context
from app.terminology.models import (
    TerminologyEntry,
    TerminologyFile,
    TerminologyMatch,
    TerminologyResolution,
)
from app.terminology.normalizer import normalize_text, replace_phrase

logger = logging.getLogger(__name__)


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(
        rf"(?<![\w]){re.escape(phrase)}(?![\w])",
        text,
        flags=re.IGNORECASE,
    ))


class TerminologyResolver:
    """File-backed glossary resolver with application scoping and hot reload."""

    def __init__(
        self,
        file_path: str | Path,
        *,
        max_matches: int = 12,
        max_context_chars: int = 3000,
    ) -> None:
        self.file_path = Path(file_path)
        self.max_matches = max(1, max_matches)
        self.max_context_chars = max(256, max_context_chars)
        self._mtime_ns: int | None = None
        self._entries: list[TerminologyEntry] = []
        self._load()

    def _load(self) -> None:
        try:
            stat = self.file_path.stat()
            if self._mtime_ns == stat.st_mtime_ns:
                return
            raw = json.loads(self.file_path.read_text(encoding="utf-8"))
            glossary = TerminologyFile.model_validate(raw)
            self._entries = [
                entry for entry in glossary.terms if entry.status == "active"
            ]
            self._mtime_ns = stat.st_mtime_ns
            logger.info(
                "Loaded terminology glossary: entries=%d file=%s version=%d",
                len(self._entries), self.file_path, glossary.version,
            )
        except FileNotFoundError:
            self._entries = []
            self._mtime_ns = None
            logger.warning("Terminology glossary file not found: %s", self.file_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            # Keep last known-good entries if a new file is malformed.
            logger.exception("Could not load terminology glossary: %s", exc)

    @staticmethod
    def _is_applicable(entry: TerminologyEntry, app_id: str | None) -> bool:
        return not entry.app_ids or not app_id or app_id in entry.app_ids

    def resolve(self, text: str, *, app_id: str | None = None) -> TerminologyResolution:
        self._load()
        original = text or ""
        normalized = normalize_text(original)
        candidates: list[tuple[int, int, TerminologyEntry, str]] = []

        for entry in self._entries:
            if not self._is_applicable(entry, app_id):
                continue
            phrases = [entry.canonical, *entry.aliases]
            for phrase in phrases:
                normalized_phrase = normalize_text(phrase)
                if not normalized_phrase:
                    continue
                # A single entry is matched once, preferring its longest phrase.
                if _contains_phrase(normalized, normalized_phrase):
                    candidates.append((
                        len(normalized_phrase), entry.priority, entry, normalized_phrase
                    ))

        candidates.sort(key=lambda item: (-item[0], item[1], item[2].term_id))
        selected: list[tuple[TerminologyEntry, str]] = []
        occupied: list[str] = []
        seen_ids: set[str] = set()
        for _length, _priority, entry, phrase in candidates:
            if entry.term_id in seen_ids:
                continue
            # Avoid overlapping matches such as a generic alias inside a longer term.
            if any(phrase in prior or prior in phrase for prior in occupied):
                continue
            selected.append((entry, phrase))
            occupied.append(phrase)
            seen_ids.add(entry.term_id)
            if len(selected) >= self.max_matches:
                break

        matches: list[TerminologyMatch] = []
        normalized_query = normalized
        search_terms: list[str] = []
        for entry, phrase in selected:
            normalized_query = replace_phrase(normalized_query, phrase, normalize_text(entry.canonical))
            matches.append(TerminologyMatch(
                term_id=entry.term_id,
                canonical=entry.canonical,
                matched_text=phrase,
                definition=entry.definition,
                domain=entry.domain,
                entity_type=entry.entity_type,
                related_terms=entry.related_terms,
                search_terms=entry.search_terms,
                intent_hints=entry.intent_hints,
                form_id=entry.form_id,
                priority=entry.priority,
            ))
            for term in [entry.canonical, *entry.aliases, *entry.related_terms, *entry.search_terms]:
                cleaned = normalize_text(term)
                if cleaned and cleaned.casefold() not in {x.casefold() for x in search_terms}:
                    search_terms.append(cleaned)
                    if len(search_terms) >= 30:
                        break
            if len(search_terms) >= 30:
                break

        context = build_terminology_context(
            matches, max_chars=self.max_context_chars
        )
        return TerminologyResolution(
            original_text=original,
            normalized_text=normalized_query,
            matches=matches,
            search_terms=search_terms,
            context=context,
        )


@lru_cache(maxsize=4)
def _resolver_for(path: str, max_matches: int, max_context_chars: int) -> TerminologyResolver:
    return TerminologyResolver(
        path, max_matches=max_matches, max_context_chars=max_context_chars
    )


def get_terminology_resolver() -> TerminologyResolver:
    """Return the process-wide resolver configured by environment settings."""
    from app.core.config import settings

    return _resolver_for(
        settings.terminology_file,
        settings.terminology_max_matches,
        settings.terminology_max_context_chars,
    )
