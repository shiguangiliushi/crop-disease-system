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
        # 第 107 批：**真正的启动预热**
        # ------------------------------------------------------------------
        # 上面那句 `import ai_service` 只导入模块，**不加载模型** ——
        # 模型是在第一次 `get_ai_service()`（也就是第一个识别请求）时才加载的。
        # 实测冷启动代价：加载 5.5s + **第一次真实推理 21s**，之后每次 0.8s。
        # 也就是说第一个上传图片的用户要盯着转圈 20 多秒，很容易以为"识别坏了"。
        #
        # 这里调一次完整的假图推理把它提前到启动阶段。
        #
        # 三个刻意的约束：
        #   1. **失败绝不影响启动**（`warm_up()` 内部自己吞异常）——
        #      识别是核心功能，但它不该拥有"否决服务启动"的权力；
        #   2. 可以用 `AI_WARMUP_ON_STARTUP=False` 关掉
        #      （例如跑测试、或在极慢的机器上不想拖长启动）；
        #   3. 只在 `ready()` 里做一次 —— `apps.ready()` 在 autoreload 的
        #      子进程里也会执行，而处理请求的正是子进程。
        try:
            from .ai_service import warm_up
            warm_up()
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning('AI 预热调度失败（不影响启动）：%s', e)