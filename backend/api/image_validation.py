"""
图片上传的统一校验（第 91 批）
==================================================================
背景（真实的三个问题，都出在通用图片上传 `/api/upload/image/`）：

1. **没有大小上限**。同一个项目里头像上传有 `MAX_SIZE = 2MB`，通用上传却没有 ——
   任何登录用户都能拿它把磁盘灌满（分片上传一次几 MB，写脚本就能刷）。
2. **只比 `content_type`**。那是**客户端自己声明的请求头**，随便伪造：
   `Content-Type: image/png` + 一个 500MB 的任意文件就能过。
   项目的 `requirements.txt` 里有 Pillow，这里就用它按**文件头**判断真实格式。
3. **直接用了用户给的原始文件名**（`f'uploads/{image_file.name}'`）。
   文件名里带 `../` 或绝对路径时，是否越出媒体目录取决于存储后端，
   属于"能不能出事看运气"的写法。

所以这里集中做四件事：**大小上限 → 真实格式探测 → 扩展名按真实格式决定 → 文件名随机化**。
探测只读文件头的几十个字节，不会把整个图读进内存。

用法：

    from .image_validation import validate_image_upload, ImageValidationError

    try:
        meta = validate_image_upload(request.FILES.get('image'))
    except ImageValidationError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    name = default_storage.save(f'uploads/{meta["filename"]}', request.FILES['image'])
"""
from __future__ import annotations

import uuid

from django.core.files.uploadedfile import UploadedFile
from PIL import Image

#: 通用图片上传的大小上限（新闻/帖子插图）。头像另有 2MB 的独立上限，见 views_user.py。
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB

#: 允许的图片格式 → 落盘扩展名（扩展名由**探测结果**决定，不看用户传的 filename）
ALLOWED_FORMATS = {
    'JPEG': '.jpg',
    'PNG': '.png',
    'GIF': '.gif',
    'WEBP': '.webp',
    'BMP': '.bmp',
}

#: 给用户看的格式说明（与 ALLOWED_FORMATS 保持一致）
FORMAT_HINT = 'JPG / PNG / GIF / WEBP / BMP'

#: 探测时需要读的头部长度：覆盖 JPEG/PNG/GIF/BMP/WEBP 的魔数与 RIFF 头
_HEADER_BYTES = 32


class ImageValidationError(ValueError):
    """校验失败。`str(exc)` 就是要回给用户的说明文案。"""


def detect_image_format(upload: UploadedFile) -> str | None:
    """
    按**文件内容**判断图片格式（不信任 `content_type`），失败返回 None。

    只读文件头的 `_HEADER_BYTES` 字节，读完把指针还原 —— 调用方随后仍能正常保存整个文件。
    """
    try:
        upload.seek(0)
        head = upload.read(_HEADER_BYTES)
    except Exception:  # noqa: BLE001  文件对象异常一律当"不是图片"
        return None
    finally:
        try:
            upload.seek(0)
        except Exception:  # noqa: BLE001
            pass

    if not head:
        return None

    # ① 常见格式的魔数（先自己判，避免把整个文件交给 Pillow）
    if head.startswith(b'\xff\xd8\xff'):
        return 'JPEG'
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'PNG'
    if head.startswith((b'GIF87a', b'GIF89a')):
        return 'GIF'
    if head.startswith(b'BM'):
        return 'BMP'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'WEBP'

    # ② 兜底：交给 Pillow 用**头部**判断（不 load()，所以不会解压整张图）
    try:
        upload.seek(0)
        with Image.open(upload) as img:
            fmt = (img.format or '').upper()
        return fmt or None
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            upload.seek(0)
        except Exception:  # noqa: BLE001
            pass


def safe_upload_name(upload: UploadedFile, ext: str, prefix: str = '') -> str:
    """
    生成随机的安全文件名。

    刻意**不用**用户给的 `upload.name`：那个字符串可以带 `../` 或绝对路径，
    落到存储后端的行为取决于实现（Django 的 `get_valid_name` 会清洗，但依赖它不如不依赖）。
    扩展名由真实格式决定，也不采用原文件名里的后缀。
    """
    suffix = uuid.uuid4().hex[:16]
    stem = f'{prefix}{suffix}' if prefix else suffix
    return f'{stem}{ext}'


def validate_image_upload(
    upload: UploadedFile | None,
    *,
    max_size: int = MAX_IMAGE_SIZE,
    allowed_formats: dict | None = None,
    prefix: str = '',
) -> dict:
    """
    校验一张上传的图片，返回 `{'format', 'ext', 'filename', 'size'}`。

    失败时抛 `ImageValidationError`，其文案可直接展示给用户。

    :param upload: `request.FILES` 里的文件对象
    :param max_size: 大小上限（字节）
    :param allowed_formats: 允许的格式集合，默认 `ALLOWED_FORMATS`
    :param prefix: 文件名前缀（例如新闻图用 `news_`），便于人工排查
    """
    allowed = allowed_formats or ALLOWED_FORMATS

    if upload is None:
        raise ImageValidationError('未提供图片文件')

    size = getattr(upload, 'size', None)
    if not size:
        raise ImageValidationError('图片内容为空')
    if size > max_size:
        raise ImageValidationError(
            f'图片大小不能超过 {max_size // (1024 * 1024)}MB（当前 {size / (1024 * 1024):.1f}MB）'
        )

    fmt = detect_image_format(upload)
    if fmt is None or fmt not in allowed:
        raise ImageValidationError(f'无法识别图片格式，请上传 {FORMAT_HINT} 格式的图片')

    ext = allowed[fmt]
    return {
        'format': fmt,
        'ext': ext,
        'filename': safe_upload_name(upload, ext, prefix=prefix),
        'size': size,
    }
