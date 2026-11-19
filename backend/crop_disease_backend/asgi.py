"""ASGI 入口：异步服务器（uvicorn / daphne 等）从这里取 application 对象。

⚠️ `DJANGO_SETTINGS_MODULE` 必须在 `get_asgi_application()` **之前**设好 ——
   那一步会立即加载 settings，顺序颠倒时报错落在 Django 内部，根因很难看出来。
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')

application = get_asgi_application()