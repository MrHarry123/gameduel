const CACHE_NAME = "quiz-duel-v40";

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

// Stale-while-revalidate: serveer uit cache, ververs op de achtergrond.
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  const url = new URL(event.request.url);
  if (url.origin !== location.origin) return;

  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE_NAME);
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

      if (event.request.mode === "navigate") {
        return cache.match("./index.html");
      }
      return new Response("Offline", { status: 503 });
    })()
  );
});
