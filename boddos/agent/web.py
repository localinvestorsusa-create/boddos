"""Fetch and lightly parse a web page for the agent / advisor."""
from __future__ import annotations

import re

import httpx

_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\n\s*\n\s*\n+")


def _strip_html(html: str) -> str:
    html = _TAG_RE.sub(" ", html)
    text = _HTML_RE.sub(" ", html)
    text = re.sub(r"[ \t]+", " ", text)
    return _WS_RE.sub("\n\n", text).strip()


async def fetch_url(url: str, max_chars: int = 12000) -> dict:
    """Fetch a URL and return {url, status, title, text} (text is de-tagged)."""
    if not url.startswith(("http://", "https://")):
        return {"url": url, "status": 0, "error": "only http(s) URLs allowed"}
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": "BODDOS/0.1 (personal-assistant)"})
        title_m = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S | re.I)
        return {
            "url": str(r.url),
            "status": r.status_code,
            "title": (title_m.group(1).strip() if title_m else ""),
            "text": _strip_html(r.text)[:max_chars],
        }
    except Exception as e:
        return {"url": url, "status": 0, "error": str(e)}
