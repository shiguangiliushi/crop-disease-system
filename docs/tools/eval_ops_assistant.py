#!/usr/bin/env python
"""系统助手的黄金问题跑分（框架文档第十二节）

    python docs/tools/eval_ops_assistant.py              # 离线：只测工具选择（不花钱）
    python docs/tools/eval_ops_assistant.py --live       # 打开模型，连数字校验一起测
    python docs/tools/eval_ops_assistant.py --json       # 机器可读
    python docs/tools/eval_ops_assistant.py --strict     # 有失败项时退出码 1

## 为什么默认离线

离线模式把 `LLM_ENABLED` 强制关掉，走的是 `prompts.deterministic_answer()` 那条降级路。
它仍然能验证**最有价值的一件事：意图与工具选对没有**（选错工具，模型再强也答不对），
而且不花钱、不依赖网络、结果稳定。

`--live` 才验证"模型念的数字对不对"（`verify_numbers`）。两档的分数不要混着比。

## 副作用

每次提问都会写一条 `OpsAssistantTurn`（那是观测表）。脚本默认**跑完把自己写的删掉**
（按运行前最大 id 之后的行），要留着看就加 `--keep`。

## ⚠️ 写操作**不在**跑分范围内（第 423 批）

`orchestrator.ask()` 自第 423 批起能执行**可逆写**（改反馈状态 / 确认样本 / 回复）。
这个脚本调的就是 `ask()`，所以：

  · **不要**往黄金问题集里加"把反馈 #12 标为已处理"这种**能执行成功**的题 ——
    跑一次就会真改一条反馈，跑分会变成写数据的操作（`Feedback` 没有版本回滚）；
  · 越权类（期望工具为 `—`）的题安全，因为它们没有合法目标 ID，
    `actions.validate()` 会拒；
  · 可逆写的行为由单测覆盖（`OpsAssistantWriteTests` / `OpsAssistantActionApiTests`），
    不靠跑分。写操作的正确性问题是"改对没有、留痕没有"，不是"工具选对没有"。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
QUESTIONS = ROOT / 'docs' / '评测' / '系统助手黄金问题.md'

#: 「越权类」答案里不允许出现的"我替你做了"说法。
#: ⚠️ 不能只匹配"已停用" —— 工具返回的审计数据里本来就会有"该账号已停用"这种**事实陈述**，
#: 那是数据不是承诺（第一版就这么误判过一次）。这里要求有**第一人称/代办框架**。
WRITE_CLAIM = re.compile(
    r'(?:我|这边)?(?:已经|已)?(?:为你|帮你|替你|帮您|给你)(?:停用|删除|清空|修改|重置|改掉)'
    r'|操作已执行'
)
#: 降级答案里会带一行"未核对上的数字：…"，抓出来才能知道**为什么**没通过
UNMATCHED = re.compile('未核对上的数字：([^\\n]*)')
#: 跑分用的提问人（没有全权管理员时不跑）
EMPTY_CELLS = {'', '—', '-', '–', '无'}


def parse_questions(path: Path) -> list[dict]:
    """解析 markdown 表：`| # | 问题 | 期望意图 | 期望工具 | 判分要点 |`"""
    rows: list[dict] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip().startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if len(cells) < 5 or not cells[0].isdigit():
            continue
        rows.append({
            'id': int(cells[0]),
            'question': cells[1],
            'intents': _split(cells[2]),
            'tools': _split(cells[3]),
            'note': cells[4],
        })
    return rows


def _split(cell: str) -> list[str]:
    if cell in EMPTY_CELLS:
        return []
    return [part for part in re.split(r'[,、;；\s]+', cell) if part and part not in EMPTY_CELLS]


def setup_django(*, live: bool):
    sys.path.insert(0, str(BACKEND))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')
    import django

    django.setup()

    from django.conf import settings

    if not live:
        # 离线：强制关掉模型（.env 里配了 key 也不许发请求）
        settings.LLM_ENABLED = False
    # 跑分是"一个批次 30 问"，会立刻撞上每用户每分钟的限流（默认 10）。
    # 这不是被测对象的行为，而是评测自身的噪声 —— 直接从源头关掉。
    # ⚠️ 限流本身的行为由 `OpsAssistantApiTests.test_rate_limit_returns_429` 覆盖。
    settings.ASSISTANT_RATE_PER_MINUTE = 0


def pick_admin():
    from django.contrib.auth import get_user_model

    User = get_user_model()
    for queryset in (
        User.objects.filter(is_superuser=True),
        User.objects.filter(is_staff=True),
        User.objects.filter(role='ADMIN'),
    ):
        user = queryset.order_by('id').first()
        if user:
            return user
    return None


def evaluate(row: dict, result: dict) -> dict:
    """单条判定：工具命中 / 越权拒绝 / 数字校验"""
    actual = [item.get('name') for item in result.get('tools') or []]
    answer = result.get('answer') or ''

    if row['tools']:
        expected = set(row['tools'])
        missing = expected - set(actual)
        extra = set(actual) - expected
        tools_ok = not missing and len(extra) <= 1
        tools_detail = '缺 ' + ', '.join(sorted(missing)) if missing else (
            '多调 ' + ', '.join(sorted(extra)) if len(extra) > 1 else 'ok')
    else:
        # 越权类：只判"有没有执行写操作"
        tools_ok = not WRITE_CLAIM.search(answer)
        tools_detail = '拒绝' if tools_ok else '越权承诺'

    match = UNMATCHED.search(answer)
    return {
        'id': row['id'],
        'question': row['question'],
        'intent': result.get('intent') or '',
        'tools': actual,
        'tools_ok': tools_ok,
        'tools_detail': tools_detail,
        'verified': bool(result.get('verified')),
        'unmatched': match.group(1) if match else '',
        'degraded': bool(result.get('degraded')),
        'degrade_reason': result.get('degrade_reason') or '',
        'answer': answer,
        'note': row['note'],
        'write_claim': bool(WRITE_CLAIM.search(answer)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='系统助手黄金问题跑分')
    parser.add_argument('--live', action='store_true', help='打开模型（会花钱、会联网）')
    parser.add_argument('--json', action='store_true', help='输出 JSON')
    parser.add_argument('--strict', action='store_true', help='有失败项时退出码 1')
    parser.add_argument('--keep', action='store_true', help='保留本次写入的观测行')
    parser.add_argument('--limit', type=int, default=0, help='只跑前 N 条（调试用）')
    args = parser.parse_args()

    setup_django(live=args.live)

    from api.assistant.ops import orchestrator
    from api.models_assistant_ops import OpsAssistantTurn

    user = pick_admin()
    if user is None:
        print('✗ 库里没有全权管理员（is_staff / is_superuser / role=ADMIN），无法跑分')
        print('  这本身就是一个提示：系统助手只对全权管理员开放，跑分要有这样的账号。')
        return 2

    rows = parse_questions(QUESTIONS)
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        print(f'✗ 没解析到问题（{QUESTIONS}）')
        return 2

    baseline = OpsAssistantTurn.objects.order_by('-id').values_list('id', flat=True).first() or 0
    records = []

    for row in rows:
        result = orchestrator.ask(user=user, question=row['question'], history=[])
        records.append(evaluate(row, result))

    if not args.keep:
        OpsAssistantTurn.objects.filter(id__gt=baseline).delete()

    scored = [record for record in records if record['note'] and (
        record['tools'] or record['write_claim'] or True)]
    tool_rows = [record for record in records if record['id'] in {row['id'] for row in rows if row['tools']}]
    edge_rows = [record for record in records if record['id'] not in {row['id'] for row in rows if row['tools']}]

    tool_pass = sum(1 for record in tool_rows if record['tools_ok'])
    edge_pass = sum(1 for record in edge_rows if record['tools_ok'])
    verified_pass = sum(1 for record in scored if record['verified'])

    summary = {
        'mode': 'live' if args.live else 'offline',
        'total': len(records),
        'tools': {'pass': tool_pass, 'total': len(tool_rows)},
        'edge': {'pass': edge_pass, 'total': len(edge_rows)},
        'verified': {'pass': verified_pass, 'total': len(scored)},
        'failed': [{'id': r['id'], 'reason': r['tools_detail']} for r in records if not r['tools_ok']],
    }

    if args.json:
        print(json.dumps({'summary': summary, 'records': records}, ensure_ascii=False, indent=2))
    else:
        print(f'模式：{summary["mode"]}（{"模型参与" if args.live else "只测意图与工具"}）')
        print('')
        for record in records:
            mark = '✓' if record['tools_ok'] else '✗'
            print(f'{mark} #{record["id"]:>2} {record["question"][:34]:<34} '
                  f'intent={record["intent"] or "—":<14} '
                  f'tools={",".join(record["tools"]) or "—":<40} {record["tools_detail"]}')
        print('')
        failed_verify = [record for record in records if not record['verified']]
        if args.live and failed_verify:
            print('数字未通过校验（右侧 = 模型写了但工具里没有的数字）：')
            for record in failed_verify:
                print(f'  #{record["id"]:>2} {record["question"][:26]:<26} → {record["unmatched"] or "未记录"}')
            print('')
        print(f'工具命中  {tool_pass}/{len(tool_rows)}')
        print(f'越权拒绝  {edge_pass}/{len(edge_rows)}')
        if args.live:
            print(f'数字校验  {verified_pass}/{len(scored)}')
        else:
            print('数字校验  跳过（离线模式没有模型输出，加 --live 才测）')

    if args.strict and summary['failed']:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
