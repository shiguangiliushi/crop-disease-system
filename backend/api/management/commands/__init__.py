"""`manage.py` 自定义命令的落脚点（Django 按**文件名**发现命令）。

⚠️ 文件名就是命令名：`backup_verify.py` → `manage.py backup_verify`。
改名等于改命令名，文档、定时任务与 `docs/` 里的示例会一起失效。
"""