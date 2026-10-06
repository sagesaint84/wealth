// Wealth Service Worker - MDN Progressive Web App Standard
const CACHE_NAME = "wealth-cache-v1.3.0";
const PRECACHE_RESOURCES = [
  "/",
  "/dashboard",
  "/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/apple-touch-icon.png"
];

// 1. 서비스 워커 설치: 필수 리소스 사전 캐싱 (오프라인 지원)
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_RESOURCES))
      .then(() => self.skipWaiting())
      .catch((err) => {
        console.warn("[PWA SW] Pre-cache failed, continuing without precache:", err);
        return self.skipWaiting();
      })
  );
});

// 2. 서비스 워커 활성화: 이전 버전 캐시 정리
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

function isWealthCacheEligible(request) {
  const url = new URL(request.url);
  return request.method === "GET" &&
    (url.protocol === "http:" || url.protocol === "https:") &&
    url.origin === self.location.origin &&
    !url.pathname.startsWith("/api/") &&
    !url.pathname.endsWith(".js") &&
    !url.pathname.endsWith(".css");
}

async function offlineResponse(request) {
  const cachedResponse = await caches.match(request);
  if (cachedResponse) return cachedResponse;
  if (request.mode === "navigate") {
    const fallback = await caches.match("/");
    if (fallback) return fallback;
    const fallbackDash = await caches.match("/dashboard");
    if (fallbackDash) return fallbackDash;
  }
  return new Response("오프라인 상태입니다. 네트워크 연결을 확인하세요.", {
    status: 503,
    statusText: "Service Unavailable",
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}

// 3. 네트워크 요청 처리: 캐시 대상만 Network-first 전략 적용
self.addEventListener("fetch", (event) => {
  if (!isWealthCacheEligible(event.request)) {
    event.respondWith(fetch(event.request));
    return;
  }

  const network = fetch(event.request);
  // Register synchronously. Returning put's promise keeps the entire write in
  // the event lifetime; a write rejection remains visible to waitUntil without
  // rejecting the independent successful network response.
  event.waitUntil(network.then((response) => {
    if (response && response.status === 200) {
      const clone = response.clone();
      return caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
    }
  }, () => undefined)); // Network failure needs no cache update.

  event.respondWith(network.then(
    (response) => response,
    () => offlineResponse(event.request)
  ));
});
