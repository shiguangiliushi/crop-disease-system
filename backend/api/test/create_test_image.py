from PIL import Image

# 创建一个100x100像素的白色图像
img = Image.new('RGB', (100, 100), color='white')
# 保存为JPEG格式
img.save('test.jpg', 'JPEG')
