"""Privacy-preserving breach check for YOUR OWN credentials.

Uses the Have I Been Pwned "Pwned Passwords" range API with k-anonymity: only the
first 5 characters of the SHA-1 hash of your password are ever sent; the server
returns all suffixes in that bucket and the match is done locally. Your actual
password/hash never leaves the machine.

This checks your own secrets so you can rotate anything exposed. It is not a
lookup tool for other people.
"""
from __future__ import annotations

import hashlib

import httpx

_API = "https://api.pwnedpasswords.com/range/"


async def check_password(password: str) -> dict:
    if not password:
        return {"ok": False, "error": "empty password"}
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(_API + prefix, headers={"Add-Padding": "true",
                                                    "User-Agent": "BODDOS/0.1"})
            r.raise_for_status()
    except Exception as e:
        return {"ok": False, "error": f"breach service unavailable: {e}"}

    count = 0
    for line in r.text.splitlines():
        h, _, c = line.partition(":")
        if h.strip().upper() == suffix:
            count = int(c.strip() or 0)
            break
    return {
        "ok": True,
        "pwned": count > 0,
        "times_seen": count,
        "advice": ("This password appears in known breaches — do NOT reuse it; "
                   "change it everywhere and enable 2FA."
                   if count else "Not found in the breach corpus. Still use a "
                   "unique password per site."),
        "privacy": "only the first 5 chars of the hash were sent (k-anonymity)",
    }
