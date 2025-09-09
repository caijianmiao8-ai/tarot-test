/* 轻量 SW：跳过等待 + 最简拦截（避免 iOS 问题，不做 aggressive 缓存） */
self.addEventListener('install', e => { self.skipWaiting(); });
self.addEventListener('activate', e => { clients.claim(); });

self.addEventListener('fetch', event => {
  // 对静态资源可做温和缓存；HTML 直连网络，避免旧页面卡住
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  const isHTML = req.headers.get('accept')?.includes('text/html');
  if (isHTML) return; // 不拦截 HTML

  event.respondWith(
    caches.open('cosmos-assets-v1').then(async cache => {
      const hit = await cache.match(req);
      const fetchPromise = fetch(req).then(res => {
        try { cache.put(req, res.clone()); } catch(e) {}
        return res;
      }).catch(()=>hit);
      return hit || fetchPromise;
    })
  );
});
