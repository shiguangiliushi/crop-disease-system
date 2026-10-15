"""LLM 调用层（第 193 批，K5）—— 与既有 `services_translate.py` 的写法一致，但配置独立。

## 为什么另开一组配置而不是复用 `TRANSLATE_*`

翻译与助手是两条独立的链路，各有自己的降级策略：
  · 翻译挂了 → 帖子照发，只是没有英文；
  · 助手挂了 → 识别结果页仍要能看，回答降级成"词条原文"。
混用同一组配置会让两种故障互相牵连（改翻译的 provider 顺手把助手弄坏）。

## 实测事实（第 192 批验证过，见 docs/智能回答助手框架.md 6.1）

· 端点：`https://api.deepseek.com/v1`，OpenAI 兼容；
· **请求 `deepseek-chat` 时响应体的 `model` 字段是 `deepseek-flash`** —— 端点侧做了
  重定向/别名。所以 `LLM_MODEL` **不保证精确选型**，本模块把实际落到的模型记进
  `ChatResult.model`，让上层能发现"配置与实到不一致"而不是静默接受；
· 极短请求 0.8s，真实回答（带 7 维度上下文）会显著更慢 —— 所以默认 `timeout=20`。

## 与 requests 的关系

项目已依赖 `requests`（`services_translate.py` 用它），这里同样用它，
不另引 SDK —— 少一个依赖，且 SDK 会自带重试/代理策略，反而不便于精确控制超时。
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """LLM 调用失败（网络、超时、HTTP 错误码、响应结构不对）。

    调用方（`orchestrator`）**必须接住它并降级**，不允许把它抛给视图层 ——
    助手是旁路功能，不能因为模型不可用而让识别结果页报错。
    """


@dataclass
class ChatResult:
    """一次调用的结果。`usage` 与 `model` 都要留下来：
    · `usage` → 用量台账（框架文档第六节）；
    · `model` → 发现"配置的模型与实到的模型不一致"（本端点就会发生）；
    · `finish_reason` → **判断答案有没有被长度上限截断**（第 204 批补）。

    ## 为什么必须留 `finish_reason`

    第 204 批发现：回答被 `max_tokens` 截断时，**接口与界面都毫无表示** ——
    用户看到的是半句话（"具体用药请以…"之前就断了），而系统以为答完了、
    还照常提示"已生成"。**用药建议被截尾比"答得短"严重得多**，
    所以这个字段必须一路传到前端。
    """

    text: str
    model: str = ''
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    #: OpenAI 兼容字段：`'stop'` 正常结束、`'length'` 触到 max_tokens 被截断
    finish_reason: str = ''
    raw: dict = field(default_factory=dict)

    @property
    def truncated(self) -> bool:
        """是否被长度上限截断（`finish_reason == 'length'`）。"""
        return self.finish_reason == 'length'


def _cfg(name: str, default):
    """读配置：**优先 `settings`，其次 `os.environ`**。

    为什么两处都读：`settings.py` 里那份是给 Django 各处用的；而本模块的单元测试
    可能只设了环境变量、没经过 settings。两处都认，行为在两种入口下一致。
    """
    value = getattr(settings, name, None)
    if value in (None, ''):
        import os
        value = os.environ.get(name, default)
    return value if value not in (None, '') else default


def enabled() -> bool:
    """是否具备调用条件（开关打开 + 三个必填项齐备）。"""
    flag = str(_cfg('LLM_ENABLED', 'False')).strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(flag and _cfg('LLM_API_URL', '') and _cfg('LLM_API_KEY', '') and _cfg('LLM_MODEL', ''))


def model_name() -> str:
    return str(_cfg('LLM_MODEL', 'deepseek-chat'))


def timeout_seconds() -> float:
    try:
        return float(_cfg('LLM_TIMEOUT', 20))
    except (TypeError, ValueError):
        return 20.0


def _endpoint() -> str:
    base = str(_cfg('LLM_API_URL', '')).rstrip('/')
    # 兼容两种写法：给了 `/v1` 或直接给了完整的 `/chat/completions`
    if base.endswith('/chat/completions'):
        return base
    return f'{base}/chat/completions'


def chat(messages: list[dict], *, max_tokens: int | None = None,
         temperature: float = 0.2, timeout: float | None = None) -> ChatResult:
    """调一次 `/chat/completions`。失败抛 `LLMError`（由调用方降级）。

    `temperature` 默认 0.2 而不是 0：完全贪心在长上下文里容易反复重复同一句；
    但也不能高 —— 农业问答要的是稳定复述语料，不是发挥。
    """
    if not enabled():
        raise LLMError('LLM 未启用或配置不全（LLM_ENABLED / LLM_API_URL / LLM_API_KEY / LLM_MODEL）')

    if max_tokens is None:
        try:
            max_tokens = int(_cfg('LLM_MAX_TOKENS', 800))
        except (TypeError, ValueError):
            max_tokens = 800

    payload = {
        'model': model_name(),
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
        'stream': False,
    }
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {_cfg("LLM_API_KEY", "")}',
    }
    started = time.time()
    try:
        resp = requests.post(_endpoint(), json=payload, headers=headers,
                             timeout=timeout or timeout_seconds())
    except requests.Timeout as exc:
        raise LLMError(f'调用超时（{timeout or timeout_seconds()}s）') from exc
    except requests.RequestException as exc:
        raise LLMError(f'网络错误：{exc}') from exc

    latency_ms = int((time.time() - started) * 1000)
    if resp.status_code != 200:
        # 把响应体截断后带上：401/402/429 的 body 里通常直接写了原因（余额/鉴权/限流）
        raise LLMError(f'HTTP {resp.status_code}：{(resp.text or "")[:200]}')

    try:
        data = resp.json()
        text = data['choices'][0]['message']['content']
        # 第 204 批：`finish_reason == 'length'` 表示触到了 max_tokens、答案被截断
        finish_reason = str(data['choices'][0].get('finish_reason') or '')
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError(f'响应结构不符合预期：{(resp.text or "")[:200]}') from exc

    usage = data.get('usage') or {}
    actual_model = str(data.get('model') or '')
    configured = model_name()
    if actual_model and actual_model != configured:
        # 不报错、不重试 —— 只留痕。第 192 批实测本端点就会这样（chat → flash）。
        logger.warning('LLM 配置模型 %s，实际落到 %s（端点侧重定向）', configured, actual_model)

    return ChatResult(
        text=(text or '').strip(),
        model=actual_model,
        prompt_tokens=int(usage.get('prompt_tokens') or 0),
        completion_tokens=int(usage.get('completion_tokens') or 0),
        latency_ms=latency_ms,
        finish_reason=finish_reason,
        raw=data,
    )


def chat_stream(messages: list[dict], *, max_tokens: int | None = None,
                temperature: float = 0.2, timeout: float | None = None):
    """流式调用：逐段 yield SSE 事件字典。

    事件种类：`{"text": ...}`（正文增量）/ `{"usage": ...}` / 
    `{"model": ..., "finish_reason": ...}`（**最后一个事件**，第 204 批补 `finish_reason`）。

    `finish_reason == 'length'` 表示**被 max_tokens 截断** —— 上层据此如实告知用户，
    否则界面上就是"半句话 + 看起来答完了"。
    

    ## 为什么用 `iter_lines` 而不是 `iter_content`

    服务端按 SSE 逐行发（`data: {...}\\n\\n`）。`iter_lines` 会按行切分并处理跨包的半行，
    这正是 SSE 需要的；用 `iter_content` 自己拼缓冲区也行，但等于重写一遍。

    ## 为什么错误处理与 `chat()` 不同

    流式一旦开始吐字，**就不能再"整体失败"**了：用户已经看到半句话。
    所以这里的约定是：
      · 连接/HTTP 阶段的错误照旧抛 `LLMError`（此时还没有任何输出，上层可以降级）；
      · **中途**出错只记日志并结束生成 —— 上层把已收到的文本当作答案保存。
        否则会出现"看着在答，突然整段消失"的体验，比半句话更糟。
    """
    if not enabled():
        raise LLMError('LLM 未启用或配置不全（LLM_ENABLED / LLM_API_URL / LLM_API_KEY / LLM_MODEL）')

    if max_tokens is None:
        try:
            max_tokens = int(_cfg('LLM_MAX_TOKENS', 800))
        except (TypeError, ValueError):
            max_tokens = 800

    payload = {
        'model': model_name(),
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
        'stream': True,
        # 让端点在最后一个 chunk 里带 usage（OpenAI 兼容字段）
        'stream_options': {'include_usage': True},
    }
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {_cfg("LLM_API_KEY", "")}',
        'Accept': 'text/event-stream',
    }

    try:
        resp = requests.post(_endpoint(), json=payload, headers=headers,
                             timeout=timeout or timeout_seconds(), stream=True)
    except requests.Timeout as exc:
        raise LLMError(f'调用超时（{timeout or timeout_seconds()}s）') from exc
    except requests.RequestException as exc:
        raise LLMError(f'网络错误：{exc}') from exc

    if resp.status_code != 200:
        detail = ''
        try:
            detail = (resp.text or '')[:200]
        except Exception:  # noqa: BLE001
            pass
        raise LLMError(f'HTTP {resp.status_code}：{detail}')

    configured = model_name()
    actual_model = ''
    finish_reason = ''
    try:
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            line = raw.strip()
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue

            if chunk.get('model'):
                actual_model = str(chunk['model'])
            choices = chunk.get('choices') or []
            if choices:
                delta = (choices[0].get('delta') or {}).get('content')
                if delta:
                    yield {'text': delta}
                # 第 204 批：流式的 finish_reason 出现在**最后一个** chunk 上
                # （通常是空 delta + finish_reason='stop'/'length'）。
                # 原来只取 delta.content，于是"被 max_tokens 截断"这件事完全看不见。
                reason = choices[0].get('finish_reason')
                if reason:
                    finish_reason = str(reason)
            if chunk.get('usage'):
                usage = chunk['usage']
                yield {
                    'usage': {
                        'prompt_tokens': int(usage.get('prompt_tokens') or 0),
                        'completion_tokens': int(usage.get('completion_tokens') or 0),
                    }
                }
    except requests.RequestException as exc:
        # 中途断流：**不抛**，让上层保留已生成的部分（见函数 docstring）
        logger.warning('流式生成中途断开，保留已生成内容：%s', exc)
    finally:
        resp.close()

    if actual_model and actual_model != configured:
        logger.warning('LLM 配置模型 %s，实际落到 %s（端点侧重定向）', configured, actual_model)
    yield {'model': actual_model or configured, 'finish_reason': finish_reason}


def probe() -> dict:
    """连通性自检（给 `check_assistant` 诊断命令用）。**不抛异常**，返回结果字典。"""
    info = {
        'enabled': enabled(),
        'endpoint': _endpoint() if _cfg('LLM_API_URL', '') else '',
        'configured_model': model_name(),
        'key_set': bool(_cfg('LLM_API_KEY', '')),
        'ok': False,
        'error': '',
        'actual_model': '',
        'latency_ms': 0,
        'answer': '',
    }
    if not info['enabled']:
        info['error'] = '未启用或配置不全'
        return info
    try:
        result = chat([{'role': 'user', 'content': '只回四个字：连接正常'}],
                      max_tokens=16, temperature=0, timeout=15)
    except LLMError as exc:
        info['error'] = str(exc)
        return info
    info.update(ok=True, actual_model=result.model, latency_ms=result.latency_ms,
                answer=result.text[:40])
    return info
