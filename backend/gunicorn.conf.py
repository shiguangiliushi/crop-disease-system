# ============================================================================
# Gunicorn 生产配置（第 94 批）
# ----------------------------------------------------------------------------
# 用法：
#   gunicorn -c gunicorn.conf.py crop_disease_backend.wsgi:application
#
# 为什么需要它：`runserver` 只适合开发 —— 单进程、无超时、无优雅重启，
# 而且启动时会打印"不要在生产使用"的安全警告。在这之前项目里**没有任何生产启动方式**。
#
# 调参要点（都是踩过的坑）：
#   · **worker 数与 CPU 有关，不是越多越好**：每个 worker 都会**各加载一份 YOLO 模型**
#     （约 6MB 权重 + torch 运行时，实测单进程常驻内存 ~700MB）。所以这里默认 2 个，
#     而不是 `2*CPU+1` —— 那样 8 核机器会吃 8 份模型，直接把内存打满。
#   · **timeout 要留够**：识别一张大图在 CPU 上可能跑十几秒，默认 30s 会中途杀掉 worker，
#     表现为前端"识别服务暂时不可用（503）"。这里给 120s。
#   · **preload_app=False**：预加载虽然省内存，但模型会在 fork 时继承一份句柄，
#     与 ultralytics 的懒加载混用时行为不好预测；宁可用显式 worker 数控制内存。
#   · 访问日志与错误日志分开，便于排查。
# ============================================================================
import multiprocessing  # noqa: F401  （保留：想把 workers 调成 CPU 相关时用得上）
import os

# ── 绑定 ────────────────────────────────────────────────────────────────────
# 默认只监听本机：正经部署应当由 Nginx 反代到它，而不是直接对外暴露。
bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:8000')

# ── 进程 ────────────────────────────────────────────────────────────────────
workers = int(os.environ.get('GUNICORN_WORKERS', 2))
worker_class = 'sync'
threads = int(os.environ.get('GUNICORN_THREADS', 1))
# 识别是 CPU 密集且同步的：开太多并发只会互相抢 CPU，把每张图的耗时拖长。
worker_connections = 100

# ── 超时与重启 ──────────────────────────────────────────────────────────────
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 120))  # 见文件头说明：识别很慢
graceful_timeout = 30
keepalive = 5

# 定期重启 worker：防止长跑进程的内存缓慢增长（ultralytics/torch 会缓存）
max_requests = int(os.environ.get('GUNICORN_MAX_REQUESTS', 1000))
max_requests_jitter = 100

# ── 日志 ────────────────────────────────────────────────────────────────────
accesslog = os.environ.get('GUNICORN_ACCESS_LOG', '-')   # '-' = stdout
errorlog = os.environ.get('GUNICORN_ERROR_LOG', '-')     # '-' = stderr（容器里就该这样）
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%({x-forwarded-for}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" %(D)sµs'

# ── 其它 ────────────────────────────────────────────────────────────────────
proc_name = 'crop-disease-backend'
# 让 gunicorn 尊重反代传来的 X-Forwarded-* （配合 settings 的 SECURE_PROXY_SSL_HEADER）
forwarded_allow_ips = os.environ.get('GUNICORN_FORWARDED_ALLOW_IPS', '127.0.0.1')
