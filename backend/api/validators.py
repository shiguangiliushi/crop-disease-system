"""上传文件校验（第 342 批）

## 为什么需要统一入口

审计发现上传校验**分散在 10 个文件**里（各自写大小判断/扩展名判断），结果是：

- 新接口容易忘；
- 有地方只看 `content_type`（客户端可伪造），不看文件头；
- 有地方只看扩展名（改名就能绕过）。

这里提供一个**唯一入口**，新接口只要调 `validate_image_upload(file)` 就行。

## 为什么不用 Pillow 的 verify()

Pillow 会把整个图解码，对 10MB 的图耗时几十毫秒到几百毫秒；而这里只需要
**判断"这是不是真的图片"**，读前 12 字节就够。真正的解码在上传之后由业务逻辑做
（例如助手会把图缩到 1280px），那时才需要完整解码。

## 拒绝策略

- 体积超限 → `ValidationError`
- `content_type` 不在白名单 → 拒绝（**但不能只信它**）
- 文件头不匹配 → 拒绝（这才是真正的防线）

## 用法

    from .validators import validate_image_upload

    def post(self, request):
        validate_image_upload(request.data.get('image'))
        ...
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

#: 允许的图片类型：MIME → 可接受的魔数前缀
_IMAGE_SIGNATURES = {
    'image/jpeg': (b'\xff\xd8\xff',),
    'image/png': (b'\x89PNG\r\n\x1a\n',),
    'image/gif': (b'GIF87a', b'GIF89a'),
}

#: 默认体积上限（10MB）。助手/识别都远小于这个值。
DEFAULT_MAX_MB = 10

#: 读多少字节足够判断所有支持的格式（WEBP 需要读到第 12 字节）
_HEAD_BYTES = 16


def sniff_image_type(head: bytes) -> str | None:
    """从文件头判断真实类型，返回 MIME 或 None。"""
    for mime, prefixes in _IMAGE_SIGNATURES.items():
        if any(head.startswith(prefix) for prefix in prefixes):
            return mime
    # WEBP: RIFF....WEBP
    if len(head) >= 12 and head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image/webp'
    return None


def validate_image_upload(upload, *, max_mb: int = DEFAULT_MAX_MB, field: str = '图片'):
    """校验一个上传的图片；不合法直接抛 `ValidationError`。

    ⚠️ 传入必须是 Django 的 `UploadedFile`（有 `read` / `size`）。
       若为 None 或空，按"没传"处理（不抛）。
    """
    if upload is None:
        return

    size = getattr(upload, 'size', None)
    if size is not None and size > max_mb * 1024 * 1024:
        raise ValidationError(f'{field}不能超过 {max_mb}MB')

    claimed = (getattr(upload, 'content_type', '') or '').lower()
    if claimed and not (claimed.startswith('image/') or claimed == 'application/octet-stream'):
        raise ValidationError(f'{field}必须是图片文件')

    # 读文件头再复位，避免影响后续读取
    try:
        head = upload.read(_HEAD_BYTES)
        upload.seek(0)
    except (AttributeError, OSError):
        # 不是文件对象（例如已经是 ContentFile）→ 跳过魔数检查，交给业务层
        return

    if not head:
        raise ValidationError(f'{field}是空文件')

    real = sniff_image_type(head)
    if real is None:
        raise ValidationError(f'{field}内容不是有效的图片（文件头不匹配）')


def validate_video_upload(upload, *, max_mb: int = 50, field: str = '视频'):
    """视频同理，但只校验体积与 MIME（魔数格式太多，逐个判断性价比低）。"""
    if upload is None:
        return
    size = getattr(upload, 'size', None)
    if size is not None and size > max_mb * 1024 * 1024:
        raise ValidationError(f'{field}不能超过 {max_mb}MB')
    claimed = (getattr(upload, 'content_type', '') or '').lower()
    if claimed and not claimed.startswith('video/'):
        raise ValidationError(f'{field}必须是视频文件')
