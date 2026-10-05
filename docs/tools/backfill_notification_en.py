"""回填历史站内通知的英文标题（第 72 批）

站内通知的标题是后端按模板拼装的中文（"xxx 回复了你的帖子：yyy"）。
第 72 批给 `notify()` 加了 `title_en`/`message_en`，**新通知**都会带英文；
但升级前已经存在的通知没有英文版本，英文界面下仍显示中文。

本脚本按标题的中文模板反向还原英文，幂等（只填空字段）。
用法：
    python docs/tools/backfill_notification_en.py
    python docs/tools/backfill_notification_en.py --force
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crop_disease_backend.settings')

import django  # noqa: E402

django.setup()

from api.models_notify import Notification  # noqa: E402

# (正则, 英文模板) —— 顺序即优先级，越具体的放前面
PATTERNS = [
    (r'^有新的待审核帖子：(?P<x>.+)$', 'New post awaiting review: {x}'),
    (r'^你的帖子已通过审核：(?P<x>.+)$', 'Your post was approved: {x}'),
    (r'^你的帖子未通过审核：(?P<x>.+)$', 'Your post was rejected: {x}'),
    (r'^新的专家咨询：(?P<x>.+)$', 'New expert question: {x}'),
    (r'^(?P<u>[^ ]+) 回答了你的问题：(?P<x>.+)$', '{u} answered your question: {x}'),
    (r'^你的回答被采纳了：(?P<x>.+)$', 'Your answer was accepted: {x}'),
    (r'^收到新的举报：(?P<x>.+)$', 'New report received: {x}'),
    (r'^你的举报已处理$', 'Your report was handled'),
    (r'^你的举报已驳回$', 'Your report was rejected'),
    (r'^病害预警：(?P<x>.+)$', 'Disease alert: {x}'),
    (r'^(?P<u>[^ ]+) 收藏了你的帖子：(?P<x>.+)$', '{u} favourited your post: {x}'),
    (r'^(?P<u>[^ ]+) 点赞了你的帖子：(?P<x>.+)$', '{u} liked your post: {x}'),
    (r'^(?P<u>[^ ]+) 回复了你的帖子：(?P<x>.+)$', '{u} replied to your post: {x}'),
    (r'^(?P<u>[^ ]+) 点赞了你的评论$', '{u} liked your comment'),
    (r'^(?P<u>[^ ]+) 给你发了私信$', '{u} sent you a private message'),
    (r'^(?P<u>[^ ]+) 关注了你$', '{u} started following you'),
    (r'^你已被设为平台专家$', 'You have been granted expert status'),
]

MESSAGES = [
    (r'^(?P<u>[^ ]+) 在「(?P<b>.+)」发布了新帖，等待审核$',
     '{u} posted in "{b}" and it is waiting for review'),
    (r'^现在其他用户可以看到这篇帖子了$', 'Other users can now see this post'),
]


def translate(title, table):
    for pattern, template in table:
        m = re.match(pattern, title or '')
        if m:
            return template.format(**{k: v for k, v in m.groupdict().items() if v is not None})
    return ''


def main():
    force = '--force' in sys.argv
    done = 0
    unmatched = []

    for note in Notification.objects.all():
        fields = []
        if force or not note.title_en:
            en = translate(note.title, PATTERNS)
            if en:
                note.title_en = en[:200]
                fields.append('title_en')
            elif note.title:
                unmatched.append(note.title)
        if force or not note.message_en:
            en = translate(note.message, MESSAGES)
            if en:
                note.message_en = en[:500]
                fields.append('message_en')
        if fields:
            note.save(update_fields=fields)
            done += 1

    print(f'通知：回填 {done} 条，仍缺英文标题 {Notification.objects.filter(title_en="").count()} 条')
    if unmatched:
        print('以下标题没有匹配到模板（需要补进 PATTERNS）：')
        for item in sorted(set(unmatched))[:20]:
            print('  -', item)


if __name__ == '__main__':
    main()
