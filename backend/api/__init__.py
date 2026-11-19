"""`api` 应用的包入口：只声明 `default_app_config`。

⚠️ 这里只允许出现这一个字符串赋值 —— 包 `__init__` 在 app registry 就绪**之前**执行，
一旦导入模型或应用内其它模块，就会直接触发循环导入。
"""
# crop-disease-system/backend/api/__init__.py
# 注意：不要在这里导入任何模型，这会导致循环导入问题
default_app_config = 'api.apps.ApiConfig'