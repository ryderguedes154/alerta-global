/* Alerta Global — Service Worker: cache de interface e últimas notícias. */
const VERSION = "ag-v23-20261118-botao-atualizar";
const SHELL = "alerta-shell-" + VERSION;
const DATA = "alerta-dados-" + VERSION;
const ASSETS = ["./", "./index.html", "./manifest.webmanifest", "./portal-claro.css", "./icons/logo-alerta-global-horizontal.svg", "./icons/icon-192.png", "./icons/icon-512.png", "./icons/alerta-global.svg"];
const ROOT = new URL("./", self.registration.scope);
const NEWS = new URL("noticias.json", ROOT).href;
const SOURCES = new URL("status_fontes.json", ROOT).href;
self.addEventListener("install", event => {
  event.waitUntil(caches.open(SHELL).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener("message", event => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
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
  // JSON dinâmico sempre é consultado na rede, sem cache infinito para ?t=...
  // Uma cópia por arquivo já consultado permanece disponível offline.
  const dynamicJson = /\/(?:noticias|status_fontes|destaques-radar|curadoria-chatgpt)\.json$/.test(url.pathname)
    || /\/historico\/(?:indice|\d{4}-\d{2})\.json$/.test(url.pathname);
  if (dynamicJson) {
    event.respondWith((async () => {
      const cache = await caches.open(DATA);
      const cacheKey = url.origin + url.pathname;
      try {
        const response = await fetch(request);
        if (!response.ok) throw new Error("HTTP " + response.status);
        await cache.put(cacheKey, response.clone());
        return response;
      } catch (error) {
        const saved = await cache.match(cacheKey);
        if (saved) return saved;
        const blank = url.pathname.endsWith("/noticias.json") ? "[]" : "{}";
        return new Response(blank, { headers: { "Content-Type": "application/json; charset=utf-8" } });
      }
    })());
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith((async () => {
      try {
        // HTML da página sempre usa a rede, evitando versões antigas do navegador.
        const response = await fetch(request, {cache:"no-store"});
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
  const appHome = new URL("index.html#radar", ROOT).href;
  const action = event.action || "read";
  const requested = action === "radar" ? appHome : event.notification.data?.url || appHome;
  let target = appHome;
  try {
    const parsed = new URL(requested, ROOT);
    if (["https:", "http:"].includes(parsed.protocol)) target = parsed.href;
  } catch {}
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({type:"window",includeUncontrolled:true});
    // Se já existe uma janela mostrando o destino exato, colocá-la na frente.
    for (const client of windows) {
      if (client.url === target) {
        await client.focus();
        return;
      }
    }
    // Ações externas abrem a matéria; o atalho Radar abre o próprio aplicativo.
    try {
      const opened = await self.clients.openWindow(target);
      if (opened) return;
    } catch (error) {
      console.warn("Falha ao abrir destino da notificação",error);
    }
    for (const client of windows) {
      if (client.url.startsWith(ROOT.href)) {
        if (client.navigate) await client.navigate(appHome);
        await client.focus();
        return;
      }
    }
    await self.clients.openWindow(appHome);
  })());
});
