// BODDOS service worker — receives Web Push and shows lock-screen notifications.
self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let payload = { title: "BODDOS", body: "Alert" };
  try { payload = event.data.json(); } catch (e) { if (event.data) payload.body = event.data.text(); }
  const opts = {
    body: payload.body,
    tag: "boddos-alert",
    renotify: true,
    requireInteraction: true,
    vibrate: [200, 100, 200, 100, 400],
    data: payload.data || {},
  };
  event.waitUntil(self.registration.showNotification(payload.title || "BODDOS", opts));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((cls) => {
      for (const c of cls) if ("focus" in c) return c.focus();
      if (self.clients.openWindow) return self.clients.openWindow("/");
    })
  );
});
