"""
用户生成内容（帖子/评论）的英文译文 —— 可插拔机器翻译（第 85 批）

============================================================================
要解决的问题
----------------------------------------------------------------------------
第 84 批把界面文案、病害百科、防治措施等都做了中英对照，唯独**用户自己写的内容**
（帖子标题/正文、评论与回复）在英文界面下仍是中文 —— 因为它没有"标准答案"，
不像词典那样能提前把译文写进 `messages.js`。

本模块提供一条**可插拔**的翻译链路：

    services_translate.translate_instance(post)      # 翻一个帖子/评论
    services_translate.translate_text('中文')        # 翻一段文本

provider 由环境变量决定（见 settings.TRANSLATE_PROVIDER）：

    mymemory   免 key 的公共接口（默认）。适合开发/演示，有每日额度，超限会返回
               429/带 error 的 JSON —— 这里会识别并抛 TranslateError，绝不把
               "额度已用完"这种字符串当成译文写进数据库。
    libre      LibreTranslate 兼容接口（自建或第三方），配 TRANSLATE_API_URL。
    openai     OpenAI 兼容的 /chat/completions（DeepSeek、通义、本地 vLLM 都行），
               配 TRANSLATE_API_URL + TRANSLATE_API_KEY + TRANSLATE_MODEL。
    none       关闭自动翻译（只保留人工填写译文的能力）。

设计上的几条硬规则
----------------------------------------------------------------------------
① **绝不阻断主流程**：调用方（发帖/评论的视图）用 `safe_translate_instance()`
   包一层，翻译失败只写日志，帖子照常发布 —— 论坛的可用性不能绑定在第三方接口上。
② **人工译文优先**：`translation_source == 'manual'` 的内容不会被自动翻译覆盖，
   除非显式 `force=True`（命令行 `--force`）。作者自己写的英文版永远是最准的。
③ **按段落分块**：机器翻译接口对单次请求长度有限制（MyMemory 匿名 500 字节），
   而帖子正文可能上千字。这里按**空行分段 → 长段落再按句末标点切**的方式分块，
   逐块请求后按原结构拼回，保留段落换行。
④ **结果缓存**：用 Django cache（开发环境是 FileBasedCache）按
   `provider + 原文hash` 缓存 7 天。论坛里重复内容很常见（本次实测就有两个帖子
   正文完全一样），缓存能同时省额度、省时间。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

#: 单块最大字符数。MyMemory 匿名请求上限是 500 字节，中文 UTF-8 一字 3 字节，
#: 取 160 字（≈480 字节）留出 URL 编码后的余量；其它 provider 也够用。
MAX_CHUNK_CHARS = 160

#: 缓存时长（秒）：7 天。译文不会自己变，缓存久一点没有副作用。
CACHE_TTL = 7 * 24 * 3600

#: 句末标点（中英）：用于把长段落切成可翻译的小块
_SENTENCE_END = re.compile(r'(?<=[。！？!?；;])|(?<=\.\s)')

#: 意见反馈里由**系统**写死的历史文案（早期前端把这两个词当按钮文案直接入库）。
#: 它们不是用户敲的字，`FeedbackSerializer` 有确定的中英对照表（Marked correct /
#: Marked incorrect），所以**不要**送去机器翻译 —— 实测公共接口会把「识别正确」
#: 译成 "Identify Correctly"，还不如固定映射准确。
SYSTEM_SUGGESTIONS = frozenset({'识别正确', '识别错误'})

# ============================================================================
# 术语校正表（译文后处理）
# ----------------------------------------------------------------------------
# 免 key 的公共接口对**农业专有名词**经常直译错，而这类词恰恰是本站的核心词汇。
# 这些规则来自本次实测的真实错译（不是凭空猜的）：
#   · 番茄早疫病 → "Tomato Premature Disease"（早疫 = early blight，不是"早产"）
#   · 抛砖引玉   → "throw bricks here to guide you"（成语直译，英文读者看不懂）
# 只做"目标语"替换、不做源语替换：先让翻译接口正常断句，再纠正用词。
# 换成 DeepL / OpenAI 这类质量更高的接口后，可用 TRANSLATE_GLOSSARY=False 关掉。
# ============================================================================
_GLOSSARY_RULES = (
    (re.compile(r'\bTomato Premature Disease\b', re.I), 'Tomato early blight'),
    (re.compile(r'\bPotato Premature Disease\b', re.I), 'Potato early blight'),
    (re.compile(r'\bPremature Disease\b', re.I), 'early blight'),
    (re.compile(r'\bLate Blight\b', re.I), 'late blight'),
    (re.compile(r'\bCommon Rust\b', re.I), 'common rust'),
    (re.compile(r'\bLeaf Scorch\b', re.I), 'leaf scorch'),
    (
        re.compile(r'\bthrow bricks? (?:here )?to (?:guide|attract) (?:you|jade)\b', re.I),
        'share my experience to start the discussion',
    ),
)


def apply_glossary(text: str) -> str:
    """按术语表纠正机器译文的用词（只处理目标语，不碰原文）"""
    if text and getattr(settings, 'TRANSLATE_GLOSSARY', True):
        for pattern, replacement in _GLOSSARY_RULES:
            text = pattern.sub(replacement, text)
    return text


#: 翻译记忆库脏数据的特征（XLIFF/ TM 标记）。**不能**用"含尖括号"来判定 ——
#: 帖子正文本身就带 `<p>` 等 HTML，那样会把正常译文也拒掉。
_TM_ARTIFACT = re.compile(r'</?(?:g|ph|bpt|ept|it|bx|ex|mrk)\b[^>]*>', re.I)


class TranslateError(RuntimeError):
    """翻译失败（网络、额度、返回格式异常……）。调用方应自行决定是否降级。"""


# ============================================================================
# 配置读取
# ============================================================================
def provider_name() -> str:
    return (getattr(settings, 'TRANSLATE_PROVIDER', 'mymemory') or 'none').strip().lower()


def is_enabled() -> bool:
    """自动翻译是否可用（关闭时只保留人工译文能力）"""
    if not getattr(settings, 'TRANSLATE_ENABLED', True):
        return False
    return provider_name() not in ('', 'none')


def _timeout() -> float:
    return float(getattr(settings, 'TRANSLATE_TIMEOUT', 8))


# ============================================================================
# 分块
# ============================================================================
def split_chunks(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """把长文本切成不超过 `limit` 字符的块，尽量在句末断开

    空行分段会被保留（块之间用 '\\n\\n' 记录），拼回时能还原段落。
    """
    text = (text or '').replace('\r\n', '\n').strip()
    if not text:
        return []
    chunks: list[str] = []
    for paragraph in re.split(r'\n\s*\n', text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= limit:
            chunks.append(paragraph)
            continue
        sentences = [s for s in _SENTENCE_END.split(paragraph) if s and s.strip()]
        current = ''
        for sentence in sentences:
            # 单句就超长（没有标点的长串）：硬切
            while len(sentence) > limit:
                if current:
                    chunks.append(current)
                    current = ''
                chunks.append(sentence[:limit])
                sentence = sentence[limit:]
            if len(current) + len(sentence) <= limit:
                current += sentence
            else:
                if current:
                    chunks.append(current)
                current = sentence
        if current.strip():
            chunks.append(current)
    return chunks


# ============================================================================
# 各 provider 的单块翻译
# ============================================================================
def _http_json(url: str, *, data=None, headers=None, method=None) -> dict:
    body = None
    if data is not None:
        body = json.dumps(data).encode('utf-8')
        headers = {**(headers or {}), 'Content-Type': 'application/json'}
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=_timeout()) as response:
            raw = response.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as exc:  # 4xx/5xx：把响应体带出来便于定位
        detail = exc.read().decode('utf-8', errors='replace')[:200]
        raise TranslateError(f'HTTP {exc.code}: {detail}') from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TranslateError(f'网络错误: {exc}') from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TranslateError(f'返回的不是 JSON: {raw[:120]}') from exc


def _translate_mymemory(chunk: str) -> str:
    """MyMemory 公共接口（免 key，有每日额度）"""
    query = urllib.parse.urlencode({'q': chunk, 'langpair': 'zh-CN|en'})
    email = getattr(settings, 'TRANSLATE_CONTACT_EMAIL', '') or ''
    if email:
        # 官方文档：带上邮箱可以把匿名额度从 5000 字/天提到 50000 字/天
        query += '&de=' + urllib.parse.quote(email)
    payload = _http_json(f'https://api.mymemory.translated.net/get?{query}')
    # 额度用尽时接口仍返回 200，但 responseStatus 不是 200，且 translatedText 里
    # 会塞一句英文的"配额已用完" —— 必须识别出来，不能当译文入库。
    status = payload.get('responseStatus')
    translated = ((payload.get('responseData') or {}).get('translatedText') or '').strip()
    if str(status) != '200' or not translated:
        raise TranslateError(f'MyMemory responseStatus={status} detail={payload.get("responseDetails")!r}')
    if 'MYMEMORY WARNING' in translated.upper() or 'QUERY LENGTH LIMIT' in translated.upper():
        raise TranslateError(f'MyMemory 额度/长度限制: {translated[:120]}')
    if _TM_ARTIFACT.search(translated):
        # 该接口底层是翻译记忆库，偶尔会命中一条**带标记的脏记忆**直接返回，例如
        # 把"标题"译成 `<g id="2610">Captions</g>.`（实测）。这种东西一旦入库，
        # 英文界面就会出现 XML 片段，比"没有译文"糟糕得多 —— 直接当失败处理。
        raise TranslateError(f'MyMemory 返回了翻译记忆库脏数据: {translated[:120]}')
    return translated


def _translate_libre(chunk: str) -> str:
    """LibreTranslate 兼容接口（自建服务或第三方镜像）"""
    url = (getattr(settings, 'TRANSLATE_API_URL', '') or '').rstrip('/')
    if not url:
        raise TranslateError('未配置 TRANSLATE_API_URL（libre provider 必填）')
    data = {'q': chunk, 'source': 'zh', 'target': 'en', 'format': 'text'}
    api_key = getattr(settings, 'TRANSLATE_API_KEY', '') or ''
    if api_key:
        data['api_key'] = api_key
    payload = _http_json(f'{url}/translate', data=data)
    translated = (payload.get('translatedText') or '').strip()
    if not translated:
        raise TranslateError(f'LibreTranslate 未返回译文: {str(payload)[:150]}')
    return translated


def _translate_openai(chunk: str) -> str:
    """OpenAI 兼容的 /chat/completions（DeepSeek / 通义 / 本地 vLLM 等）"""
    base = (getattr(settings, 'TRANSLATE_API_URL', '') or '').rstrip('/')
    if not base:
        raise TranslateError('未配置 TRANSLATE_API_URL（openai provider 必填）')
    api_key = getattr(settings, 'TRANSLATE_API_KEY', '') or ''
    model = getattr(settings, 'TRANSLATE_MODEL', '') or 'gpt-4o-mini'
    system = (
        'You are a professional translator for an agricultural forum. '
        'Translate the user message from Chinese to natural English. '
        'Keep the paragraph structure. Output ONLY the translation, no explanations.'
    )
    payload = {
        'model': model,
        'temperature': 0,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': chunk},
        ],
    }
    headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
    data = _http_json(f'{base}/chat/completions', data=payload, headers=headers)
    try:
        translated = (data['choices'][0]['message']['content'] or '').strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise TranslateError(f'返回结构异常: {str(data)[:150]}') from exc
    if not translated:
        raise TranslateError('模型返回空译文')
    return translated


def _http_form(url: str, fields: dict, headers: dict | None = None) -> dict:
    """表单编码的 POST（DeepL / 百度翻译用的就是这种接口）"""
    body = urllib.parse.urlencode(fields).encode('utf-8')
    request = urllib.request.Request(
        url,
        data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded', **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=_timeout()) as response:
            raw = response.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:200]
        raise TranslateError(f'HTTP {exc.code}: {detail}') from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TranslateError(f'网络错误: {exc}') from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TranslateError(f'返回的不是 JSON: {raw[:120]}') from exc


def _translate_deepl(chunk: str) -> str:
    """DeepL 官方接口（第 86 批）

    免费版 key 以 `:fx` 结尾，接口域名与付费版不同 —— 这里按 key 自动判断，
    也允许用 `TRANSLATE_API_URL` 显式覆盖（例如公司内网网关）。

    鉴权方式（实测踩到的坑）：DeepL 现在要求把 key 放在
    `Authorization: DeepL-Auth-Key <key>` 请求头里；旧的表单字段 `auth_key`
    会被直接拒掉（实测返回 403 "Missing Authorization header"），所以这里只发头。
    """
    api_key = getattr(settings, 'TRANSLATE_API_KEY', '') or ''
    if not api_key:
        raise TranslateError('未配置 TRANSLATE_API_KEY（deepl provider 必填）')
    base = (getattr(settings, 'TRANSLATE_API_URL', '') or '').rstrip('/')
    if not base:
        base = 'https://api-free.deepl.com' if api_key.endswith(':fx') else 'https://api.deepl.com'
    payload = _http_form(
        f'{base}/v2/translate',
        {
            'text': chunk,
            # DeepL 的中文代码是 ZH；目标语用 EN-US（新版接口不接受裸 'EN'）
            'source_lang': 'ZH',
            'target_lang': getattr(settings, 'TRANSLATE_TARGET_LANG', '') or 'EN-US',
        },
        headers={'Authorization': f'DeepL-Auth-Key {api_key}'},
    )
    try:
        translated = (payload['translations'][0]['text'] or '').strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise TranslateError(f'DeepL 返回结构异常: {str(payload)[:150]}') from exc
    if not translated:
        raise TranslateError('DeepL 返回空译文')
    return translated


def _translate_baidu(chunk: str) -> str:
    """百度翻译开放平台（第 86 批）：国内网络可直接访问，适合没有外网代理的部署

    签名规则（官方文档）：`sign = md5(appid + q + salt + 密钥)`。
    """
    app_id = getattr(settings, 'TRANSLATE_APP_ID', '') or ''
    api_key = getattr(settings, 'TRANSLATE_API_KEY', '') or ''
    if not app_id or not api_key:
        raise TranslateError('未配置 TRANSLATE_APP_ID / TRANSLATE_API_KEY（baidu provider 必填）')
    salt = str(int(time.time() * 1000))
    sign = hashlib.md5(f'{app_id}{chunk}{salt}{api_key}'.encode('utf-8')).hexdigest()
    payload = _http_form(
        (getattr(settings, 'TRANSLATE_API_URL', '') or 'https://fanyi-api.baidu.com').rstrip('/')
        + '/api/trans/vip/translate',
        {'q': chunk, 'from': 'zh', 'to': 'en', 'appid': app_id, 'salt': salt, 'sign': sign},
    )
    if payload.get('error_code'):
        # 常见：54003 访问频率受限、54004 余额不足、52001 超时、58001 语种方向不支持
        raise TranslateError(f"百度翻译错误 {payload.get('error_code')}: {payload.get('error_msg')}")
    try:
        translated = ''.join(item.get('dst', '') for item in payload['trans_result']).strip()
    except (KeyError, TypeError) as exc:
        raise TranslateError(f'百度翻译返回结构异常: {str(payload)[:150]}') from exc
    if not translated:
        raise TranslateError('百度翻译返回空译文')
    return translated


_PROVIDERS = {
    'mymemory': _translate_mymemory,
    'deepl': _translate_deepl,
    'baidu': _translate_baidu,
    'libre': _translate_libre,
    'openai': _translate_openai,
}

#: 每个 provider 需要哪些配置 + 一句话说明（`manage.py translate_provider_check` 用它
#: 提示"还差什么"，避免用户改完 .env 却不知道为什么不生效）
PROVIDER_INFO = {
    'mymemory': {
        'label': 'MyMemory 公共接口（免 key）',
        'requires': [],
        'note': '有每日额度；质量一般，适合开发/演示。填 TRANSLATE_CONTACT_EMAIL 可提到 5 万字/天。',
    },
    'deepl': {
        'label': 'DeepL 官方接口',
        'requires': ['TRANSLATE_API_KEY'],
        'note': '质量最好之一；免费版 key 以 :fx 结尾会自动走 api-free.deepl.com。',
    },
    'baidu': {
        'label': '百度翻译开放平台',
        'requires': ['TRANSLATE_APP_ID', 'TRANSLATE_API_KEY'],
        'note': '国内网络可直接访问，适合没有外网代理的部署。',
    },
    'libre': {
        'label': 'LibreTranslate 兼容接口',
        'requires': ['TRANSLATE_API_URL'],
        'note': '可自建（离线部署）；API_KEY 视服务端是否开启鉴权。',
    },
    'openai': {
        'label': 'OpenAI 兼容 /chat/completions',
        'requires': ['TRANSLATE_API_URL', 'TRANSLATE_API_KEY'],
        'note': '可接 DeepSeek / 通义 / Moonshot / 本地 vLLM；用 TRANSLATE_MODEL 指定模型。',
    },
}


def missing_provider_config(provider: str | None = None) -> list:
    """当前 provider 还缺哪些必填配置（供检查命令与错误提示使用）"""
    name = (provider or provider_name()).strip().lower()
    info = PROVIDER_INFO.get(name)
    if not info:
        return []
    return [key for key in info['requires'] if not (os.environ.get(key) or getattr(settings, key, ''))]


# ============================================================================
# 对外接口
# ============================================================================
def translate_text(text: str, provider: str | None = None) -> str:
    """把一段中文翻成英文；失败抛 TranslateError

    空文本直接返回空串（不请求接口）。分块翻译后按段落拼回。
    """
    text = (text or '').strip()
    if not text:
        return ''
    name = (provider or provider_name()).strip().lower()
    if name in ('', 'none'):
        raise TranslateError('翻译已关闭（TRANSLATE_PROVIDER=none）')
    handler = _PROVIDERS.get(name)
    if handler is None:
        raise TranslateError(
            f'未知的翻译 provider: {name}（可选：{", ".join(_PROVIDERS)}、none）'
        )
    missing = missing_provider_config(name)
    if missing:
        raise TranslateError(f'{name} 缺少配置：{"、".join(missing)}（见 .env.example）')

    # 缓存键带 v2：术语校正表是第 85 批中途加入的，v1 的缓存里存的是**未校正**的
    # 译文，若不改版本号，`--force` 重跑会直接命中旧缓存、看起来"规则没生效"。
    # 同时把 glossary 开关编进键名：关掉术语表时不会读到已校正的缓存。
    glossary_on = bool(getattr(settings, 'TRANSLATE_GLOSSARY', True))
    version = 'v2g1' if glossary_on else 'v2g0'
    digest = hashlib.sha1(text.encode('utf-8')).hexdigest()
    cache_key = f'translate:{version}:{name}:{digest}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    pieces = []
    for chunk in split_chunks(text):
        # 分块缓存里存的是**原始**机器译文（与术语表无关），换 provider 也不会串
        chunk_key = 'translate:v1:%s:%s' % (name, hashlib.sha1(chunk.encode('utf-8')).hexdigest())
        hit = cache.get(chunk_key)
        if not hit:
            hit = handler(chunk)
            if not hit:
                raise TranslateError('接口返回空译文')
            cache.set(chunk_key, hit, CACHE_TTL)
        pieces.append(hit)

    # 段落之间用空行拼回（split_chunks 是按段落顺序切的，这里只需保留可读性）
    result = apply_glossary('\n\n'.join(pieces).strip())
    cache.set(cache_key, result, CACHE_TTL)
    return result


def is_translatable(instance) -> bool:
    """这条内容还有没有**值得翻译**的原文

    用途：批量命令排期时过滤掉"看起来没译文、其实不需要译"的行。典型例子是
    意见反馈里系统写死的「识别正确/识别错误」—— 它们由序列化器固定映射成英文，
    送去机器翻译只会更差（见 SYSTEM_SUGGESTIONS）。
    """
    from .models import Feedback

    if isinstance(instance, Feedback):
        suggestion = (instance.suggestion or '').strip()
        if suggestion and suggestion not in SYSTEM_SUGGESTIONS:
            return True
        return bool((instance.admin_reply or '').strip())
    return bool(instance.source_fingerprint())


def translate_instance(instance, *, force: bool = False, provider: str | None = None,
                       allow_manual_overwrite: bool = False) -> bool:
    """给一个帖子/评论补齐英文译文；返回是否**真的写入**了

    规则：
      · 原文为空 → 跳过（返回 False）；
      · 已有译文且指纹一致（原文没改过）→ 跳过；
      · 已有**人工**译文且未被 force → 跳过（人工优先）；
      · 否则翻译并写回 `*_en` + `translation_hash` / `translation_source` / `translated_at`。

    只保存自己改动的字段（`update_fields`），避免把并发中的其它字段一起覆盖。
    """
    from .models import Feedback
    from .models_forum import Comment, Post  # 局部导入，避免模型层反向依赖

    fingerprint = instance.source_fingerprint()
    if not fingerprint:
        return False  # 原文为空，没什么可翻

    has_text = instance.has_translation
    if has_text and instance.translation_hash == fingerprint and not force:
        return False  # 原文没变，译文仍然有效

    if (instance.translation_source == instance.SOURCE_MANUAL and has_text
            and not allow_manual_overwrite):
        # 第 86 批：`force` **不再**越过这道闸。理由：第 85 批加了"作者自己填英文"
        # 的能力之后，`--force`（换 provider 后一键重刷）会把作者写的英文冲掉。
        # 现在只有显式 `allow_manual_overwrite=True`（命令行 --force-manual）才覆盖人工译文。
        logger.info('跳过人工译文 id=%s（需要 allow_manual_overwrite / --force-manual 才会覆盖）', instance.pk)
        return False

    update_fields = []
    if isinstance(instance, Post):
        title_en = translate_text(instance.title, provider=provider) if instance.title.strip() else ''
        content_en = translate_text(instance.content, provider=provider)
        if title_en:
            instance.title_en = title_en
            update_fields.append('title_en')
        if content_en:
            instance.content_en = content_en
            update_fields.append('content_en')
    elif isinstance(instance, Comment):
        content_en = translate_text(instance.content, provider=provider)
        if content_en:
            instance.content_en = content_en
            update_fields.append('content_en')
    elif isinstance(instance, Feedback):
        # 第 85 批：反馈有两条独立文本（用户写的意见 + 管理员写的回复），
        # 只翻**非空**的那一条 —— 空字符串不请求接口，也不覆盖已有译文。
        # 系统写死的「识别正确/识别错误」跳过（序列化器有固定映射，见 SYSTEM_SUGGESTIONS）。
        suggestion = (instance.suggestion or '').strip()
        if suggestion and suggestion not in SYSTEM_SUGGESTIONS:
            suggestion_en = translate_text(instance.suggestion, provider=provider)
            if suggestion_en:
                instance.suggestion_en = suggestion_en
                update_fields.append('suggestion_en')
        if (instance.admin_reply or '').strip():
            reply_en = translate_text(instance.admin_reply, provider=provider)
            if reply_en:
                instance.admin_reply_en = reply_en
                update_fields.append('admin_reply_en')
    else:
        raise TranslateError(f'不支持的内容类型: {type(instance).__name__}')

    if not update_fields:
        return False

    instance.translation_hash = fingerprint
    instance.translation_source = instance.SOURCE_AUTO
    instance.translated_at = timezone.now()
    update_fields += ['translation_hash', 'translation_source', 'translated_at']
    instance.save(update_fields=update_fields)
    return True


def safe_translate_instance(instance, **kwargs) -> bool:
    """给视图层用的"绝不抛异常"版本

    论坛发帖/评论不能被翻译接口拖垮：网络抖动、额度用尽、返回格式变了……
    一律只记日志。返回是否写入成功，调用方不需要关心失败原因。
    """
    if not is_enabled():
        return False
    try:
        return translate_instance(instance, **kwargs)
    except TranslateError as exc:
        logger.warning('自动翻译失败（已忽略）%s id=%s: %s', type(instance).__name__, instance.pk, exc)
    except Exception:  # noqa: BLE001 —— 兜底，绝不让翻译影响发帖
        logger.exception('自动翻译异常（已忽略）%s id=%s', type(instance).__name__, instance.pk)
    return False
