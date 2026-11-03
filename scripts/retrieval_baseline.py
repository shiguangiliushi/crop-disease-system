"""检索质量基线（第 366 批）

## 为什么先测再改

要改检索（例如按「症状 / 用药 / 预防」分块），必须先有一份**基线**，
否则改完无法回答"是变好还是变坏"。

这个脚本拿一批**典型问法**跑 `retriever.search()`，输出：
  · 期望命中的词条（人工标注的答案）
  · 实际 Top-1 / Top-3
  · 是否命中（hit@1 / hit@3）

只用本地 ORM，不联网、不调模型，秒级完成，可随时复跑对比。

## 用法

    python scripts/retrieval_baseline.py            # 表格输出
    python scripts/retrieval_baseline.py --verbose  # 附带每条的打分理由（why）
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')

import django  # noqa: E402

django.setup()

from api.assistant.retriever import search  # noqa: E402

#: (问题, 期望命中的词条；`None` 表示库里**本来就没有**对应词条，
#:          tuple 表示"命中其中任一条都算对"（同病不同名/病毒类）
#:
#: ⚠️ 第一版基线我按"常识"写期望（葡萄白粉病、黄瓜霜霉病、玉米大斑病…），
#: 结果 hit@1 只有 38% —— 查了库才发现**这些词条根本不在 38 条语料里**。
#: 错的不是检索，是测试用例。现在期望值一律以库里实际存在的 38 条为准。
CASES = [
    # ── 有明确对应词条 ──
    ('番茄晚疫病用什么药', '番茄晚疫病'),
    ('番茄叶子背面长白毛怎么办', '番茄晚疫病'),
    ('番茄早疫病和晚疫病怎么区分', '番茄早疫病'),
    ('土豆叶子发黑烂了', '马铃薯晚疫病'),
    ('西红柿果实上有褐色硬斑', '番茄晚疫病'),
    ('柑橘叶片发黄脱落', '柑橘黄龙病'),
    ('草莓叶子边缘焦枯', '草莓叶焦病'),
    ('玉米叶片有铁锈色斑点', '玉米普通锈病'),
    ('苹果叶片背面有橙黄色锈斑', '苹果雪松锈病'),
    ('葡萄果实上有黑褐色小点', ('葡萄黑腐病', '葡萄黑麻疹病')),
    ('番茄叶片上有白色霉层', '番茄叶霉病'),
    ('番茄叶子背面有红蜘蛛', '番茄二斑叶螨'),
    ('甜椒叶片有细菌性斑点', '甜椒细菌性斑点病'),
    ('番茄病毒病怎么传播', ('番茄花叶病毒', '番茄黄化曲叶病毒')),
    ('what causes tomato late blight', '番茄晚疫病'),
    ('how to prevent tomato leaf mold', '番茄叶霉病'),
    # ── 库里没有对应词条（期望"答不上来"，不能硬凑一个病害） ──
    ('黄瓜霜霉病怎么治', None),
    ('葡萄叶片背面有白粉', None),
    ('苹果树皮腐烂怎么办', None),
    ('草莓灰霉病怎么预防', None),
    ('玉米大斑病症状', None),
    ('小麦锈病用什么药', None),
    ('茄子黄萎病', None),
    ('茶叶叶子有黑斑', None),
    ('桃子流胶是什么病', None),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', action='store_true', help='打印每条的命中理由')
    parser.add_argument('--top', type=int, default=3)
    args = parser.parse_args()

    hit1 = hit3 = total_expected = 0
    no_answer_ok = 0
    no_answer_total = 0
    rows = []

    for question, expected in CASES:
        hits = search(question)[: args.top]
        names = [hit.pest.name for hit in hits]
        scores = [round(hit.score, 0) for hit in hits]

        expected_names = (expected,) if isinstance(expected, str) else (expected or ())

        if expected is None:
            no_answer_total += 1
            # 期望"没有明确答案"：Top-1 分数很低（<15）就算符合预期
            ok = bool(hits) and hits[0].score < 15 or not hits
            if ok:
                no_answer_ok += 1
        else:
            total_expected += 1
            ok1 = bool(names) and names[0] in expected_names
            ok3 = any(name in expected_names for name in names)
            hit1 += 1 if ok1 else 0
            hit3 += 1 if ok3 else 0
            rows.append((question, '/'.join(expected_names), names[0] if names else '(无)',
                         ok1, ok3, scores))

    print(f'用例总数 {len(CASES)}：有标准答案 {total_expected} 条，期望无答案 {no_answer_total} 条\n')
    print(f'{"问题":32} {"期望":14} {"实际Top1":14} "hit@1" "hit@3"')
    for question, expected, top1, ok1, ok3, _scores in rows:
        print(f'{question[:30]:32} {expected:14} {top1:14} '
              f'{"✓" if ok1 else "✗":4} {"✓" if ok3 else "✗"}')

    print()
    if total_expected:
        print(f'hit@1 = {hit1}/{total_expected} = {hit1 / total_expected:.0%}')
        print(f'hit@3 = {hit3}/{total_expected} = {hit3 / total_expected:.0%}')
    if no_answer_total:
        print(f'"本该答不上来"判对 = {no_answer_ok}/{no_answer_total}')

    if args.verbose:
        print('\n--- 命中理由 ---')
        for question, _expected in CASES:
            hits = search(question)[: args.top]
            if hits:
                print(f'{question[:28]:30}', ' | '.join(
                    f'{hit.pest.name}({hit.score:.0f}: {hit.why[0] if hit.why else ""})' for hit in hits))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
