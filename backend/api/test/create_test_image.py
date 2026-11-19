"""手工造一张 100x100 的白色图并存成 `test.jpg`，供识别接口试着上传用。

⚠️ 路径相对**当前工作目录**、也不清理产物：它不是 pytest 用例，跑一次就会在
当前目录里留下 test.jpg；把它接进 CI 会把仓库搞脏。
"""
from PIL import Image

img = Image.new('RGB', (100, 100), color='white')
img.save('test.jpg', 'JPEG')
