"""助手"看图"（第 229 批）：把一张上传的图片变成**可检索、可引用**的事实。

## 为什么这一版是"本地识别 + RAG"，而不是接一个视觉大模型

项目里已经有一个训练好的 YOLOv8（39 类、离线、零成本），识别页用的就是它。
接真 VLM（qwen-vl / glm-4v / 豆包视觉）能回答"叶子上这块斑是什么形状"这种细粒度问题，
但要新 key、按张计费，而且结论可能和识别页给出的不一样 —— 同一个产品里两种说法是最糟的。

所以这一版先用**本地识别当"眼睛"**：

    图片 → 病害名 + 置信度 → 作为检索锚点 + 写进提示词 → 回答只引用站内词条

这守住了项目那条硬约定"**无来源不回答**"：模型不会被允许只凭一张图自由发挥。

将来要换成 VLM，只需要另写一个同签名的 `describe()`（`source` 改成 'vlm'），
`orchestrator` 与前端都不用动 —— 这也是这里把"识别"和"编排"分开的原因。

## 图片不落盘

图片只在本次请求内用于识别，**不存**（也不进 `media/`）：
  · 助手的价值是"回答"，不是"相册"；识别记录另有专门入口（`/detect` → 识别历史）；
  · 落盘就要配套清理策略（`prune_media` 目前只认识别图与新闻图），漏一次就是磁盘垃圾。
会话里只留一句 `image_summary`（"图片识别：番茄晚疫病 99%"），历史因此仍然读得懂。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import prompts

logger = logging.getLogger(__name__)

#: 识别来源（写进 `image_summary` 前面，将来接 VLM 时这里会是 'vlm'）
SOURCE_LOCAL = 'local-yolo'

#: 只传图不打字时的默认问题（先问"怎么了"，比空问题有用）
DEFAULT_QUESTIONS = {
    'zh': '这张图片里的作物怎么了？',
    'en': 'What is wrong with the crop in this photo?',
}


@dataclass
class VisionResult:
    """一次"看图"的结论。"""

    #: success / healthy / not_found / error
    status: str
    #: 模型给出的类名（如 `Tomato___Late_dighter`），成功与"未收录"时都有值
    identifier: str = ''
    confidence: float = 0.0
    #: 匹配到的站内词条（None = 词库没有）
    pest: object = None
    #: 模型/异常给的原始说明（中文，直接展示给用户）
    message: str = ''
    source: str = SOURCE_LOCAL
    #: 置信度低到无法确认时，模型会走 not_found；这里保留它给用户看
    extra: dict = field(default_factory=dict)

    @property
    def matched(self) -> bool:
        return self.pest is not None


def default_question(lang: str = prompts.DEFAULT_LANG) -> str:
    return DEFAULT_QUESTIONS[prompts.normalize_lang(lang)]


def describe(image_file, *, lang: str = prompts.DEFAULT_LANG) -> VisionResult:
    """跑一次识别，返回结论。**不抛异常**（失败也翻译成 status=error）。"""
    code = prompts.normalize_lang(lang)
    if image_file is None:
        return VisionResult(status='error', message='没有收到图片文件')

    try:
        from ..ai_service import get_ai_service

        service = get_ai_service()
        raw = service.predict(image_file) or {}
    except Exception as exc:  # noqa: BLE001 —— 识别失败不该让问答 500
        logger.exception('助手看图：识别调用失败')
        return VisionResult(status='error', message=f'识别服务暂时不可用（{exc}）')

    status = str(raw.get('status') or 'error')
    identifier = str(raw.get('identifier') or '')
    confidence = float(raw.get('confidence') or 0.0)
    message = str(raw.get('message') or '')

    result = VisionResult(
        status=status, identifier=identifier, confidence=confidence,
        message=message, extra={'class_name': raw.get('class_name') or ''},
    )

    if status == 'success' and identifier:
        try:
            from ..pest_lookup import find_pest_info

            pest, why = find_pest_info(identifier)
            result.pest = pest
            if pest is None:
                logger.info('助手看图：类名 %s 在词库里没有词条（%s）', identifier, why)
        except Exception:  # noqa: BLE001 —— 匹配失败最多是"没锚点"，不该整条链路失败
            logger.exception('助手看图：类名映射词条失败')
    return result


def summary(result: VisionResult, lang: str = prompts.DEFAULT_LANG) -> str:
    """一行摘要，落进 `AssistantMessage.image_summary`（会话历史里要读得懂）。"""
    code = prompts.normalize_lang(lang)
    percent = round(result.confidence * 100)
    label = _label_of(result, code)

    if result.status == 'success' and result.matched:
        return (f'图片识别：{label}（{percent}%）' if code == 'zh'
                else f'Photo: {label} ({percent}%)')
    if result.status == 'healthy':
        return '图片识别：未检出病斑（判为健康）' if code == 'zh' else 'Photo: no lesion detected (healthy)'
    if result.status == 'success':
        return (f'图片识别：{label}（{percent}%，词条未收录）' if code == 'zh'
                else f'Photo: {label} ({percent}%, no wiki entry)')
    return '图片识别：未得出结论' if code == 'zh' else 'Photo: inconclusive'


def observation_text(result: VisionResult, lang: str = prompts.DEFAULT_LANG) -> str:
    """写进提示词知识区的"观察"段落。

    为什么要明写"这是识别结果、不是用户说的"：模型看到一段"番茄晚疫病"很容易
    把它当成用户的原话，回答里冒出"你刚才说…"。这里用【图片识别结果】标注来源。
    """
    code = prompts.normalize_lang(lang)
    percent = round(result.confidence * 100)
    label = _label_of(result, code)

    if result.status == 'success' and result.matched:
        return (f'【图片识别结果】模型判为「{label}」，置信度 {percent}%，已匹配站内词条。'
                if code == 'zh'
                else f'[Photo recognition] The model identified "{label}" '
                     f'with {percent}% confidence; a wiki entry was matched.')
    if result.status == 'success':
        return (f'【图片识别结果】模型判为 `{result.identifier}`（{percent}%），'
                '但词库里没有对应词条 —— 只能按作物与症状的一般规律回答，并说明这一点。'
                if code == 'zh'
                else f'[Photo recognition] The model identified `{result.identifier}` '
                     f'({percent}%), but no wiki entry matches it — answer from general '
                     'crop/symptom knowledge and say so explicitly.')
    if result.status == 'healthy':
        return (f'【图片识别结果】未检出病斑，模型判为健康（置信度 {percent}%）。'
                if code == 'zh'
                else f'[Photo recognition] No lesion detected; the model says healthy ({percent}%).')
    return (f'【图片识别结果】没有得出结论：{result.message}'
            if code == 'zh' else f'[Photo recognition] Inconclusive: {result.message}')


def failure_text(result: VisionResult, lang: str = prompts.DEFAULT_LANG) -> str:
    """看不了这张图时直接回答的话术（不调模型）。"""
    code = prompts.normalize_lang(lang)
    reason = (result.message or '').strip()
    if code == 'zh':
        head = '这张图片我没能认出来'
        tail = '建议把叶片放满画面中间、避开杂乱背景，在自然光下重拍一张；也可以直接在「病害识别」页拍照识别。'
        return f'{head}：{reason}。\n{tail}' if reason else f'{head}。{tail}'
    head = "I couldn't recognise anything in this photo"
    tail = ('Please fill the frame with a single leaf, avoid clutter and glare, and retake it — '
            'or use the “Diagnose” page, which runs the same detector.')
    return f'{head}: {reason}.\n{tail}' if reason else f'{head}. {tail}'


def _label_of(result: VisionResult, lang: str) -> str:
    """展示名：优先词条名（按语言），否则用类名里可读的一段。"""
    pest = result.pest
    if pest is not None:
        if lang == 'en':
            return pest.name_en or pest.name or result.identifier
        return pest.name or result.identifier
    raw = (result.identifier or '').replace('___', ' ').replace('_', ' ').strip()
    return raw or '未知'
