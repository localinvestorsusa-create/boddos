"""Web Push notifications (VAPID) so duress alerts hit the phone lock screen.

The phone PWA subscribes via a service worker; subscriptions are stored on the
node. On a duress/dead-man event the node pushes to every subscription, so the
alert shows even when the app is closed or the phone is locked.

Requires the `pywebpush` package (install extra: `pip install boddos[push]`).
If it's not installed, push degrades to a no-op with a clear status — the rest
of the system is unaffected.
"""
from __future__ import annotations

import json
from pathlib import Path

try:
    from pywebpush import webpush, WebPushException  # type: ignore
    _HAVE_PYWEBPUSH = True
except Exception:  # pragma: no cover - optional dep
    _HAVE_PYWEBPUSH = False


class PushManager:
    def __init__(self, vapid_public: str, vapid_private: str,
                 subject: str, store_path: str):
        self.vapid_public = vapid_public
        self.vapid_private = vapid_private
        self.subject = subject or "mailto:boddos@localhost"
        self.store_path = Path(store_path).expanduser()
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._subs: dict[str, dict] = self._load()

    @property
    def enabled(self) -> bool:
        return bool(_HAVE_PYWEBPUSH and self.vapid_public and self.vapid_private)

    def _load(self) -> dict[str, dict]:
        if self.store_path.exists():
            try:
                return json.loads(self.store_path.read_text())
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        self.store_path.write_text(json.dumps(self._subs))

    def subscribe(self, subscription: dict) -> dict:
        endpoint = subscription.get("endpoint")
        if not endpoint:
            return {"ok": False, "error": "invalid subscription"}
        self._subs[endpoint] = subscription
        self._save()
        return {"ok": True, "count": len(self._subs)}

    def unsubscribe(self, endpoint: str) -> dict:
        removed = self._subs.pop(endpoint, None) is not None
        self._save()
        return {"ok": removed}

    def count(self) -> int:
        return len(self._subs)

    def notify_all(self, title: str, body: str, data: dict | None = None) -> list[dict]:
        if not self.enabled:
            return [{"ok": False, "error": "push not configured"}]
        payload = json.dumps({"title": title, "body": body, "data": data or {}})
        results = []
        for endpoint, sub in list(self._subs.items()):
            try:
                webpush(
                    subscription_info=sub,
                    data=payload,
                    vapid_private_key=self.vapid_private,
                    vapid_claims={"sub": self.subject},
                )
                results.append({"endpoint": endpoint[:40], "ok": True})
            except WebPushException as e:  # type: ignore
                # Drop dead subscriptions (410 Gone / 404).
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status in (404, 410):
                    self._subs.pop(endpoint, None)
                    self._save()
                results.append({"endpoint": endpoint[:40], "ok": False, "status": status})
            except Exception as e:  # pragma: no cover - defensive
                results.append({"endpoint": endpoint[:40], "ok": False, "error": str(e)})
        return results
