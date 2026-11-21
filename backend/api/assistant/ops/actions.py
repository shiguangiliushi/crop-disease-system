"""可逆写工具 —— 系统助手**唯一**能改数据的地方（第 423 批）。

## 与 `tools.py` 的关系：分开，不合并

`tools.py` 的模块说明第一条写着"只读：不写库、不删文件、不改配置"。那不只是风格，
`verify.py` 的命令白名单、`orchestrator._execute()` 的降级矩阵、六条单测都建立在
"`tools.TOOLS` 里全是只读工具"之上。把写工具塞进同一个注册表，等于让
"按名字跑一个工具"这条通用路径突然具备写能力 —— 一次拼错参数就可能改到数据。

所以写工具单独一个注册表（`ACTIONS`），并且**只能**经 `execute()` 执行：
它要求先过 `validate()`、要求目标来自管理员原话、要求落审计。

## 分级：`docs/系统助手框架.md` 的 L3 只开放"可逆"那一半

框架文档按能力分三层：**L1 状态 / L2 归因 / L3 动作**（第 82 行）。本批动的是 L3，
并且只在 L3 里开放**可逆**子集：

| 动作 | 例子 | 本期 |
|---|---|---|
| 可逆写（`reversibility='reversible'`） | 改处理状态、确认/排除样本、写回复 | **本批** |
| 不可逆写 | 删记录、清空历史、删图片文件 | 不做 |

判断标准不是"影响大不大"，而是**能不能靠再执行一次改回去**：把反馈标成已确认，
再标回待确认就复原了；删掉的识别记录与图片文件复原不了。
不可逆写要做得先有"待确认 → 二次确认"的状态机（框架文档 17.4 的后续项），
`ActionSpec.reversibility` 就是留给那一步的开关 —— 现在它只可能等于 `'reversible'`。

## 五条安全约束（缺一条都不许上线）

1. **白名单**：只有 `ACTIONS` 里的三个名字能执行。模型给一个"看起来很像"的名字，
   直接拒绝并留痕，不猜。
2. **目标必须来自管理员原话**：`feedback_id` 必须以 `#12` / `反馈 12` / `12 号反馈`
   这类写法出现在问题里。不校验这一条，模型幻觉一个 id 就能改到无关记录 ——
   这类事故不会报错，只会让"某条反馈莫名其妙变成已处理"。
3. **先校验后执行**：`validate()` 是唯一校验入口，模型的 `tool_calls` 与关键词规则
   两条路都必须过它（一份校验，两个生产者）。
4. **一次一条**：同一轮问答最多执行一次写（`MAX_WRITES`）。没有回滚，做一半更糟。
5. **必落审计**：每次成功写都写 `AdminAuditLog`，动作名在 `ACTIONS[].audit_action`
   里显式声明（`test_every_action_is_reversible_and_audited` 会核对它是否登记过）。
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

from ...audit import log_admin_action
from . import redact
from .intent import id_in_question
from .tools import ToolResult

logger = logging.getLogger(__name__)

#: 一轮问答最多执行几次写。严格为 1：多步写入没有回滚，失败一半比不做更糟。
MAX_WRITES = 1

#: 与 `Feedback.VERIFY_CHOICES` / `Feedback.STATUS_CHOICES` 保持一致。
#: ⚠️ 刻意不 import 模型常量：本模块要在"模型没装好"时也能被导入与单测。
#: 一致性由 `test_action_enums_match_model_choices` 钉住 —— 模型加了取值这里没跟上会红。
VERIFY_VALUES = ('pending', 'confirmed', 'rejected')
STATUS_VALUES = ('pending', 'processing', 'resolved')


@dataclass(frozen=True)
class ActionSpec:
    """一个写工具的静态声明（名字 / 可逆性 / 审计动作 / 给模型的 schema）"""

    name: str
    #: 人读的动作名，答案里复述用（"把反馈 #12 标为已确认"）
    label: str
    #: 可逆性：本期只允许 `'reversible'`。写死在这里，别处无法放宽 ——
    #: 不可逆写要先有"待确认 → 二次确认"的状态机（见模块说明的分级表）。
    reversibility: str
    #: `AdminAuditLog.ACTION_CHOICES` 里的取值
    audit_action: str
    description: str
    properties: dict = field(default_factory=dict)
    required: tuple = ()

    def schema(self) -> dict:
        """OpenAI 兼容的 function schema（`chat(tools=[...])` 直接用）"""
        return {
            'type': 'function',
            'function': {
                'name': self.name,
                'description': self.description,
                'parameters': {
                    'type': 'object',
                    'properties': self.properties,
                    'required': list(self.required),
                },
            },
        }


_VERIFY_PROPERTY = {
    'type': 'string',
    'enum': list(VERIFY_VALUES),
    'description': 'pending=待确认，confirmed=已确认（可进训练集），rejected=已排除',
}
_STATUS_PROPERTY = {
    'type': 'string',
    'enum': list(STATUS_VALUES),
    'description': 'pending=待处理，processing=处理中，resolved=已处理',
}

ACTIONS: dict[str, ActionSpec] = {
    'verify_feedback_sample': ActionSpec(
        name='verify_feedback_sample',
        label='确认/排除训练样本',
        reversibility='reversible',
        audit_action='feedback.verify_sample',
        description=('把一条识别纠错反馈标记为「已确认」或「已排除」，决定它进不进训练集。'
                     '只对可训练样本有效（识别纠错 + 用户判定有误 + 给了正确病害）。'
                     '可逆：随时可以改回 pending。'),
        properties={
            'feedback_id': {'type': 'integer', 'description': '反馈 ID（必须出现在管理员原话里）'},
            'verify_status': _VERIFY_PROPERTY,
        },
        required=('feedback_id', 'verify_status'),
    ),
    'mark_feedback_handled': ActionSpec(
        name='mark_feedback_handled',
        label='流转反馈处理状态',
        reversibility='reversible',
        audit_action='feedback.status',
        description=('把一条反馈的处理状态改成待处理/处理中/已处理。只改状态，不写回复内容。'
                     '可逆。注意：改成「已处理」会给提交人发一条站内通知（与网页端一致）。'),
        properties={
            'feedback_id': {'type': 'integer', 'description': '反馈 ID（必须出现在管理员原话里）'},
            'status': _STATUS_PROPERTY,
        },
        required=('feedback_id', 'status'),
    ),
    'reply_feedback': ActionSpec(
        name='reply_feedback',
        label='回复反馈',
        reversibility='reversible',
        audit_action='feedback.reply',
        description=('给一条反馈写管理员回复正文，并把它流转为「已处理」。'
                     '回复会**发给提交人**（站内通知），所以内容必须是管理员明确要求的原话。'
                     '可逆：再次回复会覆盖，也可只改状态。'),
        properties={
            'feedback_id': {'type': 'integer', 'description': '反馈 ID（必须出现在管理员原话里）'},
            'reply': {'type': 'string', 'description': '要发给提交人的回复正文（管理员原话里的内容）'},
            'status': _STATUS_PROPERTY,
        },
        required=('feedback_id', 'reply'),
    ),
}

#: 给 `llm.chat(tools=...)` 用
TOOL_SCHEMAS: list[dict] = [spec.schema() for spec in ACTIONS.values()]


@dataclass
class Validated:
    """校验通过的写请求 —— `execute()` 只接受它（不是裸 args）"""

    spec: ActionSpec
    args: dict
    #: 人读的目标描述（"反馈 #12 番茄晚疫病"），答案与审计里都用它
    target: str = ''
    #: 本次会改动的字段
    changes: list = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.spec.name


def _as_int(value) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


#: 回复正文的长度上限。**与 `services_feedback.MAX_REPLY_CHARS` 必须一致**
#: （那边是写库前的兜底，这里是给模型/规则的第一道限制），
#: 由 `test_reply_length_matches_service` 钉住。
MAX_REPLY_CHARS = 1000

#: 比较"回复正文是否出现在原话里"时要抹掉的字符（空白与中英文标点）。
#: 管理员写的是"回复 #12：已修复，请升级后重试"，模型抽出来的正文常带/不带结尾标点 ——
#: 不归一化就会因为一个句号把正确的请求拒掉。
_SQUASH = re.compile(r'[\s，,。.：:；;！!？?、（）()「」“”"\'`]+')


def _squash(text: str) -> str:
    return _SQUASH.sub('', text or '')


def validate(name: str, args: dict, *, question: str = '') -> tuple[Validated | None, str]:
    """唯一校验入口。返回 `(Validated | None, 错误说明)`。

    模型给的 `tool_calls` 和关键词规则抽出来的意图都走这里 ——
    校验写两遍的话，第一遍总会比第二遍宽松（这是本项目"双删除口径"的教训）。
    """
    spec = ACTIONS.get(str(name or '').strip())
    if spec is None:
        return None, f'工具 {name} 不在写操作白名单内，已拒绝执行'
    if not isinstance(args, dict):
        return None, f'{name} 的参数不是对象，已拒绝执行'

    feedback_id = _as_int(args.get('feedback_id'))
    if feedback_id is None:
        return None, '缺少有效的反馈 ID（feedback_id）'
    if question and not id_in_question(feedback_id, question):
        # 见模块说明第 2 条：模型幻觉一个 id 就能改到无关记录
        return None, f'反馈 ID {feedback_id} 没有出现在你的原话里，为避免改错记录已拒绝执行'

    changes: list[str] = []
    normalized: dict = {'feedback_id': feedback_id}

    if name == 'verify_feedback_sample':
        value = str(args.get('verify_status') or '').strip()
        if value not in VERIFY_VALUES:
            return None, f'verify_status 只能取 {list(VERIFY_VALUES)} 之一'
        normalized['verify_status'] = value
        changes.append('verify_status')
    elif name == 'mark_feedback_handled':
        value = str(args.get('status') or '').strip()
        if value not in STATUS_VALUES:
            return None, f'status 只能取 {list(STATUS_VALUES)} 之一'
        normalized['status'] = value
        changes.extend(['status', 'handled_at'])
    elif name == 'reply_feedback':
        reply = str(args.get('reply') or '').strip()
        if not reply:
            # 模型没给回复正文时**不许自己编**：这段话会直接发给农户
            return None, '没有给出回复正文，已拒绝执行（回复会直接发给提交人，不能代写）'
        if len(reply) > MAX_REPLY_CHARS:
            return None, f'回复正文超过 {MAX_REPLY_CHARS} 字，请缩短后再试'
        if question and _squash(reply) not in _squash(question):
            # 与 ID 同一条原则：**这段话必须能在管理员原话里找到**。
            # 少了这条，模型可以"顺手润色"出一段没人授权的话发给农户。
            return None, '回复正文在管理员原话里找不到，为避免代写已拒绝执行'
        value = str(args.get('status') or 'resolved').strip() or 'resolved'
        if value not in STATUS_VALUES:
            return None, f'status 只能取 {list(STATUS_VALUES)} 之一'
        normalized['reply'] = reply
        normalized['status'] = value
        changes.extend(['admin_reply', 'status', 'handled_at'])

    return Validated(spec=spec, args=normalized, changes=changes), ''


def _snapshot(feedback) -> dict:
    """写之前的现场（给答案与审计用）。只留状态类字段，**不带正文** ——
    反馈正文是农户写的，会随答案发给外部模型（框架文档 9.1）。"""
    return {
        'status': feedback.status,
        'status_display': feedback.get_status_display(),
        'verify_status': feedback.verify_status,
        'verify_status_display': feedback.get_verify_status_display(),
        'reply_len': len(feedback.admin_reply or ''),
        'handled_at': feedback.handled_at.isoformat() if feedback.handled_at else '',
    }


def _target_of(feedback) -> str:
    """人读目标：`反馈 #12 番茄晚疫病`。病害名是**用户可控**的，所以过脱敏。"""
    name = redact.text(feedback.disease_name or '')[:40]
    return f'反馈 #{feedback.id}' + (f' {name}' if name else '')


def _changed(before: dict, after: dict, changes) -> list[str]:
    """这次**真的**改了哪些字段（值本来就一样的字段不算）。

    `admin_reply` 比的是 `reply_len` 而不是正文：快照里刻意不留回复文本
    （它会被拼进答案/上下文），所以长度变化是这里唯一可用的信号。
    代价是"同样长度换了一句话"看不出来 —— 这种情况极少，且审计里有操作本身。
    """
    out: list[str] = []
    for key in changes:
        if key == 'admin_reply':
            if before.get('reply_len') != after.get('reply_len'):
                out.append(key)
            continue
        if before.get(key) != after.get(key):
            out.append(key)
    return out


def execute(validated: Validated, *, user=None) -> ToolResult:
    """执行一条已校验的写请求：写库 → 落审计 → 返回结构化结果。

    **不抛异常**（与 `tools._tool` 的约定一致）：任何失败都变成 `ok=False`，
    答案里如实说"没改成"，而不是假装成功或整页 500。
    """
    from ...models import Feedback
    from ...services_feedback import (FeedbackWriteError, apply_reply,
                                      apply_sample_verify)

    started = time.time()
    name = validated.name
    feedback_id = int(validated.args['feedback_id'])
    result = ToolResult(name=name, ok=False)
    feedback = Feedback.objects.filter(pk=feedback_id).first()
    if feedback is None:
        result.error = f'反馈 #{feedback_id} 不存在'
        result.ms = int((time.time() - started) * 1000)
        return result

    before = _snapshot(feedback)
    try:
        if name == 'verify_feedback_sample':
            apply_sample_verify(feedback, validated.args['verify_status'])
        elif name == 'mark_feedback_handled':
            apply_reply(feedback, status=validated.args['status'], actor=user or None)
        else:
            apply_reply(feedback, status=validated.args.get('status') or 'resolved',
                        admin_reply=validated.args['reply'], actor=user or None)
    except FeedbackWriteError as exc:
        # 业务拒绝（不可训练样本 / 状态非法）：用户看得懂，原样进答案
        result.error = str(exc)
        result.ms = int((time.time() - started) * 1000)
        return result
    except Exception as exc:  # noqa: BLE001 —— 写库异常也不能让整页 500
        logger.exception('系统助手写操作失败 name=%s feedback=%s', name, feedback_id)
        result.error = redact.text(str(exc) or type(exc).__name__)
        result.ms = int((time.time() - started) * 1000)
        return result

    feedback.refresh_from_db()
    after = _snapshot(feedback)
    target = _target_of(feedback)
    _audit(user, validated, feedback, before, after, target)

    result.ok = True
    result.data = {
        'action': name,
        'label': validated.spec.label,
        'target': target,
        'feedback_id': feedback.id,
        'before': before,
        'after': after,
        'changed': _changed(before, after, validated.changes),
        'reversibility': validated.spec.reversibility,
        'audited': True,
        'audit_action': validated.spec.audit_action,
        'note': '本条操作已写入管理操作日志（action=%s）' % validated.spec.audit_action,
    }
    result.evidence = [{
        'title': validated.spec.label,
        'source': f'{validated.spec.audit_action} · Feedback#{feedback.id}',
        'lines': [
            f'目标：{target}',
            f'处理状态：{before["status"]} → {after["status"]}',
            f'样本状态：{before["verify_status"]} → {after["verify_status"]}',
        ],
    }]
    result.ms = int((time.time() - started) * 1000)
    return result


def _audit(user, validated: Validated, feedback, before: dict, after: dict,
           target: str) -> None:
    """写一条管理操作日志。`log_admin_action` 内部兜异常，失败不会影响已完成的操作。"""
    detail = (f'系统助手自动执行：{validated.spec.label}；'
              f'处理状态 {before["status"]} → {after["status"]}；'
              f'样本状态 {before["verify_status"]} → {after["verify_status"]}')
    log_admin_action(
        user, validated.spec.audit_action,
        target_type='feedback', target_id=str(feedback.id),
        target_repr=target[:200], detail=detail,
    )
