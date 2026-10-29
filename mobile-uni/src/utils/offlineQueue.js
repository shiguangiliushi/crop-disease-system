/**
 * 离线补传队列（第 239 批）
 * ============================================================================
 * 断网/服务不可用时，把"这张图没传上去"记下来，回到识别页且网络恢复后自动补传。
 *
 * ## 与 H5 的差别（必须说清）
 *
 * H5 版（`mobile/src/utils/offlineSync.js`）用 IndexedDB 存 Blob，**刷新/关页面后还在**。
 * uni-app 三端没有统一的 Blob 存储：
 *   · App/小程序：图片是临时文件路径，重启后可能失效；
 *   · H5：选图得到的是 `blob:` URL，**刷新就失效**。
 * 所以这里只承诺"**本次运行期间**能补传"：路径失效时直接丢弃并提示，
 * 不假装"跨会话持久化"（那需要 App 端 `saveFile` / 小程序 `getFileSystemManager`，
 * 每个平台一套，等真机验证后再补）。
 *
 * 存储结构：[{ id, path, createdAt }]
 */
const STORAGE_KEY = 'uni_offline_queue'

function read() {
  try {
    const value = uni.getStorageSync(STORAGE_KEY)
    return Array.isArray(value) ? value : []
  } catch (error) {
    return []
  }
}

function write(items) {
  try {
    uni.setStorageSync(STORAGE_KEY, items)
  } catch (error) {
    console.warn('[offline] 保存队列失败', error)
  }
}

export function pending() {
  return read()
}

export function enqueue(path) {
  if (!path) return pending()
  const items = read()
  // 同一张图重复失败不重复入队
  if (items.some((item) => item.path === path)) return items
  items.push({ id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, path, createdAt: Date.now() })
  write(items)
  return items
}

export function dequeue(id) {
  const items = read().filter((item) => item.id !== id)
  write(items)
  return items
}

export function clearQueue() {
  write([])
}

/**
 * 逐条补传：`send(path)` 成功即出队，失败保留。
 * @returns {Promise<{ok: number, failed: number}>}
 */
export async function syncAll(send) {
  const items = read()
  let ok = 0
  let failed = 0
  for (const item of items) {
    try {
      await send(item.path)
      dequeue(item.id)
      ok += 1
    } catch (error) {
      failed += 1
    }
  }
  return { ok, failed }
}
