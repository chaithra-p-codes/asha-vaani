/* ASHA Vaani service worker: caches the app shell only, so the PWA opens without
   network. API calls and the visit WebSocket are never cached - live Gnani speech
   processing needs a connection, and the UI says so instead of pretending. */
const CACHE = "asha-vaani-shell-v3";
const SHELL = ["/", "/styles.css", "/manifest.webmanifest", "/icons/icon.svg", "/icons/logo.png", "/audio/pcm-capture-worklet.js",
  "/assets/main.js"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/")) return;
  // network first for the shell (fresh code during the hackathon), cache as offline fallback
  e.respondWith(
    fetch(e.request).then((resp) => {
      if (resp.ok && (SHELL.includes(url.pathname) || url.pathname.startsWith("/assets/"))) {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
      }
      return resp;
    }).catch(() => caches.match(e.request).then((r) => r || caches.match("/")))
  );
});
