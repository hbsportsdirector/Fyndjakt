// Fyndjakt – tar emot morgonnotiser. Ingen cachning: sidan hämtas alltid färsk.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = { title: "Fyndjakt", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "Fyndjakt", {
    body: d.body || "Nya fynd väntar.", tag: d.tag || "fyndjakt", icon: "ikon-192.png", badge: "favicon.png",
    data: { url: d.url || self.registration.scope },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || self.registration.scope;
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((lista) => {
    for (const c of lista) if (c.url.startsWith(self.registration.scope) && "focus" in c) return c.focus();
    return self.clients.openWindow(url);
  }));
});
