/* Alerta Global — Service Worker: cache de interface e últimas notícias. */
const VERSION = "ag-v9-20261117-fontes-500";
const SHELL = "alerta-shell-" + VERSION;
const DATA = "alerta-dados-" + VERSION;
const ASSETS = ["./", "./index.html", "./manifest.webmanifest", "./icons/icon-192.png", "./icons/icon-512.png", "./icons/alerta-global.svg"];
const ROOT = new URL("./", self.registration.scope);
const NEWS = new URL("noticias.json", ROOT).href;
const SOURCES = new URL("status_fontes.json", ROOT).href;
self.addEventListener("install", event => {
  event.waitUntil(caches.open(SHELL).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(Promise.all([
    caches.keys().then(keys => Promise.all(keys.filter(key => (key.startsWith("alerta-") && key !== SHELL && key !== DATA)).map(key => caches.delete(key)))),
    self.clients.claim()
  ]));
});
self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.endsWith("/noticias.json") || url.pathname.endsWith("/status_fontes.json")) {
    event.respondWith((async () => {
      const cache = await caches.open(DATA);
      const cacheKey = url.pathname.endsWith("/status_fontes.json") ? SOURCES : NEWS;
      try {
        const response = await fetch(request);
        if (!response.ok) throw new Error("HTTP " + response.status);
        await cache.put(cacheKey, response.clone());
        return response;
      } catch (error) {
        const saved = await cache.match(cacheKey);
        const blank = cacheKey === SOURCES ? "{}" : "[]";
        return saved || new Response(blank, { headers: { "Content-Type": "application/json; charset=utf-8" } });
      }
    })());
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const response = await fetch(request);
        if (response.ok) {
          const cache = await caches.open(SHELL);
          await cache.put("./index.html", response.clone());
        }
        return response;
      } catch (error) {
        return (await caches.match("./index.html")) || Response.error();
      }
    })());
    return;
  }
  event.respondWith((async () => {
    const cached = await caches.match(request);
    if (cached) return cached;
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(SHELL);
      await cache.put(request, response.clone());
    }
    return response;
  })());
});
self.addEventListener("notificationclick", event => {
  event.notification.close();
  const target = new URL("index.html#radar", ROOT).href;
  event.waitUntil((async () => {
    const clientsList = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of clientsList) {
      if (client.url.startsWith(ROOT.href)) {
        await client.focus();
        return;
      }
    }
    await self.clients.openWindow(target);
  })());
});
