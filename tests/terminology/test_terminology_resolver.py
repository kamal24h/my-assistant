from pathlib import Path

from app.terminology.normalizer import normalize_text
from app.terminology.resolver import TerminologyResolver


def test_persian_normalization():
    assert normalize_text("كالا\nي\nرسید\nانبار") == "کالا ی رسید انبار"


def test_alias_resolution_and_search_expansion(tmp_path: Path):
    glossary = tmp_path / "terms.json"
    glossary.write_text(
        '''{
          "version": 1,
          "terms": [{
            "term_id": "inventory_receipt",
            "canonical": "رسید انبار",
            "aliases": ["رسید کالا"],
            "definition": "سند ورود کالا",
            "domain": "inventory",
            "app_ids": ["inventory"],
            "related_terms": ["ورود کالا"],
            "search_terms": ["رسید کالا"],
            "intent_hints": ["مشاهده رسید"],
            "status": "active"
          }]
        }''',
        encoding="utf-8",
    )
    resolver = TerminologyResolver(glossary)
    result = resolver.resolve("وضعیت رسید کالا را نشان بده", app_id="inventory")

    assert result.matches[0].term_id == "inventory_receipt"
    assert "رسید انبار" in result.normalized_text
    assert "ورود کالا" in result.search_terms
    assert "سند ورود کالا" in result.context


def test_app_scope_and_word_boundary(tmp_path: Path):
    glossary = tmp_path / "terms.json"
    glossary.write_text(
        '''{"version":1,"terms":[{
          "term_id":"receipt","canonical":"رسید انبار",
          "aliases":["رسید"],"app_ids":["inventory"],"status":"active"
        }]}''',
        encoding="utf-8",
    )
    resolver = TerminologyResolver(glossary)
    assert not resolver.resolve("رسیدگی به درخواست", app_id="inventory").matches
    assert not resolver.resolve("رسید کالا", app_id="sales").matches
    assert resolver.resolve("رسید کالا", app_id="inventory").matches
