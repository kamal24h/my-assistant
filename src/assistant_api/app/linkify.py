# src/assistant_api/app/linkify.py
"""Convert bare URLs in text to <a> tags for HTML rendering.

Usage:
    from app.linkify import linkify_html
    answer = linkify_html(answer)

Security:
    The transformation only replaces bare URLs with <a> tags. It does not
    interpret any other HTML. To avoid XSS when the client renders HTML,
    the upstream text must be trusted (LLM output is not HTML) and this
    function must not be applied to untrusted user-provided content.
"""
from __future__ import annotations

import logging

from linkify_it import LinkifyIt

logger = logging.getLogger(__name__)

_linkify = LinkifyIt()


def linkify_html(text: str) -> str:
    """Convert bare URLs in text to HTML anchors.

    - Preserves existing <a> tags (no double-wrapping).
    - Escapes nothing (caller must ensure text is safe or already escaped).
    """
    if not text:
        return text
    try:
        matches = _linkify.match(text) or []
    except Exception:
        logger.warning("linkify failed; returning original text")
        return text
    if not matches:
        return text
    # Reverse to avoid index shifting.
    for match in reversed(matches):
        raw = match.raw
        url = match.url
        # Skip if already inside an <a> tag (basic check).
        before = text[: match.index]
        if before.rfind("<a ") > before.rfind("</a>"):
            continue
        replacement = f'<a href="{url}" target="_blank" rel="noopener noreferrer">{raw}</a>'
        text = before + replacement + text[match.last_index:]
    return text