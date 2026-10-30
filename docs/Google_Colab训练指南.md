# Google Colab 训练指南

本地 CPU 跑不动 YOLOv8 训练，所以最终训练是在 Google Colab 上用免费 GPU 完成的。以下是复现步骤。

## 📋 使用步骤

### 1. 访问Google Colab

- 打开浏览器，访问 [Google Colab](https://colab.research.google.com/)
- 使用您的Google账号登录

### 2. 创建新的Notebook

- 点击 "新建笔记本"
- 将 `colab_training.ipynb` 文件的内容复制到Colab中

### 3. 准备数据集

- 将您的所有图片文件夹压缩成一个zip文件
- 确保zip文件包含所有38个类别的文件夹

### 4. 开始训练

1. **运行环境设置单元格** - 安装必要的包
2. **上传数据集** - 上传您的zip文件
3. **数据预处理** - 自动处理数据集
4. **开始训练** - 使用GPU加速训练

## 🎯 训练优势

### Google Colab的优势：

- ✅ **免费GPU加速** - 使用T4或V100 GPU
- ✅ **稳定环境** - 避免本地环境兼容性问题
- ✅ **快速训练** - GPU训练速度比CPU快10-20倍
- ✅ **云端存储** - 训练结果自动保存

### 预期训练时间：

- **CPU训练**: 约8-12小时（50个epoch）
- **GPU训练**: 约1-2小时（50个epoch）

## 📊 训练配置

### 模型参数：

- **模型**: YOLOv8n（轻量级）
- **训练轮数**: 50 epochs
- **图片尺寸**: 640x640
- **批次大小**: 16
- **学习率**: 0.01
- **优化器**: 自动选择

### 数据集信息：

- **总图片**: 122,972张
- **训练集**: 98,377张
- **验证集**: 24,595张
- **类别数**: 39个

## 🔧 详细操作步骤

### 步骤1: 环境准备

```python
# 在Colab中运行

!pip install ultralytics
!pip install opencv-python pillow matplotlib seaborn pandas tqdm PyYAML
```

### 步骤2: 上传数据

1. 运行上传单元格
2. 选择您的数据集zip文件
3. 等待上传完成

### 步骤3: 数据预处理

```python
# 自动运行数据预处理

!python prepare_dataset.py
```

### 步骤4: 开始训练

```python
from ultralytics import YOLO

model = YOLO('yolov8n.pt')
results = model.train(
    data='dataset.yaml',
    epochs=50,
    imgsz=640,
    batch=16,
    device='0',  # 使用GPU
    # ... 其他参数
)
```

### 步骤5: 下载结果

- 训练完成后自动下载模型文件
- 包含最佳模型、训练图表和配置文件

## 📁 下载的文件

训练完成后，您将获得：
- `best.pt` - 最佳模型权重
- `last.pt` - 最新模型权重
- `dataset.yaml` - 数据集配置文件
- 训练图表（混淆矩阵、损失曲线等）

## 🎯 使用训练好的模型

### 本地预测：

```python
from ultralytics import YOLO

# 加载模型

model = YOLO('best.pt')

# 预测单张图片

results = model('path/to/image.jpg')

# 批量预测

results = model('path/to/images/')
```

### 预测脚本：

使用我们之前创建的 `predict.py` 脚本：
```bash
python predict.py --image path/to/image.jpg
python predict.py --dir path/to/images/ --output results/
```

## 💡 优化建议

### 1. 训练参数调整

- 如果精度不够，可以增加训练轮数到100
- 如果过拟合，可以减少训练轮数或增加数据增强

### 2. 模型选择

- 当前使用YOLOv8n（轻量级）
- 如果需要更高精度，可以尝试YOLOv8s或YOLOv8m

### 3. 数据增强

- 当前已启用数据增强
- 可以根据需要调整增强参数

## 🆘 常见问题

### Q: Colab断开连接怎么办？

A: 重新连接后，从断开的单元格继续运行即可

### Q: 训练时间太长？

A: 可以减少epoch数量到20-30，或使用更大的批次大小

### Q: 内存不足？

A: 减少批次大小到8或4

### Q: 如何保存训练进度？

A: Colab会自动保存，也可以定期下载中间结果

## 📞 常见问题排查

1. Colab 没连到 GPU：菜单 → 代码执行程序 → 更改运行时类型 → 选 T4 GPU
2. 数据集格式不对：确认 zip 解压后每个类别是一个文件夹，图片直接放在类别目录下
3. 训练中途断开：重新连接后从断开的单元格继续即可，已保存的 epoch 权重不会丢
