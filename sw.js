// sw.js — 轻量缓存静态资源，离线兜底页面可按需扩展
const CACHE_NAME = 'ruoshui-static-v1';
const STATIC_PATTERNS = [
  '/static/CSS/bootstrap.min.css',
  '/static/CSS/all.min.css',
  '/static/images/',    // 你的图片目录
  '/static/icons/',     // PWA 图标
  '/static/',           // 其他静态资源（可按需缩小范围）
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE_NAME));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.map(k => (k !== CACHE_NAME ? caches.delete(k) : null)))
    ).then(() => self.clients.claim())
  );
});


// 缓存优先（静态资源）；接口请求一律放行网络，不进入缓存
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  const isStatic = STATIC_PATTERNS.some(p => url.pathname.startsWith(p));
  if (isStatic) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE_NAME);
      const cached = await cache.match(request);
      if (cached) return cached;
      try {
        const resp = await fetch(request);
        if (resp.ok) cache.put(request, resp.clone());
        return resp;
      } catch (e) {
        return cached || Response.error();
      }
    })());
  }
  // 非静态资源：默认走网络
});
