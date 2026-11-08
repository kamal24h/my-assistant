"""Persian/Arabic text normalization and safe phrase replacement."""
from __future__ import annotations

import re
import unicodedata

_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED]")
_WHITESPACE = re.compile(r"\s+")


def normalize_text(value: str | None) -> str:
    """Normalize common Persian/Arabic spelling variants without stemming.

    This is deliberately conservative: it does not remove meaningful words,
    change word order, or transliterate product/entity names.
    """
    text = unicodedata.normalize("NFKC", value or "")
    text = text.translate(str.maketrans({
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "ٱ": "ا",
        "ـ": "",
        "\u200c": " ",  # normalize ZWNJ to a searchable space
    }))
    text = _DIACRITICS.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text


def replace_phrase(text: str, phrase: str, replacement: str) -> str:
    """Replace a whole normalized phrase, not a substring of another word."""
    if not phrase:
        return text
    pattern = re.compile(
        rf"(?<![\w]){re.escape(phrase)}(?![\w])",
        flags=re.IGNORECASE,
    )
    return pattern.sub(replacement, text)
