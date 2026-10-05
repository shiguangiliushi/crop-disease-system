# crop-disease-system/backend/api/apps.py

from django.apps import AppConfig  # 导入Django应用配置基类


class ApiConfig(AppConfig):  # 定义API应用配置类，继承自AppConfig
    default_auto_field = 'django.db.models.BigAutoField'  # 设置默认主键字段类型
    name = 'api'  # 设置应用名称

    def ready(self):  # 定义应用就绪方法
        """
        在应用完全加载后执行初始化代码
        注意：这里只执行必要的初始化，不直接导入模型
        """
        # 延迟导入，避免循环导入问题
        try:  # 尝试导入信号处理程序
            # 尝试导入信号处理程序（如果存在）
            import api.signals  # noqa  # 导入信号处理模块，noqa表示忽略flake8检查
        except ImportError:  # 捕获导入异常
            # 如果signals.py不存在，忽略错误
            pass  # 忽略异常

        # 确保admin.py中的模型注册代码会被执行
        try:  # 尝试导入admin配置
            import api.admin  # noqa  # 导入admin配置模块，noqa表示忽略flake8检查
        except ImportError as e:  # 捕获导入异常
            # 如果admin.py导入失败，记录错误但继续
            import logging  # 导入日志模块
            logger = logging.getLogger(__name__)  # 获取日志记录器
            logger.warning(f"Failed to import api.admin: {e}")  # 记录警告信息

        # We import the AI service here to ensure the model is loaded once on startup.
        try:  # 尝试导入AI服务
            from . import ai_service  # noqa  # 导入AI服务模块，noqa表示忽略flake8检查
        except ImportError as e:  # 捕获导入异常
            # 如果AI服务导入失败，记录错误但继续
            import logging  # 导入日志模块
            logger = logging.getLogger(__name__)  # 获取日志记录器
            logger.warning(f"Failed to import ai_service: {e}")  # 记录警告信息

        # ------------------------------------------------------------------
        # 第 107 批：启动预热（第 113 批改为**后台线程**）
        # ------------------------------------------------------------------
        # 上面那句 `import ai_service` 只导入模块，**不加载模型** ——
        # 模型是在第一次 `get_ai_service()`（也就是第一个识别请求）时才加载的。
        # 实测冷启动代价：加载 5.5s + **第一次真实推理 21s**，之后每次 0.8s。
        # 也就是说第一个上传图片的用户要盯着转圈 20 多秒，很容易以为"识别坏了"。
        #
        # ⚠️⚠️ 第 113 批：**原来这里是同步调用 `warm_up()`，那是错的**。
        #
        # `ready()` 在**服务器开始监听端口之前**执行，所以同步预热会：
        #   · 让服务在这 30 秒里**完全不接受连接**（实测：进程在跑、端口没监听、
        #     浏览器直接"无法连接"）—— 对使用者来说比"第一个请求慢"更糟，
        #     因为看起来像**服务没起来**；
        #   · 而且在 `runserver --noreload` 下它**真的卡住过**：日志停在
        #     `results[0].plot(...)` 那一行、CPU 0%、4 分钟不监听端口。
        #     同样的代码手动调用只要 30 秒就正常返回 —— 说明它与 Django
        #     启动阶段相互影响。预热不该有"让服务起不来"的权力。
        #
        # 改成**守护线程**：启动立即返回、端口马上监听，预热在后台跑。
        #   · 用户在这 30 秒内访问其它页面完全正常；
        #   · 如果这期间就有人上传图片，他会和预热**争同一把锁**（见 ai_service
        #     里的 `_WARMUP_LOCK`），等预热完再用已加载的模型 —— 不会重复加载；
        #   · `daemon=True`：进程退出时不会因为预热线程还在跑而被拖住。
        #
        # 三个仍然保留的约束：
        #   1. **失败绝不影响启动**（`warm_up()` 内部自己吞异常）；
        #   2. 可以用 `AI_WARMUP_ON_STARTUP=False` 关掉；
        #   3. 只在 `ready()` 里调度一次。
        try:
            import threading

            from django.conf import settings

            if getattr(settings, 'AI_WARMUP_ON_STARTUP', True):
                from .ai_service import warm_up

                threading.Thread(
                    target=warm_up,
                    name='ai-warmup',
                    daemon=True,
                ).start()
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning('AI 预热调度失败（不影响启动）：%s', e)