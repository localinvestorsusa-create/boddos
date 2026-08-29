import pytest
from fastapi.testclient import TestClient

from boddos.api import build_app
from boddos.config import Config, NodeCfg, NewsCfg
from boddos.services import news as news_module
from boddos.services.news import NewsManager


class FakeCurationProvider:
    def __init__(self, reply: str):
        self.reply = reply

    async def chat(self, model, messages):
        return self.reply


_RAW = [
    {"title": "AI breakthrough announced", "source": "TechSite", "date": "1h", "category": "Technology", "url": "https://a"},
    {"title": "New telescope launched", "source": "SciSite", "date": "2h", "category": "Science", "url": "https://b"},
    {"title": "AI breakthrough announced", "source": "TechSite", "date": "1h", "category": "Technology", "url": "https://a"},
]


async def test_disabled_reports_disabled():
    mgr = NewsManager(NewsCfg(enabled=False), FakeCurationProvider("[]"))
    res = await mgr.briefing("m")
    assert not res.ok
    assert "disabled" in res.error


async def test_not_installed_reports_cleanly(monkeypatch):
    monkeypatch.setattr(news_module, "DDGS", None)
    mgr = NewsManager(NewsCfg(), FakeCurationProvider("[]"))
    res = await mgr.briefing("m")
    assert not res.ok
    assert "not installed" in res.error


async def test_fallback_dedupes_when_ai_disabled(monkeypatch):
    mgr = NewsManager(NewsCfg(), FakeCurationProvider("unused"))
    monkeypatch.setattr(mgr, "_fetch_raw", lambda: list(_RAW))
    res = await mgr.briefing("m", use_ai=False)
    assert res.ok
    assert res.curated is False
    assert len(res.headlines) == 2  # the duplicate title was dropped


async def test_ai_curation_rewrites_titles(monkeypatch):
    reply = '[{"id": 0, "title": "AI wins big"}, {"id": 1, "title": "New scope"}]'
    mgr = NewsManager(NewsCfg(), FakeCurationProvider(reply))
    monkeypatch.setattr(mgr, "_fetch_raw", lambda: list(_RAW))
    res = await mgr.briefing("m", use_ai=True)
    assert res.ok
    assert res.curated is True
    titles = [h.title for h in res.headlines]
    assert titles == ["AI wins big", "New scope"]
    assert res.headlines[0].source == "TechSite"


async def test_ai_curation_falls_back_on_garbage_reply(monkeypatch):
    mgr = NewsManager(NewsCfg(), FakeCurationProvider("not json at all"))
    monkeypatch.setattr(mgr, "_fetch_raw", lambda: list(_RAW))
    res = await mgr.briefing("m", use_ai=True)
    assert res.ok
    assert res.curated is False
    assert len(res.headlines) == 2


async def test_cache_avoids_a_second_fetch(monkeypatch):
    mgr = NewsManager(NewsCfg(cache_minutes=15), FakeCurationProvider("[]"))
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return list(_RAW)

    monkeypatch.setattr(mgr, "_fetch_raw", fetch)
    await mgr.briefing("m", use_ai=False)
    await mgr.briefing("m", use_ai=False)
    assert calls["n"] == 1


async def test_empty_search_results_report_ok_with_no_headlines(monkeypatch):
    mgr = NewsManager(NewsCfg(), FakeCurationProvider("[]"))
    monkeypatch.setattr(mgr, "_fetch_raw", lambda: [])
    res = await mgr.briefing("m")
    assert res.ok
    assert res.headlines == []


@pytest.fixture
def client(tmp_path):
    cfg = Config(node=NodeCfg(id="test", role="host"))
    cfg.security.audit_log = str(tmp_path / "audit.log")
    app = build_app(cfg)
    app.state.node.news._fetch_raw = lambda: list(_RAW)
    with TestClient(app) as c:
        yield c


def test_briefing_endpoint_without_ai(client):
    r = client.get("/api/news/briefing", params={"use_ai": "false"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["headlines"]) == 2
