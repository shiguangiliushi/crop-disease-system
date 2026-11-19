"""WSGI 入口：gunicorn / uwsgi 等同步服务器通过 APPLICATION 加载本项目。

⚠️ `DJANGO_SETTINGS_MODULE` 必须在 `get_wsgi_application()` **之前**设好 ——
   那一步会立即加载 settings，漏设时报错指向 Django 内部而不是本文件。
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')

application = get_wsgi_application()