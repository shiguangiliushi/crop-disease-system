#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
托管构建产物（dist）并支持 SPA 回退（第 51 批）

为什么需要它：
  · `python -m http.server` 对 `/login`、`/pests` 这种前端路由会直接 404
    —— 单页应用必须把"找不到文件"的请求回退到 index.html（等价于 nginx 的 try_files）；
  · Service Worker 的"离线外壳"能力必须**在构建产物上**验证（开发服务器的模块 URL 是动态的），
    所以需要一个能跑 dist 的本地服务器。

用法：
    python docs/tools/serve_spa.py                 # 默认 dist 目录，端口 8099
    python docs/tools/serve_spa.py --port 9000 --dir frontend/dist
"""
import argparse
import http.server
import os
import socketserver
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SpaHandler(http.server.SimpleHTTPRequestHandler):
    """静态文件优先；找不到且不是 API/资源请求时回退到 index.html"""

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def send_head(self):
        path = self.translate_path(self.path)
        # 目录或已存在的文件：按常规处理
        if os.path.isdir(path):
            index = os.path.join(path, 'index.html')
            if os.path.exists(index):
                return super().send_head()
        if os.path.exists(path):
            return super().send_head()

        # 静态资源缺失要如实 404（否则前端加载不到 chunk 却拿到 HTML，报错更难看）
        if self.path.startswith('/assets/') or self.path.startswith('/api/'):
            self.send_error(404, 'File not found')
            return None

        # 其余（前端路由）回退到 index.html
        self.path = '/index.html'
        return super().send_head()

    def log_message(self, fmt, *args):  # 静音，避免刷屏
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8099)
    parser.add_argument('--dir', default=os.path.join(ROOT, 'frontend', 'dist'))
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        print(f'目录不存在：{args.dir}（先执行 npm run build-only）')
        return 1

    handler = lambda *a, **kw: SpaHandler(*a, directory=args.dir, **kw)  # noqa: E731
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(('127.0.0.1', args.port), handler) as httpd:
        print(f'托管 {args.dir} → http://127.0.0.1:{args.port}/ （SPA 回退已开启）')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n已停止')
    return 0


if __name__ == '__main__':
    sys.exit(main())
