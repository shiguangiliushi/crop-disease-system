"""出站脱敏 —— 上下文拼进提示之前，先把"不该离开本机"的部分处理掉。

## 为什么必须先脱敏再拼上下文

`check_env` 的输出里有 `sys.executable` 全路径（`check_env.py:130`）、requirements 路径、
各依赖版本；健康页的 `runtime` 里还有 `MEDIA_ROOT` / `BASE_DIR` / 数据库引擎名
（`views_system_health.py:210-218`）。这些**不是密钥**，但拼起来足以复原部署拓扑
（盘符、用户名、conda 路径、目录结构），而系统助手的请求会离开本机去外部模型。

所以脱敏放在**工具返回处统一过一遍**，而不是指望每个工具自觉 ——
"某个工具忘了脱敏"这种 bug 只能靠代码结构避免，靠自觉必然漏。

## 三条规则

1. **绝对路径只留最后两级**：`C:\\Users\\zhx\\envs\\crop_env\\python.exe`
   → `…\\crop_env\\python.exe`（诊断只需要知道"哪个解释器/哪个目录"，不需要知道是谁的机器）；
2. **家目录里的用户名换成 `<user>`**：`/home/alice/app/x.py` → `…/app/x.py`；
3. **凭证片段照旧抹掉**：复用 `api/audit.py` 的 `SENSITIVE_PATTERN`
   （`token=` / `password=` / `secret=` / `key=`）。只复用这条正则，不复用
   `sanitize_detail()` —— 它顺带截断到 2000 字，那是审计字段的约束，不是这里的。

URL **不动**：它可能是 `docs/` 里给出的文档链接，属于有用的信息，且不泄露本机结构。
先把 URL 换占位符、脱敏完再换回来，否则 `https://host/a/b` 里的路径会被当成绝对路径切掉。
"""
from __future__ import annotations

import re

from ...audit import SENSITIVE_PATTERN

#: 单条文本的长度上限（4 KB）。一个检查项写不了 4000 字，超了就是被拼接过。
TEXT_LIMIT = 4000

_URL = re.compile(r'https?://[^\s<>"\'）)]+')
#: 绝对路径 —— **一次扫完**，两种写法放在同一个交替里。
#:
#: ⚠️ 不能"先替换 Windows 再替换 POSIX"：第一遍把 `C:/Users/bob/x.py` 换成
#: `…/<user>/x.py` 之后，第二遍会把剩下的 `/x.py` 当成 POSIX 绝对路径再切一刀，
#: 结果拼出 `…/<user>…/x.py` 这种半截东西（第一版就是这样，被单测抓到）。
_PATH = re.compile(
    r'(?P<win>(?<![\w.])[A-Za-z]:[\\/](?:[^\\/\s:*?"<>|]+[\\/])*[^\\/\s:*?"<>|]*)'
    r'|(?P<posix>(?<![\w:])/(?:[^/\s:*?"<>|]+/)*[^/\s:*?"<>|]+)'
)

#: 家目录标记 → 它后面那一级是用户名
_HOME_MARKERS = ('users', 'home', 'documents and settings')


def _mask_path(raw: str) -> str:
    """把一条绝对路径压成 `…/<倒数第二级>/<最后一级>`"""
    if not raw:
        return raw
    sep = '\\' if '\\' in raw else '/'
    parts = [part for part in re.split(r'[\\/]+', raw) if part]
    if not parts:
        return raw

    lowered = [part.lower() for part in parts]
    for marker in _HOME_MARKERS:
        if marker in lowered:
            index = lowered.index(marker)
            if index + 1 < len(parts) and parts[index + 1].lower() not in ('public', 'default'):
                parts[index + 1] = '<user>'
            break

    keep = parts[-2:] if len(parts) > 2 else parts
    return '…' + sep + sep.join(keep)


def path(value) -> str:
    """整条路径脱敏（用于只给路径、不给整段文本的字段）"""
    text_value = '' if value is None else str(value)
    return _mask_path(text_value) if text_value.strip() else text_value


def text(value, *, limit: int = TEXT_LIMIT) -> str:
    """一段文本脱敏：路径 → 省略号路径，凭证片段抹掉，超长截断"""
    raw = '' if value is None else str(value)

    urls: list[str] = []

    def _stash_url(match):
        urls.append(match.group(0))
        return f'\uf000{len(urls) - 1}\uf001'

    masked = _URL.sub(_stash_url, raw)
    masked = _PATH.sub(lambda m: _mask_path(m.group(0)), masked)
    # 只复用凭证过滤那一条正则，**不调** `audit.sanitize_detail()`：
    # 它顺带把文本截到 2000 字，那是审计 `detail` 字段的约束；
    # 用在这里会在 4000 字的预算之前就把工具返回的 JSON 悄悄切一半（单测抓到的）。
    masked = SENSITIVE_PATTERN.sub(r'\1=***', masked)

    for index, url in enumerate(urls):
        masked = masked.replace(f'\uf000{index}\uf001', url)

    if len(masked) > limit:
        masked = masked[:limit] + '…（已截断）'
    return masked


def payload(value, *, limit: int = TEXT_LIMIT):
    """递归脱敏任意 JSON 结构（工具返回值的统一出口）"""
    if isinstance(value, str):
        return text(value, limit=limit)
    if isinstance(value, dict):
        return {key: payload(item, limit=limit) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [payload(item, limit=limit) for item in value]
    return value
