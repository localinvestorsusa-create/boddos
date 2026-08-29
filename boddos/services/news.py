"""AI-curated daily news briefing: raw headlines via DuckDuckGo's news
search, then selected and rewritten by the local chat model — the same
"small model, specialized external tool" split as the rest of this
project. DuckDuckGo does the actual searching (real, current headlines);
the model's only job is picking the best few and writing punchy titles.

Falls back to the raw (uncurated) headlines if the model call fails, so a
briefing still shows up even with no model running.

Needs `pip install 'boddos[news]'` (duckduckgo_search).
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field

from ..config import NewsCfg
from ..models.ollama_adapter import OllamaProvider
from ..models.base import ChatMessage

try:
    from duckduckgo_search import DDGS
except ImportError:  # pragma: no cover - exercised via the ok=False path
    DDGS = None

_QUERIES: list[tuple[str, str, int]] = [
    ("top news", "Top Stories", 5),
    ("technology news", "Technology", 5),
    ("science breakthrough", "Science", 3),
]

_CURATE_PROMPT = """You are a news editor. Here are raw headlines as JSON:
{items}

Pick the {n} most important and diverse stories. Rewrite each title to be
punchy and under 10 words. Reply with ONLY a JSON array, no markdown, no
other text: [{{"id": <original id>, "title": "<rewritten title>"}}]"""


@dataclass
class Headline:
    title: str
    source: str = ""
    date: str = ""
    category: str = ""
    url: str = ""
    image: str | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class BriefingResult:
    ok: bool
    error: str = ""
    curated: bool = False
    headlines: list[Headline] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "error": self.error, "curated": self.curated,
                "headlines": [h.to_dict() for h in self.headlines]}


class NewsManager:
    def __init__(self, cfg: NewsCfg, provider: OllamaProvider):
        self.cfg = cfg
        self.provider = provider
        self._cache: tuple[float, BriefingResult] | None = None

    def _cached(self) -> BriefingResult | None:
        if self._cache is None:
            return None
        ts, result = self._cache
        if time.time() - ts > self.cfg.cache_minutes * 60:
            return None
        return result

    async def briefing(self, model: str, use_ai: bool = True) -> BriefingResult:
        if not self.cfg.enabled:
            return BriefingResult(ok=False, error="news briefing disabled on this node (set services.news.enabled: true)")
        if DDGS is None:
            return BriefingResult(ok=False, error="duckduckgo_search not installed (pip install 'boddos[news]')")

        cached = self._cached()
        if cached is not None:
            return cached

        try:
            raw = await asyncio.to_thread(self._fetch_raw)
        except Exception as e:
            return BriefingResult(ok=False, error=f"news search failed: {e}")

        if not raw:
            return BriefingResult(ok=True, headlines=[])

        headlines = await self._curate(model, raw) if use_ai else None
        curated = headlines is not None
        if headlines is None:
            headlines = self._dedupe_fallback(raw)

        result = BriefingResult(ok=True, curated=curated, headlines=headlines)
        self._cache = (time.time(), result)
        return result

    def _fetch_raw(self) -> list[dict]:
        raw: list[dict] = []
        with DDGS() as ddgs:
            for query, category, limit in _QUERIES:
                for r in ddgs.news(query, max_results=limit):
                    r = dict(r)
                    r["category"] = category
                    raw.append(r)
        return raw

    def _dedupe_fallback(self, raw: list[dict]) -> list[Headline]:
        seen: set[str] = set()
        out: list[Headline] = []
        for item in raw:
            title = item.get("title", "")
            if not title or title in seen:
                continue
            seen.add(title)
            out.append(Headline(title=title, source=item.get("source", ""), date=item.get("date", ""),
                                category=item.get("category", ""), url=item.get("url", ""),
                                image=item.get("image")))
        return out[:8]

    async def _curate(self, model: str, raw: list[dict]) -> list[Headline] | None:
        items = [{"id": i, "title": n.get("title"), "source": n.get("source"), "category": n.get("category")}
                for i, n in enumerate(raw)]
        prompt = _CURATE_PROMPT.format(items=json.dumps(items), n=min(6, len(items)))
        reply = await self.provider.chat(model, [ChatMessage("user", prompt)])
        content = reply.strip()
        if "```" in content:
            content = content.split("```")[1]
            content = content[4:] if content.startswith("json") else content
        try:
            selected = json.loads(content)
        except json.JSONDecodeError:
            return None

        out: list[Headline] = []
        for s in selected:
            try:
                original = raw[int(s["id"])]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            out.append(Headline(
                title=s.get("title") or original.get("title", ""),
                source=original.get("source", ""), date=original.get("date", ""),
                category=original.get("category", ""), url=original.get("url", ""),
                image=original.get("image"),
            ))
        return out or None
