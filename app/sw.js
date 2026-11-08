// Service worker: offline-first app shell, network-first data with cached fallback.
const VERSION = "mdr-v1.0.0";
const SHELL_CACHE = `${VERSION}-shell`;
const DATA_CACHE = "mdr-data"; // survives app updates so offline data is never lost

const SHELL = [
  "./",
  "index.html",
  "css/styles.css",
  "js/main.js",
  "js/data.js",
  "js/format.js",
  "js/ui.js",
  "js/csv.js",
  "js/watchlist.js",
  "js/views/dashboard.js",
  "js/views/deals.js",
  "js/views/detail.js",
  "js/views/briefing.js",
  "js/views/watchlist.js",
  "js/views/about.js",
  "vendor/chart.umd.js",
  "manifest.webmanifest",
  "icons/favicon.svg",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL_CACHE && k !== DATA_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

/** Network first; on failure serve the saved copy, marked with an "offline" header. */
async function networkFirstData(request) {
  const cache = await caches.open(DATA_CACHE);
  const key = request.url.split("?")[0];
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(key, response.clone());
    return response;
  } catch {
    const cached = await cache.match(key);
    if (!cached) throw new Error("offline and not cached");
    const headers = new Headers(cached.headers);
    headers.set("x-mdr-offline", "1");
    return new Response(await cached.blob(), { status: 200, headers });
  }
}

/** Cache first for the versioned app shell, refreshing in the background. */
async function staleWhileRevalidate(request) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(request, { ignoreSearch: true });
  const network = fetch(request)
    .then((response) => {
      if (response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => cached);
  return cached || network;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.includes("/data/")) {
    event.respondWith(networkFirstData(request));
  } else if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("index.html")));
  } else {
    event.respondWith(staleWhileRevalidate(request));
  }
});
