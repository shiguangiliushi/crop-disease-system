"""Django 管理命令包（`api.management`）。

⚠️ 这里与 `commands/` 的两个 `__init__.py` 是 `manage.py` 发现自定义命令的前提：
Django 是按 `<app>/management/commands/` 的路径去 import 命令模块的，删掉它们
不会是"少个空文件"这么简单，而是所有 `manage.py <命令>` 一起失效。
"""