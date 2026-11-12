/* Serene Service Worker for 8 PM unwritten journal notifications */

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type === "SHOW_REMINDER") {
    self.registration.showNotification(data.title || "Evening Check-in", {
      body:
        data.body ||
        "Your daily journal is still open for today. Take two quiet minutes before midnight.",
      tag: "serene-8pm-reminder",
      renotify: false,
    });
  }
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) {
          client.postMessage({ type: "OPEN_JOURNAL" });
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow("/#journal");
      }
      return undefined;
    })
  );
});
