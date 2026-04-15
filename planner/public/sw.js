/* Minimal offline shell.
 *
 * IMPORTANT:
 * - Do NOT "cache-first" HTML forever. That makes UI updates (e.g. new buttons) appear "missing" in production
 *   until users manually clear site data.
 * - Use network-first for the app shell, falling back to cache only when offline.
 */
const CACHE = "threads-planner-v12";
const ASSETS = ["/", "/index.html", "/manifest.json"];

function isAppShellGet(req) {
  if (req.method !== "GET") return false;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return false;
  const p = url.pathname;
  return p === "/" || p === "/index.html";
}

async function pruneOldCaches() {
  const keys = await caches.keys();
  await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      await pruneOldCaches();
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  // Never cache API responses (they can include transient errors and stale data).
  const url = new URL(req.url);
  if (url.origin === self.location.origin && url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(req));
    return;
  }

  // App shell: network-first, cache fallback (offline).
  if (isAppShellGet(req)) {
    event.respondWith(
      (async () => {
        try {
          const fresh = await fetch(req);
          // Opportunistically refresh cached shell for offline fallback.
          const copy = fresh.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy)).catch(() => {});
          return fresh;
        } catch {
          const cached = await caches.match(req);
          if (cached) return cached;
          // Last resort: try the other common entry path.
          const alt = req.url.endsWith("index.html") ? caches.match("/") : caches.match("/index.html");
          return (await alt) || fetch(req);
        }
      })(),
    );
    return;
  }

  // Other GET assets: stale-while-revalidate-ish (cache-first, refresh in background).
  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy)).catch(() => {});
          return res;
        })
        .catch(() => null);

      if (cached) {
        void network;
        return cached;
      }
      return network.then((res) => res || fetch(req));
    }),
  );
});
