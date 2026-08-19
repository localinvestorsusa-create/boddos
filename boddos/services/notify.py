"""Deliver safety alerts to your trusted contacts.

Three channels, matching a contact's `channel`:
  * webhook — POST the alert JSON to a URL you control (works out of the box;
    point it at your own bot, Home Assistant, ntfy, etc.).
  * email   — SMTP (configure `services.notify.smtp`).
  * sms     — POST to a generic SMS-gateway URL template you configure
    (`services.notify.sms_webhook`), e.g. your own Twilio/relay endpoint.

Delivery is best-effort and returns a per-contact result so the UI/audit can
show what actually went out. Contacts are YOUR consenting people.
"""
from __future__ import annotations

import asyncio
import os
import smtplib
from email.message import EmailMessage

import httpx

from ..config import NotifyCfg


class Notifier:
    def __init__(self, cfg: NotifyCfg):
        self.cfg = cfg

    async def deliver_all(self, alerts: list[dict]) -> list[dict]:
        if not self.cfg.enabled:
            return [{"to": a.get("to"), "ok": False, "error": "notify disabled"} for a in alerts]
        return await asyncio.gather(*(self._deliver(a) for a in alerts))

    async def _deliver(self, alert: dict) -> dict:
        channel = alert.get("channel", "webhook")
        target = alert.get("target", "")
        body = alert.get("body", "")
        try:
            if channel == "webhook":
                return await self._webhook(target, alert)
            if channel == "sms":
                return await self._sms(target, body, alert.get("to", ""))
            if channel == "email":
                return await self._email(target, body, alert.get("to", ""))
            return {"to": alert.get("to"), "ok": False, "error": f"unknown channel {channel}"}
        except Exception as e:
            return {"to": alert.get("to"), "ok": False, "error": str(e)}

    async def _webhook(self, url: str, alert: dict) -> dict:
        if not url:
            return {"to": alert.get("to"), "ok": False, "error": "no webhook URL"}
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post(url, json=alert)
        return {"to": alert.get("to"), "channel": "webhook", "ok": r.status_code < 400,
                "status": r.status_code}

    async def _sms(self, target: str, body: str, to: str) -> dict:
        tmpl = self.cfg.sms_webhook
        if not tmpl:
            return {"to": to, "ok": False, "error": "no sms_webhook configured"}
        url = tmpl.replace("{target}", target).replace("{body}", body)
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post(url, json={"to": target, "body": body})
        return {"to": to, "channel": "sms", "ok": r.status_code < 400, "status": r.status_code}

    async def _email(self, target: str, body: str, to: str) -> dict:
        s = self.cfg.smtp
        if not s.host:
            return {"to": to, "ok": False, "error": "no SMTP configured"}
        password = os.environ.get("BODDOS_SMTP_PASSWORD", s.password)

        def _send() -> None:
            msg = EmailMessage()
            msg["Subject"] = "BODDOS safety alert"
            msg["From"] = s.from_addr or s.username
            msg["To"] = target
            msg.set_content(body)
            with smtplib.SMTP(s.host, s.port, timeout=10) as srv:
                if s.use_tls:
                    srv.starttls()
                if s.username:
                    srv.login(s.username, password)
                srv.send_message(msg)

        await asyncio.to_thread(_send)
        return {"to": to, "channel": "email", "ok": True}
