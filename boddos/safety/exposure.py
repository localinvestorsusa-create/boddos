"""Your-own OSINT exposure audit.

Turns "what could someone find about ME?" into an actionable checklist so you can
lock down your footprint. This is defensive: it audits the operator's OWN
identifiers (the ones you supply), then uses the local advisor model to produce
prioritized reduction steps. It does not build dossiers on other people.

The audit intentionally does not scrape data brokers automatically — that varies
by jurisdiction and often violates site terms. Instead it enumerates the surfaces
to check and (optionally) asks your local model to reason about likely exposure
and concrete opt-out / hardening actions.
"""
from __future__ import annotations

import re

from ..models.base import ChatMessage, ModelProvider

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Common exposure surfaces to review for your own identifiers.
SURFACES = [
    "People-search / data-broker sites (Spokeo, Whitepages, BeenVerified, etc.) — request opt-out",
    "Public breach corpora — check Have I Been Pwned for your email; rotate reused passwords",
    "Social media privacy settings, old public posts, and tagged photos",
    "Home address leakage via package photos, property records, voter rolls",
    "Phone number reuse across accounts (enables SIM-swap / correlation)",
    "EXIF geolocation in photos you've posted publicly",
    "Professional/registration databases and resumes with personal details",
    "Reused usernames that link accounts across sites",
]

_SYSTEM = (
    "You are a personal privacy/opsec advisor. The user is auditing THEIR OWN "
    "exposure to reduce it. Given the identifiers they provide, produce a "
    "prioritized, concrete action plan to minimize what a stranger could find. "
    "Focus on opt-outs, account hardening, and habits. Do not attempt to look up "
    "or invent third parties' information."
)


def classify_identifier(value: str) -> str:
    v = value.strip()
    if _EMAIL_RE.match(v):
        return "email"
    if re.fullmatch(r"\+?\d[\d\s\-()]{6,}", v):
        return "phone"
    if v.startswith(("http://", "https://")):
        return "url"
    if " " in v:
        return "name"
    return "username"


class ExposureAudit:
    def __init__(self, provider: ModelProvider, model: str):
        self.provider = provider
        self.model = model

    def surfaces_for(self, identifiers: list[str]) -> dict:
        typed = [{"value": v, "kind": classify_identifier(v)} for v in identifiers]
        return {"identifiers": typed, "surfaces_to_review": SURFACES}

    async def plan(self, identifiers: list[str]) -> dict:
        typed = self.surfaces_for(identifiers)
        prompt = (
            "My identifiers to audit (mine):\n"
            + "\n".join(f"- {t['kind']}: {t['value']}" for t in typed["identifiers"])
            + "\n\nGive me a prioritized action plan to reduce my public exposure."
        )
        advice = await self.provider.chat(
            self.model,
            [ChatMessage("system", _SYSTEM), ChatMessage("user", prompt)],
        )
        return {**typed, "action_plan": advice}
