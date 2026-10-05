"""
健康检查（第 94 批）

==================================================================
为什么需要它
==================================================================
在这之前，判断"服务到底活着没"只能靠请求一个业务接口 —— 而那需要登录、会碰业务数据、
还可能因为某条数据有问题而失败（于是"服务正常"被误报成"挂了"）。
反向的问题更麻烦：服务起来了但**数据库连不上 / 迁移没跑 / 模型文件丢了**，
业务接口才开始一个个 500，而在那之前没有任何信号。

    GET /api/health/              → 轻量：进程活着 + 数据库 + 缓存（约 1~2 次查询）
    GET /api/health/?deep=true    → 深度：额外检查迁移是否应用、模型文件是否就位

约定：
  · **不需要认证**：探针没法登录；
  · 健康返回 **200**，不健康返回 **503**（这样负载均衡/监控不用解析 body）；
  · body 里逐项列出每个检查的结果与耗时 —— 排查时一眼能看出是哪一环慢/坏；
  · 不泄露敏感信息：不回显数据库密码、密钥、完整路径（只给相对路径与文件名）。

为什么深度检查要单独开关：`?deep=true` 会碰迁移表与文件系统，
不适合每秒被探针打一次；默认的轻量版足够回答"要不要把这个实例摘掉"。
"""
import logging
import time

from django.conf import settings
from django.db import connection
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

#: 进程启动时刻（用于 uptime；模块导入即记录）
_PROCESS_STARTED_AT = time.time()


def _check_database():
    """数据库连通性 + 往返耗时"""
    started = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        return True, round((time.perf_counter() - started) * 1000, 1), ''
    except Exception as exc:  # noqa: BLE001
        return False, round((time.perf_counter() - started) * 1000, 1), str(exc)[:200]


def _check_cache():
    """
    缓存读写。

    为什么值得单列：限流计数器就存在缓存里。缓存坏掉时界面看着一切正常，
    但**限流会静默失效**（每个请求都算"第一次"），属于看不见的降级。
    另外 LocMemCache 不跨进程 —— gunicorn 多 worker 时每个进程各算一份计数，
    限额实际被放大 N 倍（见第 97 批的 settings.CACHES 说明）。
    """
    started = time.perf_counter()
    try:
        from django.core.cache import cache
        cache.set('health:probe', 'ok', 10)
        ok = cache.get('health:probe') == 'ok'
        return ok, round((time.perf_counter() - started) * 1000, 1), '' if ok else '缓存读写不一致'
    except Exception as exc:  # noqa: BLE001
        return False, round((time.perf_counter() - started) * 1000, 1), str(exc)[:200]


def _check_migrations():
    """是否有未应用的迁移（部署时最常忘的一步）"""
    try:
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        return (not pending), f'{len(pending)} 个未应用' if pending else 'up-to-date'
    except Exception as exc:  # noqa: BLE001
        return False, f'检查失败：{str(exc)[:120]}'


def _check_model():
    """识别模型权重是否存在（缺了会让识别接口 503，但服务本身还活着）"""
    from pathlib import Path
    base = Path(settings.BASE_DIR)
    for rel in ('api/newmodels/best.pt', 'api/models/best.pt', 'yolov8n.pt'):
        path = base / rel
        if path.exists():
            return True, f'{rel}（{path.stat().st_size / 1024 / 1024:.1f} MB）'
    return False, '未找到权重文件'


class HealthView(APIView):
    """健康检查（匿名可访问）"""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # 探针不带头；顺带避免 Token 查询

    #: ⚠️ **必须显式清空限流类**（第 97 批实测发现的）
    #: DRF 的限流计数存在 cache 里。如果保留了默认限流（DRF 默认按 settings 的
    #: DEFAULT_THROTTLE_CLASSES 走），那么**缓存一挂，健康检查自己先 500** ——
    #: 恰好是最需要它报出"缓存不可用"的时候。实测：配了一个连不上的 Redis，
    #: `/api/health/` 抛 TimeoutError 而不是返回 `cache.ok=false`。
    #: 健康检查本来也不该被限流（探针是机器，固定频率）。
    throttle_classes = []

    def get(self, request):
        deep = str(request.query_params.get('deep', '')).lower() in ('1', 'true', 'yes')
        started = time.perf_counter()

        checks = {}
        healthy = True

        db_ok, db_ms, db_err = _check_database()
        checks['database'] = {'ok': db_ok, 'ms': db_ms}
        if db_err:
            checks['database']['error'] = db_err
        healthy = healthy and db_ok

        cache_ok, cache_ms, cache_err = _check_cache()
        cache_shared = getattr(settings, 'CACHE_IS_SHARED', None)
        checks['cache'] = {
            'ok': cache_ok,
            'ms': cache_ms,
            'backend': settings.CACHES['default']['BACKEND'].rsplit('.', 1)[-1],
            # 第 97 批：跨进程共享与否直接决定限流是否真的生效（见 settings 里的说明）
            'shared_across_processes': cache_shared,
        }
        if cache_err:
            checks['cache']['error'] = cache_err
        # 缓存坏掉不算"服务不可用"（业务仍能跑，只是限流不准），所以不参与 healthy 判定
        # —— 但它会以 degraded 的形式出现在 body 里，监控应当据此告警。
        # 第 97 批新增：生产下**不共享**的缓存同样降级（多 worker 时限流失效）。
        cache_degraded = (not cache_ok) or (not settings.DEBUG and cache_shared is False)

        if deep:
            mig_ok, mig_detail = _check_migrations()
            checks['migrations'] = {'ok': mig_ok, 'detail': mig_detail}
            healthy = healthy and mig_ok

            model_ok, model_detail = _check_model()
            checks['model'] = {'ok': model_ok, 'detail': model_detail}
            # 模型缺失不判 503：服务是活的，只有识别这一条链路不可用
            # （healthy 不参与，但 body 里明确标出来）

        payload = {
            'status': 'ok' if healthy else 'unhealthy',
            'degraded': bool(
                healthy and (
                    cache_degraded
                    or (deep and not checks['model']['ok'])
                )
            ),
            'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'uptime_seconds': round(time.time() - _PROCESS_STARTED_AT, 1),
            'debug': settings.DEBUG,
            'checks': checks,
            'took_ms': round((time.perf_counter() - started) * 1000, 1),
        }

        if not healthy:
            logger.warning('健康检查未通过：%s', checks)

        return Response(payload, status=200 if healthy else 503)
