# ============================================================================
# 后端镜像（第 94 批）
# ----------------------------------------------------------------------------
# 构建：
#   docker build -t crop-disease-backend ./backend
# 运行（与 docker-compose.yml 二选一）：
#   docker run --rm -p 8000:8000 -v $(pwd)/backend/media:/app/media \
#     -e DJANGO_DEBUG=False -e DJANGO_SECRET_KEY=... \
#     -e DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 crop-disease-backend
#
# 两点刻意选择：
#   1. **不装 requirements-dev.txt**（faker/tabulate 只有造数据的命令用）；
#   2. **带上 requirements-prod.txt**（gunicorn + whitenoise）—— 容器里没有 Nginx
#      托管静态文件，WhiteNoise 是必须的。
#
# 镜像体积提示：torch 的 CPU 轮子本身就有几百 MB，这是识别模型的代价；
# 若要多阶段瘦身，可以在 builder 阶段装依赖、运行阶段只拷 site-packages。
# ============================================================================
FROM python:3.11-slim

# OpenCV / torch 在 slim 镜像里缺的系统库（不装会在 import cv2 时报 libGL 缺失）
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libsm6 \
        libxext6 \
        libxrender1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖（利用层缓存：改代码不必重装 torch）
COPY requirements.txt requirements-prod.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt -r requirements-prod.txt

# 再拷代码
COPY . .

# 生产默认值：容器里必须显式传 DJANGO_SECRET_KEY，否则启动会直接拒绝（settings 里有守卫）
ENV DJANGO_DEBUG=False \
    DJANGO_ALLOWED_HOSTS=* \
    DJANGO_WHITENOISE=True \
    DJANGO_SERVE_MEDIA=True \
    GUNICORN_BIND=0.0.0.0:8000 \
    GUNICORN_WORKERS=2

# collectstatic 需要 STATIC_ROOT 存在；媒体目录用卷挂出去
RUN mkdir -p /app/staticfiles /app/media \
    && python manage.py collectstatic --noinput || true

EXPOSE 8000

# 健康检查：用项目自己的 /api/health/（不依赖任何第三方工具）
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health/ || exit 1

# 入口：先跑迁移（幂等），再起 gunicorn
# 说明：把 migrate 放在这里是为了"一条命令能起"；多副本部署时应改成独立的 init job，
# 否则多个副本会同时跑迁移（Django 的迁移表有锁，通常没事，但不该依赖它）。
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn -c gunicorn.conf.py crop_disease_backend.wsgi:application"]
