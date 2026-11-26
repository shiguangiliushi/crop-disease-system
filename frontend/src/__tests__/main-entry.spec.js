/**
 * 入口文件的守护用例（第 429 批）
 *
 * ## 为什么给 `main.js` 写静态扫描
 *
 * 生产环境控制台里一直有这段：
 *
 *     WebSocket connection to 'wss://<域名>/ws' failed
 *     Max reconnection attempts reached, giving up
 *
 * 根因是入口里留了一段"生产环境连 WebSocket"的代码 —— 而**后端从来没有 WS 服务**：
 * `asgi.py` 是 `get_asgi_application()`、gunicorn 走 WSGI、依赖里没有 channels、
 * nginx 也没有 `/ws` 转发。客户端连 `onmessage` 都没有，就算连上也什么都不做。
 *
 * 代价是每次打开生产站点白试 6 次、控制台 6 条报错 + 一条资源加载失败，
 * 排查别的问题时全是噪音。整段已删，这条用例防它被"照着旧代码"加回来。
 *
 * 真要做实时推送，顺序是：channels + ASGI 服务 + nginx `/ws` 转发 + 客户端 onmessage，
 * 四件缺一不可 —— 先有服务端，再接客户端。
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const HERE = dirname(fileURLToPath(import.meta.url));
const MAIN = readFileSync(resolve(HERE, '../main.js'), 'utf8');

describe('入口不连 WebSocket（第 429 批）', () => {
  it('没有 new WebSocket，也没有拼 /ws 地址的代码', () => {
    expect(MAIN).not.toMatch(/new WebSocket\(/);
    // 注释里会引用 `wss://<域名>/ws` 与 `/ws` 这两个字样（方便按日志搜到），所以只查"代码形态"
    expect(MAIN).not.toMatch(/window\.location\.host\}\s*\/ws/);
  });

  it('没有遗留的重连机制', () => {
    expect(MAIN).not.toContain('setupWebSocket');
    expect(MAIN).not.toContain('__websocket_initialized__');
    // 只查"代码"，不查注释：上面那段说明里刻意保留了当年的报错原文，方便按日志搜到这里
    expect(MAIN).not.toMatch(/console\.warn\(\s*'Max reconnection/);
  });
});
