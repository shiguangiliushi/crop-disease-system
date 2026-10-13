"""
`manage.py role_matrix [用户名]` —— 权限矩阵自查（第 178 批）
================================================================================

## 用途

1. **不带参数**：打印"谁能做什么"的完整矩阵（角色 → 能力 → 模块 → 接口清单）。
   表来自 `api/role_matrix.py`，与代码/测试/文档**同一份来源**。
2. **带用户名**：打印**这个账号此刻**的实际权限 —— 能力、被勾的内容模块、
   能进哪几页、每个接口允许还是被拒。用来回答最常见的那类问题：
   "我明明给他勾了新闻管理，他怎么还是看不到？"
3. **`--write-docs`**：把矩阵写成 `docs/角色与权限矩阵.md`（文档不再是手抄的，
   改了表重新生成即可）。

## 为什么值得单独做一个命令

权限这块的信息原本散在三处（视图体里的 26 处判定、前端侧栏、零散注释），
出问题时只能翻代码。现在"一处表 + 一个命令 + 一个测试"：
表是唯一来源，命令给人看，测试保证表没烂。

用法：
    python manage.py role_matrix
    python manage.py role_matrix someone
    python manage.py role_matrix --write-docs
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from api.capabilities import ALL_CAPABILITIES, CONTENT_MODULES, MODULE_LABELS
from api.role_matrix import (
    CAPABILITY_PAGES, COMMON_PAGES, ENDPOINT_RULES, FULL_ADMIN_PAGES, MODULE_PAGES,
    ROLE_NOTES, allowed, describe_user,
)

User = get_user_model()

#: ⚠️ 相对路径会跟着**当前工作目录**跑：从 backend/ 执行 `manage.py` 时，
#:    `docs/...` 会被写到 `backend/docs/`（我第一次就是这样，文档跑到了错的地方，
#:    提交时 pathspec 不存在才发现）。这里锚定 Django 的 BASE_DIR（= backend/），
#:    再上一级就是仓库根 —— 无论从哪个目录执行都写到同一个地方。
DOC_PATH = settings.BASE_DIR.parent / 'docs' / '角色与权限矩阵.md'


class Command(BaseCommand):
    help = '打印/自查权限矩阵（信息编辑员各自能做什么）；--write-docs 生成文档'

    def add_arguments(self, parser):
        parser.add_argument('username', nargs='?', help='只看这个账号的实际权限')
        parser.add_argument('--write-docs', action='store_true',
                            help='把矩阵写成 docs/角色与权限矩阵.md')

    def handle(self, *args, **options):
        if options['write_docs']:
            self._write_docs()
            return
        username = options.get('username')
        if username:
            self._describe(username)
            return
        self._matrix()

    # -- ① 完整矩阵 ---------------------------------------------------------
    def _matrix(self):
        self.stdout.write(self.style.MIGRATE_HEADING('角色 × 能力'))
        for role, note in ROLE_NOTES.items():
            self.stdout.write(f'  {role:<8} {note}')

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('内容模块 × 能进的页面'))
        for module in CONTENT_MODULES:
            pages = '、'.join(MODULE_PAGES.get(module, [])) or '（无）'
            self.stdout.write(f'  {module:<10} {MODULE_LABELS.get(module, module):<8} {pages}')

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('非内容能力 / 全权 的页面'))
        for capability, pages in CAPABILITY_PAGES.items():
            self.stdout.write(f'  {capability:<12} {"、".join(pages)}')
        self.stdout.write(f'  {"（所有人）":<12} {"、".join(COMMON_PAGES)}')
        self.stdout.write(f'  {"FULL_ADMIN":<12} {"、".join(FULL_ADMIN_PAGES)}')

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'接口矩阵（{len(ENDPOINT_RULES)} 条，★ = 仅全权管理员）'))
        for method, path, allow, note in ENDPOINT_RULES:
            flag = '★' if allow == ('FULL_ADMIN',) else ' '
            self.stdout.write(f' {flag} {method:<6} {path:<44} {"|".join(allow):<18} {note}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            '提示：带用户名跑一次（如 role_matrix someone）可以看某个账号的实际权限；'
            '--write-docs 生成 docs/角色与权限矩阵.md'))

    # -- ② 某个账号的实际权限 -------------------------------------------------
    def _describe(self, username):
        user = User.objects.filter(username=username).first()
        if user is None:
            raise CommandError(f'没有这个账号：{username}')

        info = describe_user(user)
        self.stdout.write(self.style.MIGRATE_HEADING(f'{username} 的权限'))
        self.stdout.write(f'  角色          {info["role"]}'
                          f'{"" if info["is_full_admin"] else "（非全权管理员）"}')
        self.stdout.write(f'  能力          {"、".join(info["capabilities"]) or "（无）"}'
                          f'{"（全权）" if info["is_full_admin"] else ""}')
        self.stdout.write(f'  内容模块      {"、".join(info["modules"]) or "（一个都没有）"}')
        self.stdout.write(f'  能进的管理页  {"、".join(info["pages"]) or "（进不了后台）"}')

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('接口逐条判定'))
        for method, path, allow, note in ENDPOINT_RULES:
            ok = allowed(allow, info['matrix_caps'], info['modules'])
            mark = self.style.SUCCESS('允许') if ok else self.style.ERROR('拒绝')
            self.stdout.write(f'  {mark}  {method:<6} {path:<44} {note}')

        if not info['is_full_admin'] and info['role'] == 'EDITOR' and not info['modules']:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                '⚠️ 这个账号是信息编辑员，但一个内容模块都没勾 —— '
                '他登录后侧栏只有一个「数据看板」。到用户管理页给他勾模块。'))

    # -- ③ 生成文档 ----------------------------------------------------------
    def _write_docs(self):
        lines = [
            '# 角色与权限矩阵',
            '',
            '> 本文件由 `python manage.py role_matrix --write-docs` **生成**，请勿手改。',
            '> 唯一来源：`backend/api/role_matrix.py`（表）+ `backend/api/capabilities.py`（判定）。',
            '> 一致性由 `api.tests.RoleMatrixTests` 保证：表与代码不一致时测试会红。',
            '',
            '## 一、三个角色',
            '',
            '| 角色 | 说明 |',
            '|---|---|',
        ]
        for role, note in ROLE_NOTES.items():
            lines.append(f'| `{role}` | {note} |')

        lines += [
            '',
            '## 二、信息编辑员：五个内容模块各自能做什么',
            '',
            '授权方式：在控制台「用户管理」里开通编辑员并勾选模块（写进 `EditorModuleGrant` 表）。',
            '**全权管理员四个模块全有**（不查授权表）；编辑员只有被勾的那些；其余账号一个都没有。',
            '',
            '| 模块 | 名称 | 能进的管理页 |',
            '|---|---|---|',
        ]
        for module in CONTENT_MODULES:
            pages = '、'.join(MODULE_PAGES.get(module, [])) or '（无）'
            lines.append(f'| `{module}` | {MODULE_LABELS.get(module, module)} | {pages} |')

        lines += [
            '',
            '⚠️ 两个模块在"评论与帖子"上是**或**的关系：勾了「内容审核」**或**「论坛交流」都能管'
            '（`review` 是宽口径，老账号不会因为拆分掉权限）。',
            '',
            '## 三、非内容能力与"仅全权管理员"',
            '',
            '| 能力/标记 | 能进的管理页 | 说明 |',
            '|---|---|---|',
        ]
        for capability, pages in CAPABILITY_PAGES.items():
            desc = ('用户账号与他人数据（含跨用户识别记录）' if capability == 'USER_ADMIN'
                    else '对全体用户发声与系统开关（公告/预警/敏感词/版块）')
            lines.append(f'| `{capability}` | {"、".join(pages)} | {desc} |')
        lines.append(f'| （任何能进后台的人） | {"、".join(COMMON_PAGES)} | 只读聚合，没有他人明细 |')
        lines.append(f'| `FULL_ADMIN` | {"、".join(FULL_ADMIN_PAGES)} | 会暴露部署细节或"谁对谁做了什么" |')

        lines += [
            '',
            '**不可逆动作一律只给全权管理员**（不塞进任何模块）：',
            '删除意见反馈、彻底删除评论 —— 见 `capabilities.py` 的说明。',
            '',
            '## 四、接口矩阵',
            '',
            '★ = 仅全权管理员。判定语义：`allow` 里**任一命中**即可（与代码里的 `or` 一致）。',
            '',
            '| | 方法 | 接口 | 允许 | 说明 |',
            '|---|---|---|---|---|',
        ]
        for method, path, allow, note in ENDPOINT_RULES:
            flag = '★' if allow == ('FULL_ADMIN',) else ''
            lines.append(f'| {flag} | `{method}` | `{path}` | {"、".join(allow)} | {note} |')

        lines += [
            '',
            '## 五、自查',
            '',
            '```bash',
            'python manage.py role_matrix                 # 打印完整矩阵',
            'python manage.py role_matrix <用户名>        # 这个账号到底能干什么',
            'python manage.py role_matrix --write-docs    # 重新生成本文件',
            '```',
            '',
            '最常用来回答的问题是"我明明给他勾了新闻管理，他怎么还是看不到" —— '
            '跑一次带用户名的自查，能直接看到他此刻的能力、模块与逐条接口判定。',
            '',
        ]

        path = DOC_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
        self.stdout.write(self.style.SUCCESS(
            f'已写入 {DOC_PATH.relative_to(settings.BASE_DIR.parent)}（{len(lines)} 行）'))
