const CACHE_NAME = "quiz-duel-v48";

// Bestanden die altijd vers gehaald moeten worden bij internet (app shell).
// Bij offline: fallback naar cache. Zonder deze regel zie je in een iOS PWA
// pas na meerdere launches een nieuwe versie.
const NETWORK_FIRST_EXT = [".html", ".css", ".js"];
function isAppShell(url) {
  if (url.pathname === "/" || url.pathname.endsWith("/")) return true;
  return NETWORK_FIRST_EXT.some((ext) => url.pathname.endsWith(ext));
}

const ASSETS = [
  "./",
  "./index.html",
  "./style.css",
  "./script.js",
  "./manifest.json",
  "./icons/icon-180.png",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./games/index.json",
  "./games/pakket-1.json",
  "./games/pakket-2.json",
  "./games/pakket-3.json",
  "./games/pakket-4.json",
  "./games/pakket-5.json",
  "./games/stellingen-1.json",
  "./games/stellingen-2.json",
  "./games/stellingen-3.json",
  "./games/pakket-6.json",
  "./games/pakket-7.json",
  "./games/pakket-8.json",
  "./games/pakket-9.json",
  "./games/open-1.json",
  "./games/open-2.json",
  "./games/open-3.json",
  "./games/pakket-10.json",
  "./games/pakket-11.json",
  "./games/open-hints-1.json",
  "./games/open-hints-2.json",
  "./games/open-hints-3.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(
        ASSETS.map((url) =>
          cache.add(url).catch((err) =>
            console.warn(`[sw] kon niet cachen: ${url}`, err)
          )
        )
      )
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

// App shell (HTML/CSS/JS): network-first met cache-fallback.
// Overig (JSON pakketten, icons, manifest): stale-while-revalidate.
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  const url = new URL(event.request.url);
  if (url.origin !== location.origin) return;

  const networkFirst = event.request.mode === "navigate" || isAppShell(url);

  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE_NAME);

      if (networkFirst) {
        try {
          const fresh = await fetch(event.request);
          if (fresh && fresh.ok) cache.put(event.request, fresh.clone());
          return fresh;
        } catch (_) {
          const cached = await cache.match(event.request);
          if (cached) return cached;
          if (event.request.mode === "navigate") {
            const shell = await cache.match("./index.html");
            if (shell) return shell;
          }
          return new Response("Offline", { status: 503 });
        }
      }

      const cached = await cache.match(event.request);
      const networkUpdate = fetch(event.request)
        .then((response) => {
          if (response.ok) cache.put(event.request, response.clone());
          return response;
        })
        .catch(() => null);

      if (cached) {
        event.waitUntil(networkUpdate);
        return cached;
      }

      const fresh = await networkUpdate;
      if (fresh) return fresh;
      return new Response("Offline", { status: 503 });
    })()
  );
});
