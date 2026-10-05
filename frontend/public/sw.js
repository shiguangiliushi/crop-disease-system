/* eslint-disable no-restricted-globals */
/**
 * Service Worker：应用外壳离线缓存（第 51 批）
 * ------------------------------------------------------------------
 * 目标：**断网也能打开页面**（圆了第 50 批留下的那个缺口）。
 *
 * 策略（刻意保守）：
 *   · 导航请求（HTML）：**网络优先**，失败时回退到缓存的 index.html —— 保证联网时永远拿最新页面；
 *   · `/assets/*`（Vite 产物带内容哈希，内容不会变）：**缓存优先**，省流量又快；
 *   · 其它同源静态资源（manifest、图标）：缓存优先 + 后台更新；
 *   · **跨源或 /api 请求一律不缓存、直接走网络** —— 用户识别记录、通知这类数据
 *     缓存下来既过时又有隐私风险，绝不能进 Cache Storage。
 *
 * 版本号变了会在 activate 阶段清理旧缓存，避免旧产物一直占空间。
 */
const VERSION = 'v1';
const SHELL_CACHE = `crop-shell-${VERSION}`;
const ASSET_CACHE = `crop-assets-${VERSION}`;

//: 预缓存：应用外壳最小集合（hashed assets 首次访问时再运行时缓存）
const PRECACHE = ['/', '/index.html', '/manifest.webmanifest', '/icon-192.png', '/favicon.ico'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      // 单个资源失败不该让整个安装失败（例如 favicon 缺失）
      await Promise.all(
        PRECACHE.map((url) => cache.add(new Request(url, { cache: 'reload' })).catch(() => null)),
      );
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((key) => key.startsWith('crop-') && key !== SHELL_CACHE && key !== ASSET_CACHE)
          .map((key) => caches.delete(key)),
      );
      await self.clients.claim();
    })(),
  );
});

/** 是否该由 SW 接管（同源静态资源才管） */
function isCacheable(request, url) {
  if (request.method !== 'GET') return false;
  if (url.origin !== self.location.origin) return false;         // 跨源（含后端 8000）不碰
  if (url.pathname.startsWith('/api')) return false;             // 接口数据不缓存
  return true;
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (!isCacheable(request, url)) return; // 交给浏览器默认行为

  // ① 页面导航：网络优先，断网回退到缓存的外壳
  if (request.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          const fresh = await fetch(request);
          const cache = await caches.open(SHELL_CACHE);
          cache.put('/index.html', fresh.clone());
          return fresh;
        } catch (error) {
          const cache = await caches.open(SHELL_CACHE);
          const cached = (await cache.match('/index.html')) || (await cache.match('/'));
          if (cached) return cached;
          throw error;
        }
      })(),
    );
    return;
  }

  // ② 带内容哈希的构建产物：缓存优先
  const isHashedAsset = url.pathname.startsWith('/assets/');

  event.respondWith(
    (async () => {
      const cacheName = isHashedAsset ? ASSET_CACHE : SHELL_CACHE;
      const cache = await caches.open(cacheName);
      const cached = await cache.match(request);
      if (cached && isHashedAsset) return cached;

      try {
        const fresh = await fetch(request);
        if (fresh && fresh.status === 200 && fresh.type === 'basic') {
          cache.put(request, fresh.clone());
        }
        return fresh;
      } catch (error) {
        if (cached) return cached;
        throw error;
      }
    })(),
  );
});

// 允许页面主动要求立即接管（新版本部署后）
self.addEventListener('message', (event) => {
  if (event.data === 'skip-waiting') self.skipWaiting();
});
