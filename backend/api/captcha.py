"""注册验证码（第 233 批）：**图片验证码**，服务端校验、一次性、有有效期。

## 为什么要它

注册接口是 `AllowAny` + `register` 限流（`10/hour`）。限流只能拖慢批量注册，
挡不住"换 IP / 换代理"的脚本，注册表会被灌垃圾账号。加一道只有人（或 OCR 很贵的程序）
能过的验证码，是最小成本的做法。

## 设计（都在这里，别散到 view 里）

| 点 | 做法 | 为什么 |
|---|---|---|
| 存哪 | Django cache（开发=文件缓存，生产=Redis，见 settings.CACHES） | 验证码是**短命**数据，不值得进库，也不该进库（进库就要清理任务） |
| 有效期 | `CAPTCHA_TTL_SECONDS`（默认 300 秒） | 太短用户填不完，太长被人拿去批量注册 |
| 一次性 | 校验成功**立刻 `cache.delete`** | 否则同一张验证码可以反复注册 |
| 错误次数 | 同一张最多错 5 次，超了直接作废 | 不然 4 位码被暴力枚举（虽已有全局限流，双保险） |
| 大小写 | 不敏感 | 图片里是大写，用户小写也算过 —— 别在非安全问题上学究气 |
| 字符集 | 去掉 `0 O 1 I L` 这类易混字符 | 减少"我看清了但打错了"的挫败感 |

## 为什么不用"算术题"这种文字验证码

纯文本算术题机器一眼就会做，等于没加；图片验证码至少需要 OCR。
（这个项目是课程/毕设规模，够用即可；真要抗专业打码，得接第三方或滑块。）
"""
from __future__ import annotations

import base64
import io
import logging
import random
import uuid

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_PREFIX = 'captcha:'
#: 去掉 0/O/1/I/L —— 图片里这些字符人眼也容易看错
ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
CODE_LENGTH = 4
MAX_ATTEMPTS = 5
IMAGE_WIDTH = 132
IMAGE_HEIGHT = 48

#: 字体候选：Windows 自带 TTF 优先，其次 Pillow 内置字体（容器里没有系统字体也能跑）
FONT_CANDIDATES = (
    'C:/Windows/Fonts/arialbd.ttf',
    'C:/Windows/Fonts/arial.ttf',
    'C:/Windows/Fonts/segoeui.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
)


def _load_font(size: int):
    from PIL import ImageFont

    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001 —— 缺字体是常态，继续试下一个
            continue
    return ImageFont.load_default(size=size)


def _cache_key(captcha_id: str) -> str:
    return f'{CACHE_PREFIX}{captcha_id}'


def _render(code: str) -> bytes:
    """把 4 个字符画成 PNG：每个字符单独旋转、加噪点与干扰线。

    为什么逐字符画：整串一次 `draw.text()` 太"干净"，OCR 一次就过。
    逐字符变换位置/角度/颜色能把免费的 OCR 拖慢，同时人眼仍然一眼能读。
    """
    from PIL import Image, ImageDraw

    rng = random.Random()
    image = Image.new('RGB', (IMAGE_WIDTH, IMAGE_HEIGHT), (242, 246, 243))
    draw = ImageDraw.Draw(image)

    # 背景噪点
    for _ in range(90):
        x = rng.randrange(IMAGE_WIDTH)
        y = rng.randrange(IMAGE_HEIGHT)
        draw.point((x, y), fill=(rng.randint(150, 210), rng.randint(170, 220), rng.randint(160, 210)))

    # 干扰线（两条，穿过字符区域但不遮得太死）
    for _ in range(2):
        points = [
            (rng.randrange(0, 20), rng.randrange(0, IMAGE_HEIGHT)),
            (rng.randrange(40, 90), rng.randrange(0, IMAGE_HEIGHT)),
            (rng.randrange(100, IMAGE_WIDTH), rng.randrange(0, IMAGE_HEIGHT)),
        ]
        draw.line(points, fill=(rng.randint(140, 180), rng.randint(160, 200), rng.randint(140, 180)), width=2)

    font = _load_font(28)
    slot = IMAGE_WIDTH // len(code)
    for index, char in enumerate(code):
        layer = Image.new('RGBA', (slot, IMAGE_HEIGHT), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(layer)
        color = (rng.randint(20, 90), rng.randint(60, 120), rng.randint(40, 100), 255)
        char_draw.text((slot // 2, IMAGE_HEIGHT // 2), char, font=font, fill=color, anchor='mm')
        rotated = layer.rotate(rng.uniform(-24, 24), expand=False, resample=Image.BICUBIC)
        image.paste(
            rotated,
            # 不再往左偏：负偏移会把第一个字符切掉一块（实测 "6" 被裁了半边）
            (index * slot + rng.randint(0, 2), rng.randint(-3, 3)),
            rotated,
        )

    buffer = io.BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def issue() -> dict:
    """签发一张验证码，返回 `{captcha_id, image(data URI), expires_in}`。"""
    code = ''.join(random.choice(ALPHABET) for _ in range(CODE_LENGTH))
    captcha_id = uuid.uuid4().hex
    ttl = int(getattr(settings, 'CAPTCHA_TTL_SECONDS', 300))
    # 缓存 value 用 dict：以后要加"已用过"/"来源 IP"之类不用改 key 结构
    cache.set(_cache_key(captcha_id), {'code': code.upper(), 'attempts': 0}, timeout=ttl)
    png = _render(code)
    return {
        'captcha_id': captcha_id,
        'image': 'data:image/png;base64,' + base64.b64encode(png).decode('ascii'),
        'expires_in': ttl,
    }


def verify(captcha_id, code) -> bool:
    """校验并**消费**这张验证码。

    返回 True 时这张码已经被删掉（一次性）；返回 False 时：
      · 码不存在 / 已过期 / 已被用过；
      · 或对错达到 `MAX_ATTEMPTS` 次（此时也作废，防枚举）。
    """
    if not captcha_id or not code:
        return False

    key = _cache_key(str(captcha_id))
    record = cache.get(key)
    if not isinstance(record, dict):
        return False

    submitted = str(code).strip().upper()
    expected = str(record.get('code', '')).upper()

    if submitted and submitted == expected:
        cache.delete(key)
        return True

    attempts = int(record.get('attempts', 0)) + 1
    if attempts >= MAX_ATTEMPTS:
        cache.delete(key)
        logger.info('验证码错误次数过多，已作废：%s', str(captcha_id)[:8])
        return False

    # 保留剩余次数：用原 TTL 续存（简单起见重设一次超时；时间上略宽松，可接受）
    cache.set(key, {'code': expected, 'attempts': attempts},
              timeout=int(getattr(settings, 'CAPTCHA_TTL_SECONDS', 300)))
    return False
