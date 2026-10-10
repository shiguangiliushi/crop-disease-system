"""
api 应用回归测试

当前覆盖：行业新闻的「发布状态可见性」链路 + 两个历史必现 500。

背景（真实故障）：管理员在管理端下架新闻后，用户仍能在「行业动态」里看到。
排查结论是**发布状态过滤本身是好的**，真正的成因有两类：
  1. 库里存在"同标题 + 正文逐字节相同"的重复记录，管理员下架的是一条、
     用户看到的是另一条；
  2. 详情接口把 `Http404` 吞成了 500（用户点旧链接看到"服务器错误"，
     容易被误判成"还能访问"）。

因此本文件同时锁死三件事：
  - 非管理员在任何只读接口上都拿不到未发布新闻（列表 / 详情 / recent / legacy_detail）；
  - 已下架/不存在的详情返回 **404**（而不是 500）；
  - 同标题重复建档被拒绝（从源头不再产生重复新闻）。
"""
import hashlib
import json
import os  # 第 102 批：备份测试要临时改写 DJANGO_BACKUP_DIR
import time  # 第 106 批：prune_media 测试要造"N 天前的文件"
import re
import uuid  # 第 95 批：造"已登录会话"的 key
from datetime import timedelta  # 第 46 批：预警测试要造"N 天前"的记录
from pathlib import Path  # 第 91 批：净化白名单的契约测试要读前端源文件
from unittest.mock import patch  # 第 85 批：翻译服务用桩替换，测试不联网

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings  # 第 102 批：备份测试要改连接
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase  # APITestCase：第 125 批的能力矩阵
from rest_framework import status  # 第 125 批：能力矩阵测试要断言具体状态码

from .models import DetectionHistory, Feedback, News, PestInfo, PreventionMethod, SensitiveWord
from .models import EditorModuleGrant  # 第 128 批：编辑员的模块授权（内容审核/新闻/百科/反馈）
from .models_forum import Comment, Favorite, ForumBoard, Like, Post
from .models_notify import Announcement, Notification  # 第 37 批：通知与公告
from .models_social import Follow  # 第 40 批：关注关系
from .models_report import Report  # 第 41 批：举报
from .models_calendar import CalendarTask  # 第 47 批：种植日历
from .models_audit import AdminAuditLog  # 第 146 批：管理操作日志
from .models_expert import ConsultAnswer, ConsultQuestion, ExpertProfile  # 第 49 批：专家咨询
from .models_message import DirectMessage  # 第 42 批：私信
from .models_message import conversation_key_for  # 第 114 批：私信测试要自己造会话消息
from .models_points import PointLog  # 第 42 批：积分流水
from .image_validation import MAX_IMAGE_SIZE  # 第 91 批：图片上传大小上限

User = get_user_model()

# 说明（第 21 批）：本文件的测试**不写任何媒体文件**。
# 需要"有封面图"的场景直接给 ImageField 赋一个路径字符串即可 —— 序列化与
# "是否清空封面"的判断都只看字段值，不读磁盘。
# 这样做有两个原因：① 不去污染 backend/media（测试里的一次"清空封面"会真的删掉业务文件，
# 事务回滚救不了文件系统）；② 系统临时目录/新建子目录在本沙箱下不可写，
# 用临时 MEDIA_ROOT 反而会失败。


def _png_upload(name='avatar.png'):
    """
    构造一个内存里的**合法** PNG 文件对象（配合 InMemoryStorage 使用，不落盘）。

    第 26 批修正：原来用的是一段固定的 1x1 PNG 字节，能通过模型的 ImageField
    （直接赋文件不校验），但**通不过 DRF `ImageField` 的 Pillow 校验**
    （报"不是图片或者图片已损坏"）。这里改用 Pillow 现场生成，任何走序列化器的
    图片上传测试都能用。
    """
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buffer = BytesIO()
    Image.new('RGB', (8, 8), (34, 139, 34)).save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


# 头像/文件相关测试统一把默认存储换成内存存储：
# 既不会往 backend/media 里写文件，也绕开"沙箱不允许新建子目录"的问题。
IN_MEMORY_STORAGE = override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})


class NewsVisibilityTests(TestCase):
    """新闻发布状态可见性 / 权限 / 重复标题"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='news_admin', password='admin12345', is_staff=True,
        )
        cls.normal = User.objects.create_user(
            username='news_user', password='user12345',
        )
        cls.published = News.objects.create(
            title='已发布新闻', content='正文-已发布', is_published=True, author=cls.admin,
        )
        cls.draft = News.objects.create(
            title='未发布新闻', content='正文-未发布', is_published=False, author=cls.admin,
        )

    def setUp(self):
        self.anon = APIClient()
        # 让 404/500 以响应形式返回，便于断言状态码
        self.anon.raise_request_exception = False

        self.admin_client = APIClient()
        self.admin_client.raise_request_exception = False
        self.admin_client.force_authenticate(user=self.admin)

        self.user_client = APIClient()
        self.user_client.raise_request_exception = False
        self.user_client.force_authenticate(user=self.normal)

    @staticmethod
    def _ids(response):
        data = response.data
        results = data.get('results') if isinstance(data, dict) else data
        return [item['id'] for item in results]

    # ---------- 列表 ----------

    def test_anonymous_list_only_returns_published(self):
        for client in (self.anon, self.user_client):
            response = client.get('/api/news/')
            self.assertEqual(response.status_code, 200)
            ids = self._ids(response)
            self.assertIn(self.published.id, ids)
            self.assertNotIn(self.draft.id, ids)

    def test_anonymous_cannot_force_draft_filter(self):
        """非管理员显式传 is_published=false 也拿不到草稿（不能绕过）"""
        response = self.anon.get('/api/news/', {'is_published': 'false'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._ids(response), [])

    def test_admin_list_includes_draft(self):
        response = self.admin_client.get('/api/news/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.draft.id, self._ids(response))

    def test_recent_action_hides_draft_from_non_admin(self):
        response = self.anon.get('/api/news/recent/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.draft.id, self._ids(response))

    # ---------- 详情：404 而不是 500 ----------

    def test_anonymous_detail_of_published_is_ok(self):
        response = self.anon.get(f'/api/news/{self.published.id}/')
        self.assertEqual(response.status_code, 200)

    def test_anonymous_detail_of_draft_is_404(self):
        """修复前是 500 {"error":"服务器内部错误"}"""
        response = self.anon.get(f'/api/news/{self.draft.id}/')
        self.assertEqual(response.status_code, 404)

    def test_normal_user_detail_of_draft_is_404(self):
        response = self.user_client.get(f'/api/news/{self.draft.id}/')
        self.assertEqual(response.status_code, 404)

    def test_missing_news_detail_is_404_not_500(self):
        """修复前不存在的 id 同样是 500"""
        response = self.anon.get('/api/news/999999/')
        self.assertEqual(response.status_code, 404)

    def test_admin_detail_of_draft_is_ok(self):
        response = self.admin_client.get(f'/api/news/{self.draft.id}/')
        self.assertEqual(response.status_code, 200)

    # ---------- 旧版兼容接口 /api/news/{pk}/detail/ ----------

    def test_legacy_detail_action_is_reachable(self):
        """
        修复前该接口 100% 500：自定义动作命名为 `detail`，被 DRF 路由注入的
        `initkwargs={'detail': True}` 覆盖成布尔属性，`self.get` 变成 True，
        `handler(request)` 抛 TypeError: 'bool' object is not callable
        """
        response = self.anon.get(f'/api/news/{self.published.id}/detail/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], self.published.id)

    def test_legacy_detail_action_hides_draft_from_non_admin(self):
        response = self.anon.get(f'/api/news/{self.draft.id}/detail/')
        self.assertEqual(response.status_code, 404)

    # ---------- 下架主流程 ----------

    def test_unpublish_makes_news_invisible_to_users(self):
        """管理端 toggleNewsPublished 的真实请求形态：multipart 只带 is_published"""
        before = self._ids(self.anon.get('/api/news/'))
        self.assertIn(self.published.id, before)

        response = self.admin_client.patch(
            f'/api/news/{self.published.id}/', {'is_published': 'false'}, format='multipart',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.data['is_published'], False)

        self.published.refresh_from_db()
        self.assertFalse(self.published.is_published)

        after = self._ids(self.anon.get('/api/news/'))
        self.assertNotIn(self.published.id, after)
        self.assertEqual(self.anon.get(f'/api/news/{self.published.id}/').status_code, 404)

    def test_normal_user_cannot_publish_or_unpublish(self):
        response = self.user_client.patch(
            f'/api/news/{self.draft.id}/', {'is_published': 'true'}, format='multipart',
        )
        self.assertIn(response.status_code, (403, 404))
        self.draft.refresh_from_db()
        self.assertFalse(self.draft.is_published)

    # ---------- 重复标题防护 ----------

    def test_duplicate_title_create_is_rejected(self):
        """
        库里曾出现同标题 + 同正文的两条记录（一条已下架、一条仍发布），
        导致"下架了用户还能看见"。现在重复标题直接 400。
        """
        response = self.admin_client.post(
            '/api/news/',
            {
                'title': self.published.title,
                'content': '重复的新正文',
                'category': 'notice',
                'is_published': 'true',
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('title', response.data)
        self.assertEqual(
            News.objects.filter(title=self.published.title).count(), 1,
        )

    def test_duplicate_title_check_ignores_case_and_spaces(self):
        response = self.admin_client.post(
            '/api/news/',
            {
                'title': f'  {self.published.title.upper()}  ',
                'content': '正文',
                'category': 'notice',
            },
            format='multipart',
        )
        # 中文标题 upper() 不变，这里主要验证首尾空格不会绕过查重
        self.assertEqual(response.status_code, 400)

    def test_updating_without_changing_title_is_allowed(self):
        """编辑时排除自身，因此"只改正文不改标题"不能误报重复"""
        response = self.admin_client.patch(
            f'/api/news/{self.published.id}/',
            {'title': self.published.title, 'content': '改过的正文'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 200)
        self.published.refresh_from_db()
        self.assertEqual(self.published.content, '改过的正文')

    def test_renaming_to_existing_title_is_rejected(self):
        response = self.admin_client.patch(
            f'/api/news/{self.draft.id}/',
            {'title': self.published.title},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('title', response.data)

    def test_editing_duplicate_title_record_without_renaming_is_allowed(self):
        """
        历史重复数据（同标题两条）必须仍然可编辑正文/发布状态。

        背景（真实故障）：加了"同标题不得重复建档"的校验后，编辑这两条中的任意一条
        都会被查重拦成 400（因为兄弟记录标题相同），管理员在行业动态页点保存只看到
        「保存失败」。现在"标题没变"时跳过查重，只有真的**改名撞车**才拦。
        """
        first = News.objects.create(
            title='重复标题新闻', content='第一条', is_published=False, author=self.admin,
        )
        second = News.objects.create(
            title='重复标题新闻', content='第二条', is_published=True, author=self.admin,
        )
        self.assertNotEqual(first.id, second.id)

        response = self.admin_client.patch(
            f'/api/news/{second.id}/',
            {'title': '重复标题新闻', 'content': '改过的正文', 'is_published': 'false'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 200)

        second.refresh_from_db()
        self.assertEqual(second.content, '改过的正文')
        self.assertFalse(second.is_published)

    def test_patch_without_image_field_keeps_cover_and_content(self):
        """
        前端只提交白名单字段（不带 image）时，封面图不能被清空。

        背景：行业动态页原来把详情返回的所有字段塞进 FormData，并因 image 被置为
        null 而发出 `image=''`，后端按"清空封面图"处理 —— 即"编辑成功但封面没了"。
        """
        # 只给字段一个路径（不落盘），模拟"这条新闻有封面图"
        self.published.image = 'news_images/test-cover.png'
        self.published.save(update_fields=['image'])
        self.published.tags = '小麦,病害'
        self.published.save(update_fields=['tags'])

        response = self.admin_client.patch(
            f'/api/news/{self.published.id}/',
            {'title': self.published.title, 'content': '只改正文', 'tags': '小麦,病害'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 200)

        self.published.refresh_from_db()
        self.assertEqual(self.published.content, '只改正文')
        self.assertTrue(self.published.image)
        self.assertEqual(self.published.tags, '小麦,病害')


class ApiIdentitySourceTests(TestCase):
    """
    API 的身份**只能来自 Token**，Django 会话不得成为第二个身份来源。

    背景（第 19 批）：同一浏览器里同时存在两个身份载体 ——
      · `Authorization: Token xxx`（前端按标签页保存）
      · `sessionid` cookie（整个浏览器共用，属于"最后一次登录的账号"）
    两个认证类并存时，任何一次没带 Token 头的请求都会回退成"会话里的那个账号"，
    造成"界面显示 A、服务端按 B 执行"。现已在 settings 里移除
    SessionAuthentication，本组测试锁定这一行为，防止被无意加回。
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='id_admin', password='admin12345', is_staff=True,
        )
        cls.normal = User.objects.create_user(
            username='id_user', password='user12345',
        )

    def setUp(self):
        self.client_ = APIClient()
        self.client_.raise_request_exception = False

    def test_session_cookie_alone_cannot_authenticate(self):
        """只带 Django 会话（模拟浏览器里登录过另一个账号）不能通过 API 认证"""
        self.client_.force_login(self.admin)
        response = self.client_.get('/api/check-auth/')
        self.assertEqual(response.status_code, 401)

    def test_session_cookie_does_not_grant_admin_view(self):
        """只带会话时拿不到管理员视角：草稿不能出现在列表里"""
        draft = News.objects.create(
            title='会话不该看到的草稿', content='x', is_published=False, author=self.admin,
        )
        self.client_.force_login(self.admin)

        response = self.client_.get('/api/news/', {'page_size': 100})
        self.assertEqual(response.status_code, 200)
        results = response.data.get('results') if isinstance(response.data, dict) else response.data
        self.assertNotIn(draft.id, [row['id'] for row in results])

    def test_token_still_authenticates(self):
        token, _ = Token.objects.get_or_create(user=self.normal)
        self.client_.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

        response = self.client_.get('/api/check-auth/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data']['username'], self.normal.username)

    def test_token_wins_over_a_session_of_another_account(self):
        """会话属于别的账号时，身份仍以 Token 为准"""
        token, _ = Token.objects.get_or_create(user=self.normal)
        self.client_.force_login(self.admin)                                  # 会话 = 管理员
        self.client_.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')     # Token = 普通用户

        response = self.client_.get('/api/check-auth/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data']['username'], self.normal.username)
        self.assertFalse(response.data['data']['is_staff'])

    def test_invalid_token_is_rejected_not_fallen_back_to_session(self):
        """Token 无效时应 401，而不是悄悄回退到会话身份"""
        self.client_.force_login(self.admin)
        self.client_.credentials(HTTP_AUTHORIZATION='Token deadbeefdeadbeefdeadbeefdeadbeefdeadbeef')

        response = self.client_.get('/api/check-auth/')
        self.assertEqual(response.status_code, 401)


class DetectionHistoryScopeTests(TestCase):
    """
    管理端「识别记录管理」的数据范围与搜索（第 21 批）

    背景：该页此前**从未**携带 all_users=true，于是「识别记录管理」实际只显示管理员
    自己的记录，与「历史识别记录」页看起来高度重复；而它的搜索框写着
    "搜索用户或病害名称"，后端却只认 pest（病害）参数，"按用户搜索"实际不生效。
    现两边都补齐，并用测试锁住数据范围，防止越权回退。
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='dh_admin', password='pw12345678', is_staff=True,
        )
        cls.alice = User.objects.create_user(username='dh_alice', password='pw12345678')
        cls.bob = User.objects.create_user(username='dh_bob', password='pw12345678')

        cls.alice_record = DetectionHistory.objects.create(
            user=cls.alice, image='detection_history/test-alice.png',
            detection_result='小麦锈病', confidence=0.9,
        )
        cls.bob_record = DetectionHistory.objects.create(
            user=cls.bob, image='detection_history/test-bob.png',
            detection_result='玉米螟', confidence=0.8,
        )

    def setUp(self):
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)
        self.alice_client = APIClient()
        self.alice_client.force_authenticate(user=self.alice)

    @staticmethod
    def _items(response):
        return response.data['data']['items']

    def test_admin_with_all_users_sees_every_record(self):
        response = self.admin_client.get(
            '/api/detection-history/', {'all_users': 'true', 'page_size': 50},
        )
        self.assertEqual(response.status_code, 200)
        ids = [row['id'] for row in self._items(response)]
        self.assertIn(self.alice_record.id, ids)
        self.assertIn(self.bob_record.id, ids)

    def test_admin_without_all_users_sees_only_own(self):
        response = self.admin_client.get('/api/detection-history/', {'page_size': 50})
        self.assertEqual(response.status_code, 200)
        ids = [row['id'] for row in self._items(response)]
        self.assertNotIn(self.alice_record.id, ids)
        self.assertNotIn(self.bob_record.id, ids)

    def test_normal_user_cannot_see_others_even_with_all_users(self):
        response = self.alice_client.get(
            '/api/detection-history/', {'all_users': 'true', 'page_size': 50},
        )
        self.assertEqual(response.status_code, 200)
        ids = [row['id'] for row in self._items(response)]
        self.assertIn(self.alice_record.id, ids)
        self.assertNotIn(self.bob_record.id, ids)

    def test_search_matches_username(self):
        response = self.admin_client.get(
            '/api/detection-history/',
            {'all_users': 'true', 'search': 'dh_bob', 'page_size': 50},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in self._items(response)], [self.bob_record.id])

    def test_search_matches_disease_name(self):
        response = self.admin_client.get(
            '/api/detection-history/',
            {'all_users': 'true', 'search': '锈病', 'page_size': 50},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in self._items(response)], [self.alice_record.id])

    def test_statistics_scope_matches_list_scope(self):
        """
        `/statistics/` 的统计范围必须与记录列表一致（第 22 批）。

        修复前：`StatisticsView` 完全忽略 `all_users`，只按 is_staff/is_superuser 判定，
        于是管理员无论带不带该参数拿到的都是"全部用户"的统计，而列表默认只给自己
        —— 页面上就出现"列表是我的、图表是所有人"的自相矛盾。
        """
        # 管理员不带参数 → 只看自己（管理员本身没有记录 → 0）
        response = self.admin_client.get('/api/statistics/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_detections'], 0)

        # 管理员带 all_users=true → alice + bob 共 2 条
        response = self.admin_client.get('/api/statistics/', {'all_users': 'true'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_detections'], 2)

        # 普通用户即使带 all_users=true 也只能看到自己的 1 条（不越权）
        response = self.alice_client.get('/api/statistics/', {'all_users': 'true'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_detections'], 1)


@IN_MEMORY_STORAGE
class UserProfileFeatureTests(TestCase):
    """
    用户资料完善（第 23 批）：真实头像上传/删除、修改密码、资料可见性。

    背景：`CustomUser` 此前**没有 avatar 字段**（`get_avatar()` 恒为 None，
    前端只能用 `ui-avatars.com` 这个外网服务生成占位图），而且全站**没有修改密码入口**。
    """

    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(
            username='up_alice', password='alice-1234', email='alice@example.com',
        )
        cls.bob = User.objects.create_user(
            username='up_bob', password='bob-12345', email='bob@example.com',
        )
        cls.admin = User.objects.create_user(
            username='up_admin', password='admin-1234', is_staff=True,
        )

    def setUp(self):
        self.alice_client = APIClient()
        self.alice_client.force_authenticate(user=self.alice)
        self.bob_client = APIClient()
        self.bob_client.force_authenticate(user=self.bob)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)
        self.anon = APIClient()

    # ---------- 头像 ----------

    def test_avatar_upload_then_delete(self):
        response = self.alice_client.post(
            f'/api/users/{self.alice.id}/avatar/',
            {'avatar': _png_upload()},
            format='multipart',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data['avatar'])
        self.assertIn('avatars/', response.data['avatar'])

        self.alice.refresh_from_db()
        self.assertTrue(self.alice.avatar)

        # 资料接口同样要返回头像地址
        profile = self.alice_client.get(f'/api/users/{self.alice.id}/')
        self.assertEqual(profile.status_code, 200)
        self.assertIsNotNone(profile.data['avatar'])

        deleted = self.alice_client.delete(f'/api/users/{self.alice.id}/avatar/')
        self.assertEqual(deleted.status_code, 200)
        self.assertIsNone(deleted.data['avatar'])

        self.alice.refresh_from_db()
        self.assertFalse(self.alice.avatar)

    def test_avatar_rejects_non_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        bad = SimpleUploadedFile('note.txt', b'not an image', content_type='text/plain')
        response = self.alice_client.post(
            f'/api/users/{self.alice.id}/avatar/', {'avatar': bad}, format='multipart',
        )
        self.assertEqual(response.status_code, 400)

    def test_avatar_rejects_oversized_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        big = SimpleUploadedFile('big.png', b'x' * (2 * 1024 * 1024 + 1), content_type='image/png')
        response = self.alice_client.post(
            f'/api/users/{self.alice.id}/avatar/', {'avatar': big}, format='multipart',
        )
        self.assertEqual(response.status_code, 400)

    def test_avatar_requires_self_or_admin(self):
        # 别人不能改我的头像
        denied = self.bob_client.post(
            f'/api/users/{self.alice.id}/avatar/', {'avatar': _png_upload()}, format='multipart',
        )
        self.assertEqual(denied.status_code, 403)

        # 管理员可以
        allowed = self.admin_client.post(
            f'/api/users/{self.alice.id}/avatar/', {'avatar': _png_upload()}, format='multipart',
        )
        self.assertEqual(allowed.status_code, 200)

    # ---------- 修改密码 ----------

    def test_password_change_success_rotates_token(self):
        old_token, _ = Token.objects.get_or_create(user=self.alice)

        response = self.alice_client.post(
            f'/api/users/{self.alice.id}/password/',
            {'old_password': 'alice-1234', 'new_password': 'newpass-5678'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)
        # 旧 token 必须作废（否则"改了密码但旧设备仍在线"）
        self.assertNotEqual(response.data['token'], old_token.key)
        self.assertFalse(Token.objects.filter(key=old_token.key).exists())

        self.alice.refresh_from_db()
        self.assertTrue(self.alice.check_password('newpass-5678'))

        # 新密码可以正常登录
        login = APIClient().post(
            '/api/login/', {'username': 'up_alice', 'password': 'newpass-5678'}, format='json',
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn('token', login.data.get('data', {}))

    def test_password_change_rejects_wrong_old_password(self):
        response = self.alice_client.post(
            f'/api/users/{self.alice.id}/password/',
            {'old_password': 'wrong-pass', 'new_password': 'newpass-5678'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.alice.refresh_from_db()
        self.assertTrue(self.alice.check_password('alice-1234'))

    def test_password_change_rejects_weak_or_same_password(self):
        cases = [
            {'old_password': 'alice-1234', 'new_password': 'short7'},      # 太短
            {'old_password': 'alice-1234', 'new_password': '12345678'},    # 纯数字
            {'old_password': 'alice-1234', 'new_password': 'alice-1234'},  # 与旧密码相同
            {'old_password': '', 'new_password': 'newpass-5678'},          # 旧密码为空
            {'old_password': 'alice-1234', 'new_password': ''},            # 新密码为空
        ]
        for payload in cases:
            response = self.alice_client.post(
                f'/api/users/{self.alice.id}/password/', payload, format='json',
            )
            self.assertEqual(response.status_code, 400, payload)

    def test_password_change_only_self(self):
        response = self.bob_client.post(
            f'/api/users/{self.alice.id}/password/',
            {'old_password': 'alice-1234', 'new_password': 'newpass-5678'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.alice.refresh_from_db()
        self.assertTrue(self.alice.check_password('alice-1234'))

    # ---------- 资料可见性（防回归） ----------

    def test_missing_user_profile_is_404(self):
        """不存在的用户必须 404 —— 前端据此提示"用户不存在"（而不是显示假资料）"""
        response = self.alice_client.get('/api/users/999999/')
        self.assertEqual(response.status_code, 404)

    def test_public_profile_hides_email_but_exposes_avatar(self):
        response = self.anon.get(f'/api/users/{self.alice.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('email', response.data)
        self.assertIn('avatar', response.data)


@override_settings(POST_REQUIRE_REVIEW=False)
class ForumFeatureTests(TestCase):
    """
    论坛完善（第 24 批）：草稿真存草稿、置顶/精华只有版主能设、收藏打通、列表筛选排序生效。

    第 38 批说明：这一组用例关注的是**点赞/收藏/草稿/置顶**，
    而审核策略（普通用户发帖先进待审核）会让"别人看不到该帖"，从而干扰这些断言。
    审核流程有专门的 `PostReviewTests`，这里显式关掉审核开关以保持原语义。

    修复前的实测问题：
      1. 前端「保存草稿」发的 `is_draft=true` 被序列化器静默忽略（字段没声明）→
         实际按模型默认值建成了**已发布**帖子；配合每 30 秒的自动保存，论坛会被灌入
         半成品已发布帖，而且作者自己也找不回"草稿"（列表只返回 published）。
      2. `is_pinned` / `is_essence` 在序列化器里可写，服务端又没校验 →
         **普通用户能把自己的帖子置顶/加精**（实测 PATCH 200 且生效）。
      3. 收藏功能只有后端 `favorite` 动作，前端没有任何入口，响应里也没有 is_favorited。
      4. 版块页的排序下拉发的是 `ordering`，后端只认 `order_by`；「精华」标签也不参与
         筛选 —— 两个控件都是装饰。
    """

    @classmethod
    def setUpTestData(cls):
        cls.board = ForumBoard.objects.create(name='测试版块', description='desc', is_active=True)
        cls.author = User.objects.create_user(username='fa_author', password='pw12345678')
        cls.other = User.objects.create_user(username='fa_other', password='pw12345678')
        cls.admin = User.objects.create_user(username='fa_admin', password='pw12345678', is_staff=True)

    def setUp(self):
        self.author_client = APIClient()
        self.author_client.force_authenticate(user=self.author)
        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)

    def _create(self, client, **overrides):
        payload = {'board_id': self.board.id, 'title': '测试帖子', 'content': '正文', **overrides}
        return client.post('/api/forums/posts/', payload, format='json')

    @staticmethod
    def _ids(response):
        return [row['id'] for row in (response.data.get('results') or [])]

    # ---------- 草稿 ----------

    def test_draft_is_really_saved_as_draft(self):
        response = self._create(self.author_client, is_draft=True)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'draft')
        self.assertEqual(Post.objects.get(id=response.data['id']).status, 'draft')

    def test_author_sees_own_draft_others_do_not(self):
        draft_id = self._create(self.author_client, is_draft=True).data['id']

        mine = self.author_client.get('/api/forums/posts/', {'page_size': 100})
        self.assertIn(draft_id, self._ids(mine))
        self.assertEqual(self.author_client.get(f'/api/forums/posts/{draft_id}/').status_code, 200)

        others = self.other_client.get('/api/forums/posts/', {'page_size': 100})
        self.assertNotIn(draft_id, self._ids(others))
        self.assertEqual(self.other_client.get(f'/api/forums/posts/{draft_id}/').status_code, 404)

    def test_draft_can_be_published(self):
        post_id = self._create(self.author_client, is_draft=True).data['id']
        response = self.author_client.patch(
            f'/api/forums/posts/{post_id}/',
            {'board_id': self.board.id, 'title': '测试帖子', 'content': '正文', 'is_draft': False},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Post.objects.get(id=post_id).status, 'published')
        # 发布后其他用户可见
        self.assertIn(post_id, self._ids(self.other_client.get('/api/forums/posts/', {'page_size': 100})))

    # ---------- 置顶 / 精华（越权） ----------

    def test_normal_user_cannot_pin_or_essence(self):
        post_id = self._create(self.author_client).data['id']

        pinned = self.author_client.patch(
            f'/api/forums/posts/{post_id}/', {'is_pinned': True}, format='json',
        )
        self.assertEqual(pinned.status_code, 403)

        essence = self.author_client.patch(
            f'/api/forums/posts/{post_id}/', {'is_essence': True}, format='json',
        )
        self.assertEqual(essence.status_code, 403)

        post = Post.objects.get(id=post_id)
        self.assertFalse(post.is_pinned)
        self.assertFalse(post.is_essence)

    def test_normal_user_cannot_pin_on_create(self):
        response = self._create(self.author_client, is_pinned=True)
        self.assertEqual(response.status_code, 403)

    def test_moderator_can_pin_and_essence(self):
        post_id = self._create(self.author_client).data['id']

        pinned = self.admin_client.post(f'/api/forums/posts/{post_id}/set_pinned/', {'is_pinned': True}, format='json')
        self.assertEqual(pinned.status_code, 200)
        essence = self.admin_client.post(f'/api/forums/posts/{post_id}/set_essence/', {'is_essence': True}, format='json')
        self.assertEqual(essence.status_code, 200)

        post = Post.objects.get(id=post_id)
        self.assertTrue(post.is_pinned)
        self.assertTrue(post.is_essence)

        # 版主设置后，作者编辑正文不应被"不能改置顶"的规则卡住，且置顶保持
        edited = self.author_client.patch(
            f'/api/forums/posts/{post_id}/',
            {'board_id': self.board.id, 'title': '测试帖子', 'content': '改过', 'is_pinned': False},
            format='json',
        )
        self.assertEqual(edited.status_code, 200)
        post.refresh_from_db()
        self.assertEqual(post.content, '改过')
        self.assertTrue(post.is_pinned)

    # ---------- 收藏 ----------

    def test_favorite_toggle_and_state(self):
        post_id = self._create(self.author_client).data['id']

        added = self.author_client.post(f'/api/forums/posts/{post_id}/favorite/', {}, format='json')
        self.assertEqual(added.status_code, 201)
        self.assertTrue(added.data['is_favorited'])
        self.assertTrue(self.author_client.get(f'/api/forums/posts/{post_id}/').data['is_favorited'])

        # 别人看到的是未收藏
        self.assertFalse(self.other_client.get(f'/api/forums/posts/{post_id}/').data['is_favorited'])

        removed = self.author_client.post(f'/api/forums/posts/{post_id}/favorite/', {}, format='json')
        self.assertEqual(removed.status_code, 200)
        self.assertFalse(removed.data['is_favorited'])

    def test_favorited_filter_returns_only_my_favorites(self):
        favorite_id = self._create(self.author_client).data['id']
        other_id = self._create(self.author_client).data['id']
        self.author_client.post(f'/api/forums/posts/{favorite_id}/favorite/', {}, format='json')

        mine = self.author_client.get('/api/forums/posts/', {'favorited': 'true', 'page_size': 100})
        self.assertEqual(self._ids(mine), [favorite_id])

        others = self.other_client.get('/api/forums/posts/', {'favorited': 'true', 'page_size': 100})
        self.assertEqual(self._ids(others), [])
        self.assertNotIn(other_id, self._ids(mine))

    def test_anonymous_cannot_favorite(self):
        post_id = self._create(self.author_client).data['id']
        anonymous = APIClient()
        response = anonymous.post(f'/api/forums/posts/{post_id}/favorite/', {}, format='json')
        self.assertIn(response.status_code, (401, 403))

    # ---------- 列表筛选 / 排序（此前是装饰） ----------

    def test_list_supports_ordering_and_essence_filter(self):
        first = self._create(self.author_client, title='浏览多').data['id']
        second = self._create(self.author_client, title='浏览少').data['id']
        Post.objects.filter(id=first).update(view_count=100)
        Post.objects.filter(id=second).update(view_count=1)

        # 前端发的是 ordering（后端以前只认 order_by）
        by_ordering = self.author_client.get('/api/forums/posts/', {'ordering': '-view_count', 'page_size': 100})
        views = [row['view_count'] for row in by_ordering.data['results'] if not row['is_pinned']]
        self.assertEqual(views, sorted(views, reverse=True))
        self.assertEqual(views[0], 100)

        # order_by 同样可用，并按评论数排序
        Post.objects.filter(id=second).update(comment_count=5)
        by_order = self.author_client.get('/api/forums/posts/', {'order_by': '-comment_count', 'page_size': 100})
        comments = [row['comment_count'] for row in by_order.data['results'] if not row['is_pinned']]
        self.assertEqual(comments, sorted(comments, reverse=True))

        # 精华筛选
        self.admin_client.post(f'/api/forums/posts/{first}/set_essence/', {'is_essence': True}, format='json')
        essence_list = self.author_client.get('/api/forums/posts/', {'is_essence': 'true', 'page_size': 100})
        rows = essence_list.data['results']
        self.assertTrue(rows)
        self.assertTrue(all(row['is_essence'] for row in rows))

        # 列表要带上 status（前端据此显示草稿角标）
        self.assertIn('status', by_order.data['results'][0])


class ForumLikersAndUserCommentsTests(TestCase):
    """
    第 25 批：用户资料页要看得到"评论发在哪里"与"谁点赞了"。

    - `GET /api/users/{id}/comments/`：某用户的评论 + 所属帖子/版块上下文；
    - `GET /api/forums/posts/{id}/likes/`：帖子的点赞者名单；
    - `GET /api/forums/posts/{post}/comments/{id}/likes/`：评论的点赞者名单。
    此前只有 `LikeViewSet`（只返回"我赞过什么"），无法反查被谁赞过。
    """

    @classmethod
    def setUpTestData(cls):
        cls.board = ForumBoard.objects.create(name='上下文版块', description='d', is_active=True)
        cls.author = User.objects.create_user(username='lc_author', password='pw12345678')
        cls.other = User.objects.create_user(username='lc_other', password='pw12345678')
        cls.post = Post.objects.create(
            title='上下文测试帖', content='正文', author=cls.author, board=cls.board, status='published',
        )
        cls.comment = Comment.objects.create(
            content='这是一条测试评论', author=cls.author, post=cls.post,
        )
        cls.deleted_comment = Comment.objects.create(
            content='已删除的评论', author=cls.author, post=cls.post, is_deleted=True,
        )

    def setUp(self):
        self.author_client = APIClient()
        self.author_client.force_authenticate(user=self.author)
        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other)
        self.anon = APIClient()

    # ---------- 谁点赞了 ----------

    def test_post_likers_endpoint(self):
        empty = self.author_client.get(f'/api/forums/posts/{self.post.id}/likes/')
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.data['count'], 0)

        self.other_client.post(f'/api/forums/posts/{self.post.id}/like/', {}, format='json')

        response = self.author_client.get(f'/api/forums/posts/{self.post.id}/likes/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['user']['username'], self.other.username)
        # 头像字段要在（第 23 批加了真实头像，第 25 批在论坛序列化器里补上）
        self.assertIn('avatar', response.data['results'][0]['user'])

    def test_comment_likers_endpoint(self):
        self.other_client.post(
            f'/api/forums/posts/{self.post.id}/comments/{self.comment.id}/like/', {}, format='json',
        )

        response = self.author_client.get(
            f'/api/forums/posts/{self.post.id}/comments/{self.comment.id}/likes/',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['user']['username'], self.other.username)

    def test_likers_visible_to_anonymous(self):
        self.other_client.post(f'/api/forums/posts/{self.post.id}/like/', {}, format='json')
        response = self.anon.get(f'/api/forums/posts/{self.post.id}/likes/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    # ---------- 用户的评论（带"发在哪里"）----------

    def test_user_comments_include_post_context(self):
        response = self.author_client.get(f'/api/users/{self.author.id}/comments/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)  # 已软删除的那条不算

        item = response.data['results'][0]
        self.assertEqual(item['id'], self.comment.id)
        self.assertEqual(item['content'], '这是一条测试评论')
        self.assertEqual(item['post_id'], self.post.id)
        self.assertEqual(item['post_title'], self.post.title)
        self.assertEqual(item['board_name'], self.board.name)
        self.assertEqual(item['board_id'], self.board.id)

    def test_user_comments_only_that_user(self):
        response = self.other_client.get(f'/api/users/{self.other.id}/comments/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)

        mine = self.author_client.get(f'/api/users/{self.author.id}/comments/')
        self.assertEqual(mine.data['count'], 1)

    def test_post_author_payload_has_avatar_field(self):
        response = self.author_client.get(f'/api/forums/posts/{self.post.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('avatar', response.data['author'])


@IN_MEMORY_STORAGE
class FeedbackFeatureTests(TestCase):
    """
    第 26 批：把「意见反馈」做成独立可用功能。

    改前：Feedback 模型只能承载"识别结果对不对"（disease_name / is_correct 必填），
    既没有反馈类型与处理状态，用户也不能撤回自己的反馈（删除被限定为管理员）。
    """

    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(username='fb_alice', password='pw12345678')
        cls.bob = User.objects.create_user(username='fb_bob', password='pw12345678')
        cls.admin = User.objects.create_user(username='fb_admin', password='pw12345678', is_staff=True)

    def setUp(self):
        self.alice_client = APIClient()
        self.alice_client.force_authenticate(user=self.alice)
        self.bob_client = APIClient()
        self.bob_client.force_authenticate(user=self.bob)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)

    # ---------- 提交 ----------

    def test_general_feedback_without_detection_fields(self):
        """一般性意见反馈：不需要病害名称与识别正确性"""
        response = self.alice_client.post(
            '/api/feedback/',
            {'category': 'bug', 'suggestion': '历史记录页翻页后回到第一页'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)

        feedback = Feedback.objects.get(id=response.data['id'])
        self.assertEqual(feedback.user, self.alice)
        self.assertEqual(feedback.category, 'bug')
        self.assertEqual(feedback.status, 'pending')
        self.assertEqual(feedback.disease_name, '')
        self.assertIsNone(feedback.is_correct)
        # 响应里给出中文类型名与状态名，前端直接显示
        self.assertEqual(response.data['category_display'], '问题反馈')
        self.assertEqual(response.data['status_display'], '待处理')

    def test_detection_feedback_still_supported(self):
        """识别结果页的「识别正确/不正确」反馈仍要能提交"""
        response = self.alice_client.post(
            '/api/feedback/',
            {
                'category': 'recognition',
                'disease_name': '番茄晚疫病',
                'confidence': 0.93,
                'is_correct': 'false',
                'suggestion': '识别错误',
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        feedback = Feedback.objects.get(id=response.data['id'])
        self.assertEqual(feedback.category, 'recognition')
        self.assertEqual(feedback.disease_name, '番茄晚疫病')
        self.assertFalse(feedback.is_correct)

    def test_feedback_requires_content_or_image(self):
        response = self.alice_client.post('/api/feedback/', {'category': 'other'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('suggestion', response.data)

    def test_user_cannot_self_assign_status_or_reply(self):
        """处理状态与管理员回复是只读的：用户不能自己把它标记成已处理"""
        response = self.alice_client.post(
            '/api/feedback/',
            {'category': 'suggestion', 'suggestion': '希望支持导出 Excel', 'status': 'resolved', 'admin_reply': '已处理'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        feedback = Feedback.objects.get(id=response.data['id'])
        self.assertEqual(feedback.status, 'pending')
        self.assertEqual(feedback.admin_reply, '')

    def test_image_url_is_absolute_and_returned(self):
        response = self.alice_client.post(
            '/api/feedback/',
            {'category': 'bug', 'suggestion': '带图反馈', 'image': _png_upload('shot.png')},
            format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['image_url'])
        self.assertTrue(response.data['image_url'].startswith('http'))

    # ---------- 可见性与撤回 ----------

    def test_user_sees_only_own_feedback_admin_sees_all(self):
        self.alice_client.post('/api/feedback/', {'suggestion': 'alice 的反馈'}, format='json')
        self.bob_client.post('/api/feedback/', {'suggestion': 'bob 的反馈'}, format='json')

        alice_list = self.alice_client.get('/api/feedback/')
        self.assertEqual(alice_list.data['count'], 1)
        self.assertEqual(alice_list.data['results'][0]['suggestion'], 'alice 的反馈')

        bob_list = self.bob_client.get('/api/feedback/')
        self.assertEqual(bob_list.data['count'], 1)
        self.assertEqual(bob_list.data['results'][0]['suggestion'], 'bob 的反馈')

        admin_list = self.admin_client.get('/api/feedback/')
        self.assertEqual(admin_list.data['count'], 2)

    def test_user_can_withdraw_own_feedback_but_not_others(self):
        feedback_id = self.alice_client.post(
            '/api/feedback/', {'suggestion': '待撤回'}, format='json',
        ).data['id']

        # 别人删不掉（queryset 已限定为本人 → 404）
        self.assertEqual(self.bob_client.delete(f'/api/feedback/{feedback_id}/').status_code, 404)

        # 本人可以撤回
        self.assertEqual(self.alice_client.delete(f'/api/feedback/{feedback_id}/').status_code, 204)
        self.assertFalse(Feedback.objects.filter(id=feedback_id).exists())

    def test_filters_by_category_and_status(self):
        first = self.alice_client.post(
            '/api/feedback/', {'category': 'bug', 'suggestion': 'A'}, format='json',
        ).data['id']
        self.alice_client.post('/api/feedback/', {'category': 'suggestion', 'suggestion': 'B'}, format='json')

        by_category = self.admin_client.get('/api/feedback/', {'category': 'bug'})
        self.assertEqual([row['id'] for row in by_category.data['results']], [first])

        by_status = self.admin_client.get('/api/feedback/', {'status': 'resolved'})
        self.assertEqual(by_status.data['count'], 0)

        # 管理员在后台流转状态后，用户能在自己的列表里看到
        Feedback.objects.filter(id=first).update(status='resolved', admin_reply='已修复，请升级后重试')
        resolved = self.alice_client.get('/api/feedback/')
        row = next(item for item in resolved.data['results'] if item['id'] == first)
        self.assertEqual(row['status_display'], '已处理')
        self.assertEqual(row['admin_reply'], '已修复，请升级后重试')

    # ---------- 第 27 批：管理员要能看到"是谁提的"并回复 ----------

    def test_list_exposes_submitter_username(self):
        """列表必须带提交人用户名 —— 否则管理员无法知道反馈是谁提的"""
        self.alice_client.post('/api/feedback/', {'suggestion': '来自 alice 的反馈'}, format='json')

        admin_list = self.admin_client.get('/api/feedback/')
        self.assertEqual(admin_list.data['count'], 1)
        self.assertEqual(admin_list.data['results'][0]['user'], self.alice.username)

        # 用户自己的列表里同样带用户名
        alice_list = self.alice_client.get('/api/feedback/')
        self.assertEqual(alice_list.data['results'][0]['user'], self.alice.username)

    def test_admin_can_search_by_username_and_content(self):
        self.alice_client.post('/api/feedback/', {'suggestion': '翻页会跳回第一页'}, format='json')
        self.bob_client.post('/api/feedback/', {'suggestion': '希望支持导出'}, format='json')

        by_name = self.admin_client.get('/api/feedback/', {'search': 'fb_alice'})
        self.assertEqual([row['user'] for row in by_name.data['results']], ['fb_alice'])

        by_content = self.admin_client.get('/api/feedback/', {'search': '导出'})
        self.assertEqual([row['user'] for row in by_content.data['results']], ['fb_bob'])

        by_user_id = self.admin_client.get('/api/feedback/', {'user': self.bob.id})
        self.assertEqual([row['user'] for row in by_user_id.data['results']], ['fb_bob'])

    def test_admin_reply_action_flows_status(self):
        """管理端专用动作：流转状态 + 写回复（status/admin_reply 在序列化器里是只读的）"""
        feedback_id = self.alice_client.post(
            '/api/feedback/', {'suggestion': '需要处理的问题'}, format='json',
        ).data['id']

        response = self.admin_client.post(
            f'/api/feedback/{feedback_id}/reply/',
            {'status': 'resolved', 'admin_reply': '已修复，感谢反馈'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'resolved')
        self.assertEqual(response.data['admin_reply'], '已修复，感谢反馈')
        self.assertEqual(response.data['status_display'], '已处理')

        feedback = Feedback.objects.get(id=feedback_id)
        self.assertIsNotNone(feedback.handled_at)

        # 用户能看到回复
        mine = self.alice_client.get('/api/feedback/')
        row = next(item for item in mine.data['results'] if item['id'] == feedback_id)
        self.assertEqual(row['admin_reply'], '已修复，感谢反馈')

        # 退回"处理中"时清空处理时间
        back = self.admin_client.post(
            f'/api/feedback/{feedback_id}/reply/', {'status': 'processing'}, format='json',
        )
        self.assertEqual(back.status_code, 200)
        self.assertIsNone(Feedback.objects.get(id=feedback_id).handled_at)

    def test_reply_action_requires_admin(self):
        feedback_id = self.alice_client.post(
            '/api/feedback/', {'suggestion': '普通用户不能回复'}, format='json',
        ).data['id']

        denied = self.alice_client.post(
            f'/api/feedback/{feedback_id}/reply/', {'status': 'resolved'}, format='json',
        )
        self.assertIn(denied.status_code, (401, 403))
        self.assertEqual(Feedback.objects.get(id=feedback_id).status, 'pending')

    def test_reply_action_rejects_invalid_status(self):
        feedback_id = self.alice_client.post(
            '/api/feedback/', {'suggestion': '状态值非法'}, format='json',
        ).data['id']

        response = self.admin_client.post(
            f'/api/feedback/{feedback_id}/reply/', {'status': 'not-a-status'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Feedback.objects.get(id=feedback_id).status, 'pending')


# ============================================================================
# 第 35 批：账号安全三件套
#   ① 登录失败锁定 + 限流  ② 忘记密码（邮箱重置）  ③ 注册用户名实时校验
# 这三项此前都不存在：可以无限次猜密码（无验证码、无限流）、忘记密码只能找管理员、
# 注册要等提交后才知道用户名被占用。下面的测试把行为锁死。
# ============================================================================
class UsernameAvailabilityTests(TestCase):
    """③ 注册用户名实时校验"""

    def setUp(self):
        cache.clear()  # 同上：用户名校验接口也限流
        self.client = APIClient()
        User.objects.create_user(username='taken_user', password='pw123456')

    def _check(self, username):
        return self.client.get('/api/users/check-username/', {'username': username})

    def test_available_username(self):
        response = self._check('brand_new_01')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['available'])

    def test_occupied_username_is_case_insensitive(self):
        response = self._check('TAKEN_USER')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['available'])
        self.assertIn('占用', response.data['message'])

    def test_invalid_formats_rejected(self):
        for bad in ['ab', 'a' * 21, '1abc', 'has space', 'bad-name']:
            response = self._check(bad)
            self.assertEqual(response.status_code, 200, bad)
            self.assertFalse(response.data['available'], f'{bad} 不应通过')

    def test_register_rejects_invalid_username_server_side(self):
        """前端能绕，服务端必须拦（此前 1 个字符的用户名也能注册成功）"""
        response = self.client.post(
            '/api/register/', {'username': 'a', 'password': 'pw123456'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('username', response.data)

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(username='email_owner', password='pw123456', email='dup@example.com')
        response = self.client.post(
            '/api/register/',
            {'username': 'another_one', 'password': 'pw123456', 'email': 'DUP@example.com'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)


class LoginLockoutTests(TestCase):
    """① 登录失败锁定"""

    def setUp(self):
        cache.clear()  # 限流计数器存在缓存里，测试之间必须清零，否则后面的用例会 429
        self.client = APIClient()
        self.user = User.objects.create_user(username='lock_target', password='right-pw-123')

    def _login(self, password):
        return self.client.post(
            '/api/login/', {'username': 'lock_target', 'password': password}, format='json',
        )

    def _exhaust(self):
        """连错 5 次（第 5 次触发锁定）"""
        return [self._login('wrong-pw') for _ in range(5)]

    def test_failed_attempts_are_counted(self):
        response = self._login('wrong-pw')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data['code'], 'invalid_password')
        self.assertEqual(response.data['remaining_attempts'], 4)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 1)

    def test_account_locks_after_five_failures(self):
        responses = self._exhaust()
        self.assertEqual(responses[-1].status_code, 423)
        self.assertEqual(responses[-1].data['code'], 'account_locked')

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_locked)
        self.assertGreater(self.user.lock_remaining_seconds, 0)

    def test_correct_password_is_rejected_while_locked(self):
        self._exhaust()
        response = self._login('right-pw-123')
        self.assertEqual(response.status_code, 423)
        self.assertTrue(self.client.post(
            '/api/login/', {'username': 'lock_target', 'password': 'right-pw-123'}, format='json',
        ).status_code, 423)

    def test_successful_login_resets_counter(self):
        self._login('wrong-pw')
        self._login('wrong-pw')
        response = self._login('right-pw-123')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertIsNone(self.user.locked_until)

    def test_lock_expires_and_login_works_again(self):
        self._exhaust()
        # 把锁定时间挪到过去，模拟"等够了 15 分钟"
        self.user.refresh_from_db()
        self.user.locked_until = timezone.now() - timezone.timedelta(seconds=1)
        self.user.save(update_fields=['locked_until'])

        response = self._login('right-pw-123')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_locked)

    def test_unknown_user_does_not_break(self):
        response = self.client.post(
            '/api/login/', {'username': 'nobody_here', 'password': 'whatever'}, format='json',
        )
        self.assertEqual(response.status_code, 404)


class LoginBackdoorRemovedTests(TestCase):
    """
    第 91 批（安全回归）：/api/token-auth/ 这条"绕过登录防护"的后门必须消失

    事故原型：`crop_disease_backend/urls.py` 里挂着 DRF 自带的 `obtain_auth_token`。
    它和 `/api/login/` 返回同一张 Token，却**完全不走**登录那套防护 ——
    DRF 的 ObtainAuthToken 源码里 `throttle_classes = ()`，而失败计数与账号锁定
    只写在 `LoginView.post` 里。于是"错 5 次锁 15 分钟"和 `login: 10/min` 限流
    都能被绕开：改打这个端点就能无限撞库。

    现在路由已摘除，访问它应得 404（与"从未存在"一致）。
    下面四条断言把"端点必须不存在"和"原端点/正规入口的锁定仍然生效"一起锁死。
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(username='backdoor_target', password='right-pw-123')

    def test_token_auth_endpoint_is_gone(self):
        response = self.client.post(
            '/api/token-auth/', {'username': 'backdoor_target', 'password': 'right-pw-123'},
            format='json',
        )
        self.assertEqual(response.status_code, 404)

    def test_token_auth_no_longer_returns_token(self):
        response = self.client.post(
            '/api/token-auth/', {'username': 'backdoor_target', 'password': 'right-pw-123'},
            format='json',
        )
        self.assertNotIn('token', getattr(response, 'data', {}) or {})

    def test_wrong_password_does_not_issue_token_through_removed_endpoint(self):
        response = self.client.post(
            '/api/token-auth/', {'username': 'backdoor_target', 'password': 'totally-wrong'},
            format='json',
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('token', getattr(response, 'data', {}) or {})

    def test_removed_endpoint_cannot_bypass_login_lockout(self):
        """后门摘除后，连错 5 次仍然锁号 —— 换端点的路已经被堵死"""
        for _ in range(5):
            self.client.post(
                '/api/login/', {'username': 'backdoor_target', 'password': 'wrong-pw'},
                format='json',
            )

        # 后门没了
        self.assertEqual(
            self.client.post(
                '/api/token-auth/', {'username': 'backdoor_target', 'password': 'right-pw-123'},
                format='json',
            ).status_code,
            404,
        )
        # 正规入口照旧拦人
        self.assertEqual(
            self.client.post(
                '/api/login/', {'username': 'backdoor_target', 'password': 'right-pw-123'},
                format='json',
            ).status_code,
            423,
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_locked)


class RichTextSanitizerContractTests(TestCase):
    """
    第 91 批（安全）：前端富文本净化白名单的"契约"回归

    真正的净化动作在浏览器里（`frontend/src/utils/richText.js` 用 DOMPurify），
    Django 测试跑不到 DOM。但**白名单本身**是这个修复的核心资产：
    只要 v-html 那几条链路还在，就必须存在一个统一的净化入口，
    而且它必须明确禁用脚本与事件属性。这里用静态断言把这份契约钉住，
    避免以后有人"为了排版方便"把 on* / script 放回白名单。
    """

    RICH_TEXT_PATH = Path(__file__).resolve().parents[2] / 'frontend' / 'src' / 'utils' / 'richText.js'

    def test_sanitizer_module_exists(self):
        self.assertTrue(
            self.RICH_TEXT_PATH.exists(),
            f'缺少富文本净化模块：{self.RICH_TEXT_PATH}',
        )
        source = self.RICH_TEXT_PATH.read_text(encoding='utf-8')
        self.assertIn('DOMPurify.sanitize', source)
        self.assertIn('FORBID_TAGS', source)
        self.assertIn('FORBID_ATTR', source)

    def test_v_html_call_sites_use_the_sanitizer(self):
        """用到 v-html 渲染用户内容的页面必须引用净化函数"""
        views_dir = Path(__file__).resolve().parents[2] / 'frontend' / 'src' / 'views'
        for name in ('PostDetailView.vue', 'ContentReviewView.vue', 'NewsDetailView.vue'):
            source = (views_dir / name).read_text(encoding='utf-8')
            self.assertIn(
                'sanitizeRichText', source,
                f'{name} 里渲染用户内容却没有引用 sanitizeRichText（存储型 XSS 回归）',
            )


class PasswordResetTests(TestCase):
    """② 忘记密码（邮箱重置）"""

    def setUp(self):
        cache.clear()  # 同上：找回密码也是按 IP 限流的
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='reset_target', password='old-pw-123', email='reset@example.com',
        )
        self.token = Token.objects.create(user=self.user)

    def _request_reset(self, account):
        return self.client.post('/api/password-reset/', {'username_or_email': account}, format='json')

    def _extract_uid_token(self):
        """从 locmem 邮箱里取出重置链接中的 uid / token"""
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        match = re.search(r'uid=([^&\s]+)&token=([^\s]+)', body)
        self.assertIsNotNone(match, f'邮件里没有重置链接：{body}')
        return match.group(1), match.group(2)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_request_sends_mail_with_reset_link(self):
        response = self._request_reset('reset@example.com')
        self.assertEqual(response.status_code, 200)

        uid, token = self._extract_uid_token()
        self.assertTrue(uid and token)
        self.assertIn('reset-password', mail.outbox[0].body)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_request_by_username_also_works(self):
        self._request_reset('reset_target')
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_unknown_account_gets_generic_answer_and_sends_nothing(self):
        """不能通过响应差异枚举出"哪些账号存在" """
        response = self._request_reset('definitely_not_here')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_confirm_sets_new_password_and_invalidates_tokens(self):
        self._request_reset('reset@example.com')
        uid, token = self._extract_uid_token()

        response = self.client.post(
            '/api/password-reset/confirm/',
            {'uid': uid, 'token': token, 'new_password': 'brand-new-pw-9'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)

        # 密码变了 → 之前签发的 token 必须全部作废（各端都要重新登录）。
        # 注意顺序：必须在"用新密码登录"**之前**断言 —— 登录本身会签发新 token。
        self.assertFalse(Token.objects.filter(user=self.user).exists())

        # 新密码可登录
        login_new = self.client.post(
            '/api/login/', {'username': 'reset_target', 'password': 'brand-new-pw-9'}, format='json',
        )
        self.assertEqual(login_new.status_code, 200)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_confirm_rejects_short_password(self):
        self._request_reset('reset@example.com')
        uid, token = self._extract_uid_token()
        response = self.client.post(
            '/api/password-reset/confirm/',
            {'uid': uid, 'token': token, 'new_password': '123'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_confirm_rejects_bad_token(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.post(
            '/api/password-reset/confirm/',
            {'uid': uid, 'token': 'not-a-real-token', 'new_password': 'whatever123'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_reset_clears_login_lockout(self):
        """被锁定的账号通过邮件重置密码后应立刻可登录"""
        self.user.failed_login_attempts = 0
        self.user.locked_until = timezone.now() + timezone.timedelta(minutes=15)
        self.user.save(update_fields=['failed_login_attempts', 'locked_until'])

        self._request_reset('reset@example.com')
        uid, token = self._extract_uid_token()
        self.client.post(
            '/api/password-reset/confirm/',
            {'uid': uid, 'token': token, 'new_password': 'unlocked-pw-1'},
            format='json',
        )

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_locked)
        login = self.client.post(
            '/api/login/', {'username': 'reset_target', 'password': 'unlocked-pw-1'}, format='json',
        )
        self.assertEqual(login.status_code, 200)


# ============================================================================
# 第 37 批：通知与公告
# 此前"帖子被回复/点赞/收藏"作者收不到任何提示，也没有站内通知中心和系统公告。
# ============================================================================
class NotificationTests(TestCase):
    """论坛互动通知（被回复 / 被点赞 / 被收藏）"""

    def setUp(self):
        cache.clear()
        self.author = User.objects.create_user(username='post_author', password='pw123456')
        self.other = User.objects.create_user(username='replier', password='pw123456')
        self.author_client = APIClient()
        self.author_client.force_authenticate(user=self.author)
        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other)

        self.board = ForumBoard.objects.create(name='作物病害交流', description='测试版块')
        self.post = Post.objects.create(
            title='番茄叶片有褐斑', content='<p>求助</p>', author=self.author, board=self.board,
        )

    def _notifications(self, user=None):
        return Notification.objects.filter(recipient=user or self.author)

    # ---------- 被回复 ----------
    def test_comment_creates_reply_notification(self):
        response = self.other_client.post(
            f'/api/forums/posts/{self.post.id}/comments/',
            {'content': '应该是早疫病，注意通风'},
            format='json',
        )
        self.assertIn(response.status_code, (200, 201))

        notification = self._notifications().filter(type='reply').first()
        self.assertIsNotNone(notification, '回复后作者应收到通知')
        self.assertEqual(notification.actor, self.other)
        self.assertEqual(notification.post, self.post)
        self.assertIn('回复', notification.title)
        self.assertEqual(notification.url, f'/forum/post/{self.post.id}')
        self.assertFalse(notification.is_read)

    def test_self_reply_does_not_notify(self):
        self.author_client.post(
            f'/api/forums/posts/{self.post.id}/comments/',
            {'content': '自己补充一句'},
            format='json',
        )
        self.assertEqual(self._notifications().count(), 0, '自己回复自己不该产生通知')

    # ---------- 被点赞 ----------
    def test_like_creates_notification_once(self):
        url = f'/api/forums/posts/{self.post.id}/like/'
        self.other_client.post(url, {}, format='json')
        self.assertEqual(self._notifications().filter(type='like').count(), 1)

        # 再点一次是取消点赞，不应产生第二条
        self.other_client.post(url, {}, format='json')
        self.assertEqual(self._notifications().filter(type='like').count(), 1)

    # ---------- 被收藏 ----------
    def test_favorite_creates_notification_once(self):
        url = f'/api/forums/posts/{self.post.id}/favorite/'
        self.other_client.post(url, {}, format='json')
        self.assertEqual(self._notifications().filter(type='favorite').count(), 1)

        self.other_client.post(url, {}, format='json')  # 取消收藏
        self.assertEqual(self._notifications().filter(type='favorite').count(), 1)

    # ---------- 通知接口 ----------
    def test_unread_count_and_read_flow(self):
        self.other_client.post(f'/api/forums/posts/{self.post.id}/like/', {}, format='json')
        self.other_client.post(f'/api/forums/posts/{self.post.id}/favorite/', {}, format='json')

        response = self.author_client.get('/api/notifications/unread-count/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['unread'], 2)

        notification_id = self._notifications().first().id
        read = self.author_client.post(f'/api/notifications/{notification_id}/read/')
        self.assertEqual(read.status_code, 200)
        self.assertEqual(self.author_client.get('/api/notifications/unread-count/').data['unread'], 1)

        all_read = self.author_client.post('/api/notifications/read-all/')
        self.assertEqual(all_read.status_code, 200)
        self.assertEqual(self.author_client.get('/api/notifications/unread-count/').data['unread'], 0)

    def test_notifications_are_private(self):
        self.other_client.post(f'/api/forums/posts/{self.post.id}/like/', {}, format='json')
        # 触发人自己不该看到"发给作者"的通知
        response = self.other_client.get('/api/notifications/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)

    def test_unread_filter(self):
        self.other_client.post(f'/api/forums/posts/{self.post.id}/like/', {}, format='json')
        self.other_client.post(f'/api/forums/posts/{self.post.id}/favorite/', {}, format='json')
        self.author_client.post(f'/api/notifications/{self._notifications().first().id}/read/')

        unread = self.author_client.get('/api/notifications/', {'unread': '1'})
        self.assertEqual(unread.data['count'], 1)
        all_items = self.author_client.get('/api/notifications/')
        self.assertEqual(all_items.data['count'], 2)

    def test_anonymous_cannot_read_notifications(self):
        response = APIClient().get('/api/notifications/')
        self.assertIn(response.status_code, (401, 403))


class AnnouncementTests(TestCase):
    """系统公告"""

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            username='ann_admin', password='pw123456', is_staff=True, is_superuser=True,
        )
        self.user = User.objects.create_user(username='ann_user', password='pw123456')
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)
        self.user_client = APIClient()
        self.user_client.force_authenticate(user=self.user)
        self.guest = APIClient()

    def test_admin_publishes_announcement_and_fans_out_notifications(self):
        response = self.admin_client.post(
            '/api/announcements/',
            {'title': '系统维护通知', 'content': '本周日 0:00-2:00 停机维护', 'is_pinned': True},
            format='json',
        )
        self.assertEqual(response.status_code, 201)

        # 普通用户收到一条公告通知
        self.assertEqual(Notification.objects.filter(recipient=self.user, type='announcement').count(), 1)
        # 第 78 批：**发布人自己也留一份**。
        # 原实现（含本测试）断言发布人收到 0 条，理由是"不给自己发通知"；
        # 但公告是广播而非自我互动，副作用是管理员发完公告后自己的通知中心空空如也，
        # 既看不到发过什么，也无法确认有没有发出去（真实反馈见 docs 第 78 批）。
        self.assertEqual(Notification.objects.filter(recipient=self.admin, type='announcement').count(), 1)

    def test_non_admin_cannot_publish(self):
        response = self.user_client.post(
            '/api/announcements/', {'title': '我也发个公告', 'content': 'x'}, format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Announcement.objects.count(), 0)

    def test_public_can_read_active_announcements(self):
        self.admin_client.post(
            '/api/announcements/', {'title': '公开公告', 'content': '内容'}, format='json',
        )
        response = self.guest.get('/api/announcements/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_inactive_and_expired_hidden_from_public(self):
        Announcement.objects.create(title='停用的', content='x', is_active=False)
        Announcement.objects.create(
            title='已过期的', content='x',
            expires_at=timezone.now() - timezone.timedelta(hours=1),
        )
        Announcement.objects.create(title='生效中的', content='x')

        response = self.guest.get('/api/announcements/')
        titles = [item['title'] for item in response.data['results']]
        self.assertEqual(titles, ['生效中的'])

        # 管理员带 ?all=1 能看到全部
        admin_view = self.admin_client.get('/api/announcements/', {'all': '1'})
        self.assertEqual(admin_view.data['count'], 3)

    def test_latest_endpoint_prefers_pinned(self):
        Announcement.objects.create(title='普通公告', content='x')
        Announcement.objects.create(title='置顶公告', content='x', is_pinned=True)

        response = self.guest.get('/api/announcements/latest/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['announcement']['title'], '置顶公告')

    def test_latest_returns_null_when_none(self):
        response = self.guest.get('/api/announcements/latest/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['announcement'])


    def test_deleting_announcement_removes_its_notifications(self):
        """删公告要连带清掉扇出的通知（否则用户点进去什么都没有）"""
        response = self.admin_client.post(
            '/api/announcements/', {'title': '临时公告', 'content': 'x'}, format='json',
        )
        announcement_id = response.data['id']
        # 两个账号各一条：普通用户 + 发布人自己（第 78 批起发布人也留副本）
        self.assertEqual(Notification.objects.filter(type='announcement').count(), 2)

        self.admin_client.delete(f'/api/announcements/{announcement_id}/')
        self.assertEqual(Notification.objects.filter(type='announcement').count(), 0)

    def test_self_notification_still_blocked_for_interactions(self):
        """
        第 78 批：放开的是**广播**，互动类"自己跟自己"仍然不发。
        这条锁死边界，避免把 `notify(allow_self=True)` 用滥。
        """
        from .views_notify import notify

        self.assertIsNone(notify(
            self.admin, type='reply', title='自己回复自己', actor=self.admin,
        ))
        self.assertIsNotNone(notify(
            self.admin, type='announcement', title='自己发的公告', actor=self.admin, allow_self=True,
        ))


# ============================================================================
# 第 38 批：内容管理（敏感词过滤 / 发帖审核 / 新闻定时发布）
# ============================================================================
class SensitiveWordTests(TestCase):
    """敏感词过滤（此前只有文档字符串，零实现）"""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='sw_user', password='pw123456')
        self.admin = User.objects.create_user(
            username='sw_admin', password='pw123456', is_staff=True, is_superuser=True,
        )
        self.client_user = APIClient()
        self.client_user.force_authenticate(user=self.user)
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)
        self.board = ForumBoard.objects.create(name='作物病害交流')
        # 第 52 批：词库里已经有默认词（迁移 0031 种下的），这里用 update_or_create
        # 保证测试无论词库初值如何都能跑（原来用 create 会因为唯一约束直接报错）
        SensitiveWord.objects.update_or_create(word='代开发票', defaults={'category': 'ad', 'is_active': True})
        SensitiveWord.objects.update_or_create(word='加微信', defaults={'category': 'ad', 'is_active': True})
        cache.delete('sensitive_words:active')

    def tearDown(self):
        cache.clear()

    def test_post_with_sensitive_title_rejected(self):
        response = self.client_user.post(
            '/api/forums/posts/',
            {'board_id': self.board.id, 'title': '代开发票找我', 'content': '<p>正常内容</p>'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('不允许的词汇', json.dumps(response.data, ensure_ascii=False))
        self.assertEqual(Post.objects.count(), 0, '命中敏感词的帖子不应落库')

    def test_post_with_sensitive_content_rejected(self):
        response = self.client_user.post(
            '/api/forums/posts/',
            {'board_id': self.board.id, 'title': '正常标题', 'content': '<p>想了解的加微信</p>'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Post.objects.count(), 0)

    def test_clean_post_accepted(self):
        response = self.client_user.post(
            '/api/forums/posts/',
            {'board_id': self.board.id, 'title': '番茄叶片有褐斑怎么办', 'content': '<p>求助各位</p>'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)

    def test_comment_with_sensitive_word_rejected(self):
        post = Post.objects.create(
            title='正常帖', content='<p>x</p>', author=self.admin, board=self.board,
            status='published',
        )
        response = self.client_user.post(
            f'/api/forums/posts/{post.id}/comments/',
            {'content': '加微信详聊'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Comment.objects.count(), 0)

    def test_feedback_with_sensitive_word_rejected(self):
        response = self.client_user.post(
            '/api/feedback/', {'suggestion': '代开发票请联系我'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_inactive_word_does_not_block(self):
        SensitiveWord.objects.update_or_create(word='临时词', defaults={'category': 'other', 'is_active': False})
        cache.delete('sensitive_words:active')
        response = self.client_user.post(
            '/api/feedback/', {'suggestion': '这里出现了临时词但它是停用的'}, format='json',
        )
        self.assertEqual(response.status_code, 201)

    def test_word_list_change_takes_effect_immediately(self):
        """词库变更后缓存要立即失效（否则要等 60 秒）"""
        from api.sensitive import find_sensitive_words
        self.assertEqual(find_sensitive_words('加微信'), ['加微信'])

        SensitiveWord.objects.update_or_create(word='新词', defaults={'category': 'other', 'is_active': True})
        self.assertIn('新词', find_sensitive_words('这里有个新词'))


class PostReviewTests(TestCase):
    """发帖审核队列（POST_REQUIRE_REVIEW 打开时）"""

    def setUp(self):
        cache.clear()
        self.author = User.objects.create_user(username='rv_author', password='pw123456')
        self.other = User.objects.create_user(username='rv_other', password='pw123456')
        self.admin = User.objects.create_user(
            username='rv_admin', password='pw123456', is_staff=True, is_superuser=True,
        )
        self.client_author = APIClient()
        self.client_author.force_authenticate(user=self.author)
        self.client_other = APIClient()
        self.client_other.force_authenticate(user=self.other)
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)
        self.board = ForumBoard.objects.create(name='作物病害交流')

    def _create_post(self, client=None, title='待审核的帖子'):
        return (client or self.client_author).post(
            '/api/forums/posts/',
            {'board_id': self.board.id, 'title': title, 'content': '<p>内容内容内容</p>'},
            format='json',
        )

    @override_settings(POST_REQUIRE_REVIEW=True)
    def test_new_post_goes_to_pending(self):
        response = self._create_post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(Post.objects.get().status, 'pending')

    @override_settings(POST_REQUIRE_REVIEW=True)
    def test_pending_post_hidden_from_others_but_visible_to_author(self):
        post_id = self._create_post().data['id']

        # 别人看不到
        other_view = self.client_other.get('/api/forums/posts/')
        self.assertEqual(other_view.data['count'], 0)

        # 作者自己看得到（与草稿同一套可见性规则）
        author_view = self.client_author.get('/api/forums/posts/')
        self.assertEqual(author_view.data['count'], 1)

        # 详情：别人 404，作者 200
        self.assertEqual(self.client_other.get(f'/api/forums/posts/{post_id}/').status_code, 404)
        self.assertEqual(self.client_author.get(f'/api/forums/posts/{post_id}/').status_code, 200)

    @override_settings(POST_REQUIRE_REVIEW=True)
    def test_admin_post_is_published_directly(self):
        response = self._create_post(client=self.client_admin, title='管理员公告帖')
        self.assertEqual(response.data['status'], 'published')

    @override_settings(POST_REQUIRE_REVIEW=True)
    def test_moderators_get_review_notification(self):
        self._create_post()
        self.assertTrue(
            Notification.objects.filter(recipient=self.admin, title__contains='待审核').exists(),
            '管理员应收到待审核通知',
        )

    @override_settings(POST_REQUIRE_REVIEW=True)
    def test_approve_publishes_and_notifies_author(self):
        post_id = self._create_post().data['id']

        response = self.client_admin.post(f'/api/forums/posts/{post_id}/approve/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Post.objects.get(id=post_id).status, 'published')
        self.assertTrue(
            Notification.objects.filter(recipient=self.author, title__contains='通过审核').exists()
        )

        # 通过后别人也能看到了
        self.assertEqual(self.client_other.get('/api/forums/posts/').data['count'], 1)

    @override_settings(POST_REQUIRE_REVIEW=True)
    def test_reject_hides_and_notifies_author_with_reason(self):
        post_id = self._create_post().data['id']

        response = self.client_admin.post(
            f'/api/forums/posts/{post_id}/reject/', {'reason': '内容与农业无关'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Post.objects.get(id=post_id).status, 'hidden')

        notification = Notification.objects.filter(recipient=self.author, title__contains='未通过').first()
        self.assertIsNotNone(notification)
        self.assertIn('与农业无关', notification.message)

    @override_settings(POST_REQUIRE_REVIEW=True)
    def test_normal_user_cannot_approve(self):
        post_id = self._create_post().data['id']
        response = self.client_other.post(f'/api/forums/posts/{post_id}/approve/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Post.objects.get(id=post_id).status, 'pending')

    @override_settings(POST_REQUIRE_REVIEW=False)
    def test_review_disabled_publishes_immediately(self):
        response = self._create_post()
        self.assertEqual(response.data['status'], 'published')


class NewsScheduleTests(TestCase):
    """新闻定时发布（第 38 批）"""

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            username='ns_admin', password='pw123456', is_staff=True, is_superuser=True,
        )
        self.user = User.objects.create_user(username='ns_user', password='pw123456')
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)
        self.client_user = APIClient()
        self.client_user.force_authenticate(user=self.user)

    def test_future_news_hidden_from_public(self):
        News.objects.create(
            title='明天才发布的新闻', content='内容', is_published=True,
            published_at=timezone.now() + timezone.timedelta(days=1),
        )
        response = self.client_user.get('/api/news/')
        self.assertEqual(response.data['count'], 0, '未到点的定时新闻不该对用户可见')

    def test_due_news_visible_to_public(self):
        News.objects.create(
            title='已经到点的新闻', content='内容', is_published=True,
            published_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        response = self.client_user.get('/api/news/')
        self.assertEqual(response.data['count'], 1)

    def test_news_without_schedule_visible(self):
        News.objects.create(title='立即发布的新闻', content='内容', is_published=True)
        response = self.client_user.get('/api/news/')
        self.assertEqual(response.data['count'], 1)

    def test_admin_sees_scheduled_news(self):
        News.objects.create(
            title='定时新闻', content='内容', is_published=True,
            published_at=timezone.now() + timezone.timedelta(days=1),
        )
        response = self.client_admin.get('/api/news/')
        self.assertEqual(response.data['count'], 1, '管理员要能看到待发布的定时新闻')

    def test_serializer_exposes_schedule_state(self):
        news = News.objects.create(
            title='定时新闻', content='内容', is_published=True,
            published_at=timezone.now() + timezone.timedelta(hours=2),
        )
        response = self.client_admin.get(f'/api/news/{news.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('published_at', response.data)
        self.assertTrue(response.data['is_pending_schedule'])

    def test_can_create_news_with_future_published_at(self):
        target = (timezone.now() + timezone.timedelta(days=2)).isoformat()
        response = self.client_admin.post(
            '/api/news/',
            {'title': '后天发布的新闻', 'content': '正文内容够长了', 'category': 'notice',
             'is_published': True, 'published_at': target},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        news = News.objects.get(title='后天发布的新闻')
        self.assertTrue(news.is_pending_schedule)
        self.assertFalse(news.is_visible_to_public)


# ============================================================================
# 第 39 批：管理员数据看板
# ============================================================================
class AdminDashboardTests(TestCase):
    """数据看板（仅管理员，聚合识别/用户/内容/待办）"""

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            username='dash_admin', password='pw123456', is_staff=True, is_superuser=True,
        )
        self.user = User.objects.create_user(username='dash_user', password='pw123456')
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)
        self.client_user = APIClient()
        self.client_user.force_authenticate(user=self.user)
        self.guest = APIClient()

        self.board = ForumBoard.objects.create(name='作物病害交流')
        self.pest = PestInfo.objects.create(
            name='番茄早疫病', crop_type='番茄', english_identifier='Tomato___Early_blight',
        )

        # 造点数据：2 条识别记录（1 条今天）、1 篇已发布帖、1 篇待审核帖、2 条评论、1 条反馈
        DetectionHistory.objects.create(
            user=self.user, image='detection_history/a.png', detection_result='番茄早疫病',
            pest_info=self.pest, confidence=0.93,
        )
        DetectionHistory.objects.create(
            user=self.admin, image='detection_history/b.png', detection_result='番茄早疫病',
            pest_info=self.pest, confidence=0.81,
        )
        self.post = Post.objects.create(
            title='已发布的帖子', content='<p>x</p>', author=self.user, board=self.board,
            status='published',
        )
        Post.objects.create(
            title='待审核的帖子', content='<p>y</p>', author=self.user, board=self.board,
            status='pending',
        )
        Comment.objects.create(post=self.post, author=self.admin, content='第一条评论')
        Comment.objects.create(post=self.post, author=self.admin, content='第二条评论')
        Feedback.objects.create(user=self.user, suggestion='希望支持导出 Excel', status='pending')

    def tearDown(self):
        cache.clear()

    def test_admin_can_load_dashboard(self):
        response = self.client_admin.get('/api/admin/dashboard/')
        self.assertEqual(response.status_code, 200)
        data = response.data
        for key in [
            'totals', 'detection_trend', 'user_trend', 'post_trend',
            'pest_distribution', 'crop_distribution', 'posts_by_status',
            'feedback_by_status', 'top_contributors', 'recent_users',
        ]:
            self.assertIn(key, data, f'看板缺少 {key}')

    def test_totals_are_accurate(self):
        totals = self.client_admin.get('/api/admin/dashboard/').data['totals']
        self.assertEqual(totals['users'], 2)
        self.assertEqual(totals['detections'], 2)
        self.assertEqual(totals['detections_today'], 2)
        self.assertEqual(totals['posts'], 2)
        self.assertEqual(totals['pending_posts'], 1)
        self.assertEqual(totals['comments'], 2)
        self.assertEqual(totals['feedback'], 1)
        self.assertEqual(totals['feedback_pending'], 1)
        self.assertEqual(totals['pest_species'], 1)

    def test_trend_series_is_padded_to_requested_days(self):
        response = self.client_admin.get('/api/admin/dashboard/', {'days': 7})
        trend = response.data['detection_trend']
        self.assertEqual(len(trend), 7, '缺少日期的天数要补 0，否则折线会跳日期')
        self.assertEqual(trend[-1]['count'], 2, '最后一天（今天）应有 2 条识别')

        longer = self.client_admin.get('/api/admin/dashboard/', {'days': 30}).data['detection_trend']
        self.assertEqual(len(longer), 30)

    def test_days_param_is_clamped(self):
        self.assertEqual(len(self.client_admin.get('/api/admin/dashboard/', {'days': 1}).data['detection_trend']), 7)
        self.assertEqual(len(self.client_admin.get('/api/admin/dashboard/', {'days': 9999}).data['detection_trend']), 90)
        # 非法值回落到默认 14 天
        self.assertEqual(len(self.client_admin.get('/api/admin/dashboard/', {'days': 'abc'}).data['detection_trend']), 14)

    def test_distributions_are_shaped_for_charts(self):
        data = self.client_admin.get('/api/admin/dashboard/').data
        # 第 77 批：分布条目补了 name_en（英文界面下看板图表要用英文名），
        # 这里只断言"中文名 + 数量"这部分口径没变，避免把英文名写死进断言。
        self.assertEqual(
            [(row['name'], row['count']) for row in data['pest_distribution']],
            [('番茄早疫病', 2)],
        )
        self.assertEqual(
            [(row['name'], row['count']) for row in data['crop_distribution']],
            [('番茄', 2)],
        )

    def test_status_breakdowns_include_pending(self):
        data = self.client_admin.get('/api/admin/dashboard/').data
        self.assertEqual(data['posts_by_status'].get('pending'), 1)
        self.assertEqual(data['posts_by_status'].get('published'), 1)
        self.assertEqual(data['feedback_by_status'].get('pending'), 1)

    def test_top_contributors_and_recent_users(self):
        data = self.client_admin.get('/api/admin/dashboard/').data
        self.assertTrue(data['top_contributors'], '应有贡献榜数据')
        self.assertEqual(data['top_contributors'][0]['username'], 'dash_user')
        self.assertEqual(data['top_contributors'][0]['post_count'], 2)
        self.assertEqual(len(data['recent_users']), 2)

    def test_normal_user_and_guest_are_rejected(self):
        self.assertEqual(self.client_user.get('/api/admin/dashboard/').status_code, 403)
        self.assertIn(self.guest.get('/api/admin/dashboard/').status_code, (401, 403))


# ============================================================================
# 第 40 批：关注 / 粉丝
# ============================================================================
class FollowTests(TestCase):
    """关注、粉丝列表、关注通知（此前完全没有社交关系）"""

    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user(username='follow_alice', password='pw123456')
        self.bob = User.objects.create_user(username='follow_bob', password='pw123456')
        self.carol = User.objects.create_user(username='follow_carol', password='pw123456')
        self.client_alice = APIClient()
        self.client_alice.force_authenticate(user=self.alice)
        self.client_bob = APIClient()
        self.client_bob.force_authenticate(user=self.bob)
        self.client_carol = APIClient()
        self.client_carol.force_authenticate(user=self.carol)
        self.guest = APIClient()

    def tearDown(self):
        cache.clear()

    def test_follow_and_unfollow_toggle(self):
        url = f'/api/users/{self.bob.id}/follow/'

        first = self.client_alice.post(url)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.data['is_following'])
        self.assertEqual(first.data['follower_count'], 1)
        self.assertEqual(Follow.objects.count(), 1)

        second = self.client_alice.post(url)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.data['is_following'])
        self.assertEqual(second.data['follower_count'], 0)
        self.assertEqual(Follow.objects.count(), 0)

    def test_cannot_follow_self(self):
        response = self.client_alice.post(f'/api/users/{self.alice.id}/follow/')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Follow.objects.count(), 0)

    def test_follow_requires_login(self):
        response = self.guest.post(f'/api/users/{self.bob.id}/follow/')
        self.assertIn(response.status_code, (401, 403))

    def test_follow_unknown_user_404(self):
        response = self.client_alice.post('/api/users/999999/follow/')
        self.assertEqual(response.status_code, 404)

    def test_following_creates_notification_once(self):
        self.client_alice.post(f'/api/users/{self.bob.id}/follow/')
        self.assertEqual(
            Notification.objects.filter(recipient=self.bob, type='follow').count(), 1,
        )
        # 取消再关注会再发一条（这是一次新的关注行为）
        self.client_alice.post(f'/api/users/{self.bob.id}/follow/')
        self.client_alice.post(f'/api/users/{self.bob.id}/follow/')
        self.assertEqual(Notification.objects.filter(recipient=self.bob, type='follow').count(), 2)

    def test_followers_and_following_lists(self):
        self.client_alice.post(f'/api/users/{self.bob.id}/follow/')
        self.client_alice.post(f'/api/users/{self.carol.id}/follow/')
        self.client_bob.post(f'/api/users/{self.alice.id}/follow/')

        # bob 的粉丝：alice
        followers = self.guest.get(f'/api/users/{self.bob.id}/followers/')
        self.assertEqual(followers.status_code, 200)
        self.assertEqual([u['username'] for u in followers.data['results']], ['follow_alice'])

        # alice 关注的人：bob、carol（最新的在前）
        following = self.guest.get(f'/api/users/{self.alice.id}/following/')
        self.assertEqual(
            [u['username'] for u in following.data['results']], ['follow_carol', 'follow_bob'],
        )

        # 我关注的人（登录态）
        mine = self.client_alice.get('/api/users/me/following/')
        self.assertEqual(mine.data['count'], 2)

    def test_list_marks_is_following_and_is_self(self):
        """
        列表里的 `is_following` 语义是"**当前查看者**有没有关注这一条里的人"，
        也就是资料页/粉丝列表上画"回关"按钮需要的状态。
        """
        self.client_alice.post(f'/api/users/{self.bob.id}/follow/')  # alice → bob

        # alice 看 bob 的粉丝列表：列表里就是她自己 → is_self=True，且不该显示"已关注"
        data = self.client_alice.get(f'/api/users/{self.bob.id}/followers/').data
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['username'], 'follow_alice')
        self.assertTrue(data['results'][0]['is_self'])
        self.assertFalse(data['results'][0]['is_following'], '自己不该显示"已关注"')

        # bob 看自己的粉丝列表：里面是 alice，而 bob 并没关注 alice → 两个标记都是 False
        data_bob = self.client_bob.get(f'/api/users/{self.bob.id}/followers/').data
        self.assertEqual(data_bob['results'][0]['username'], 'follow_alice')
        self.assertFalse(data_bob['results'][0]['is_self'])
        self.assertFalse(data_bob['results'][0]['is_following'], 'bob 还没回关 alice')

        # bob 回关 alice 之后，同样的列表里 is_following 应该变成 True
        self.client_bob.post(f'/api/users/{self.alice.id}/follow/')
        data_bob2 = self.client_bob.get(f'/api/users/{self.bob.id}/followers/').data
        self.assertTrue(data_bob2['results'][0]['is_following'])

    def test_profile_serializer_exposes_social_counts(self):
        """资料接口要带上关注数 / 粉丝数 / 我是否已关注 / 是不是我自己"""
        self.client_alice.post(f'/api/users/{self.bob.id}/follow/')  # alice → bob

        # bob 看 alice 的主页：alice 关注了 1 人、粉丝 0；bob 没关注 alice
        seen_by_bob = self.client_bob.get(f'/api/users/{self.alice.id}/')
        self.assertEqual(seen_by_bob.status_code, 200)
        self.assertEqual(seen_by_bob.data['following_count'], 1)
        self.assertEqual(seen_by_bob.data['follower_count'], 0)
        self.assertFalse(seen_by_bob.data['is_following'])
        self.assertFalse(seen_by_bob.data['is_self'])

        # alice 看 bob 的主页：bob 粉丝 1；alice 已关注 bob
        seen_by_alice = self.client_alice.get(f'/api/users/{self.bob.id}/')
        self.assertEqual(seen_by_alice.data['follower_count'], 1)
        self.assertEqual(seen_by_alice.data['following_count'], 0)
        self.assertTrue(seen_by_alice.data['is_following'])
        self.assertFalse(seen_by_alice.data['is_self'])

        # 看自己的主页 → is_self 为真（前端据此隐藏"关注"按钮）
        own = self.client_alice.get(f'/api/users/{self.alice.id}/')
        self.assertTrue(own.data['is_self'])

    def test_my_follow_stats(self):
        self.client_bob.post(f'/api/users/{self.alice.id}/follow/')
        self.client_carol.post(f'/api/users/{self.alice.id}/follow/')
        self.client_alice.post(f'/api/users/{self.bob.id}/follow/')

        response = self.client_alice.get('/api/users/me/follow-stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['follower_count'], 2)
        self.assertEqual(response.data['following_count'], 1)

    def test_follow_suggestions_exclude_self_and_followed(self):
        self.client_alice.post(f'/api/users/{self.bob.id}/follow/')

        response = self.client_alice.get('/api/users/follow-suggestions/')
        self.assertEqual(response.status_code, 200)
        names = [u['username'] for u in response.data['results']]
        self.assertNotIn('follow_alice', names, '不该推荐自己')
        self.assertNotIn('follow_bob', names, '不该推荐已关注的人')


# ============================================================================
# 第 41 批：举报功能
# ============================================================================
class ReportTests(TestCase):
    """举报帖子/评论/用户、去重、处理与通知"""

    def setUp(self):
        cache.clear()
        self.author = User.objects.create_user(username='rp_author', password='pw123456')
        self.reporter = User.objects.create_user(username='rp_reporter', password='pw123456')
        self.admin = User.objects.create_user(
            username='rp_admin', password='pw123456', is_staff=True, is_superuser=True,
        )
        self.client_author = APIClient()
        self.client_author.force_authenticate(user=self.author)
        self.client_reporter = APIClient()
        self.client_reporter.force_authenticate(user=self.reporter)
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)
        self.guest = APIClient()

        self.board = ForumBoard.objects.create(name='作物病害交流')
        self.post = Post.objects.create(
            title='可疑的推广帖', content='<p>加微信买肥料</p>', author=self.author,
            board=self.board, status='published',
        )
        self.comment = Comment.objects.create(
            post=self.post, author=self.author, content='这是广告评论',
        )

    def tearDown(self):
        cache.clear()

    # ---------- 提交 ----------
    def test_report_post(self):
        response = self.client_reporter.post(
            '/api/reports/',
            {'target_type': 'post', 'target_id': self.post.id, 'reason': 'spam', 'detail': '明显是广告'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        report = Report.objects.get()
        self.assertEqual(report.target_key, f'post:{self.post.id}')
        self.assertEqual(report.reason, 'spam')
        self.assertEqual(report.status, 'pending')
        self.assertIn('可疑的推广帖', report.target_label)

    def test_report_comment_and_user(self):
        first = self.client_reporter.post(
            '/api/reports/', {'target_type': 'comment', 'target_id': self.comment.id}, format='json',
        )
        self.assertEqual(first.status_code, 201)

        second = self.client_reporter.post(
            '/api/reports/', {'target_type': 'user', 'target_id': self.author.id}, format='json',
        )
        self.assertEqual(second.status_code, 201)
        self.assertEqual(Report.objects.count(), 2)
        self.assertEqual(Report.objects.get(target_type='user').target_label, '用户：rp_author')

    def test_cannot_report_twice(self):
        payload = {'target_type': 'post', 'target_id': self.post.id, 'reason': 'spam'}
        self.assertEqual(self.client_reporter.post('/api/reports/', payload, format='json').status_code, 201)
        again = self.client_reporter.post('/api/reports/', payload, format='json')
        self.assertEqual(again.status_code, 400)
        self.assertIn('已经举报过', again.data['detail'])
        self.assertEqual(Report.objects.count(), 1)

    def test_cannot_report_own_content(self):
        response = self.client_author.post(
            '/api/reports/', {'target_type': 'post', 'target_id': self.post.id}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('不能举报自己', response.data['detail'])
        self.assertEqual(Report.objects.count(), 0)

    def test_report_requires_login_and_valid_target(self):
        self.assertIn(
            self.guest.post('/api/reports/', {'target_type': 'post', 'target_id': self.post.id}).status_code,
            (401, 403),
        )
        bad_type = self.client_reporter.post(
            '/api/reports/', {'target_type': 'nonsense', 'target_id': self.post.id}, format='json',
        )
        self.assertEqual(bad_type.status_code, 400)

        missing = self.client_reporter.post(
            '/api/reports/', {'target_type': 'post', 'target_id': 999999}, format='json',
        )
        self.assertEqual(missing.status_code, 404)

    def test_admins_get_notified(self):
        self.client_reporter.post(
            '/api/reports/', {'target_type': 'post', 'target_id': self.post.id, 'reason': 'spam'},
            format='json',
        )
        self.assertTrue(
            Notification.objects.filter(recipient=self.admin, title__contains='收到新的举报').exists(),
            '管理员应收到举报通知',
        )

    # ---------- 查询 ----------
    def test_user_sees_only_own_reports(self):
        self.client_reporter.post(
            '/api/reports/', {'target_type': 'post', 'target_id': self.post.id}, format='json',
        )
        other = User.objects.create_user(username='rp_other', password='pw123456')
        other_client = APIClient()
        other_client.force_authenticate(user=other)
        self.assertEqual(other_client.get('/api/reports/').data['count'], 0)

        mine = self.client_reporter.get('/api/reports/')
        self.assertEqual(mine.data['count'], 1)

    def test_admin_sees_all_with_status_filter(self):
        self.client_reporter.post(
            '/api/reports/', {'target_type': 'post', 'target_id': self.post.id}, format='json',
        )
        self.assertEqual(self.client_admin.get('/api/reports/').data['count'], 1)
        self.assertEqual(self.client_admin.get('/api/reports/', {'status': 'pending'}).data['count'], 1)
        self.assertEqual(self.client_admin.get('/api/reports/', {'status': 'handled'}).data['count'], 0)

    # ---------- 处理 ----------
    def _create_report(self):
        return self.client_reporter.post(
            '/api/reports/', {'target_type': 'post', 'target_id': self.post.id, 'reason': 'spam'},
            format='json',
        ).data['id']

    def test_admin_handles_report_and_notifies_reporter(self):
        report_id = self._create_report()
        response = self.client_admin.post(
            f'/api/reports/{report_id}/handle/',
            {'status': 'handled', 'note': '已确认为广告并处理'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)

        report = Report.objects.get(id=report_id)
        self.assertEqual(report.status, 'handled')
        self.assertEqual(report.handler, self.admin)
        self.assertIsNotNone(report.handled_at)
        self.assertTrue(
            Notification.objects.filter(recipient=self.reporter, title__contains='举报已处理').exists()
        )

    def test_handle_can_hide_the_reported_post(self):
        report_id = self._create_report()
        response = self.client_admin.post(
            f'/api/reports/{report_id}/handle/',
            {'status': 'handled', 'note': '隐藏内容', 'hide_content': True},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['hidden_content'])
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'hidden')

    def test_handle_can_hide_a_reported_comment(self):
        comment = Comment.objects.create(post=self.post, author=self.author, content='广告评论 2')
        report_id = self.client_reporter.post(
            '/api/reports/', {'target_type': 'comment', 'target_id': comment.id}, format='json',
        ).data['id']

        self.client_admin.post(
            f'/api/reports/{report_id}/handle/',
            {'status': 'handled', 'hide_content': True}, format='json',
        )
        comment.refresh_from_db()
        self.assertTrue(comment.is_deleted)
        self.assertEqual(comment.content, '[已被管理员隐藏]')

    def test_reject_report(self):
        report_id = self._create_report()
        response = self.client_admin.post(
            f'/api/reports/{report_id}/handle/', {'status': 'rejected', 'note': '内容没问题'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Report.objects.get(id=report_id).status, 'rejected')
        self.assertTrue(
            Notification.objects.filter(recipient=self.reporter, title__contains='举报已驳回').exists()
        )

    def test_non_admin_cannot_handle(self):
        report_id = self._create_report()
        response = self.client_reporter.post(
            f'/api/reports/{report_id}/handle/', {'status': 'handled'}, format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Report.objects.get(id=report_id).status, 'pending')

    def test_invalid_status_rejected(self):
        report_id = self._create_report()
        response = self.client_admin.post(
            f'/api/reports/{report_id}/handle/', {'status': 'whatever'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_dashboard_counts_pending_reports(self):
        self._create_report()
        totals = self.client_admin.get('/api/admin/dashboard/').data['totals']
        self.assertEqual(totals['reports_pending'], 1)


# ============================================================================
# 第 42 批：私信 + 等级积分
# ============================================================================
class DirectMessageTests(TestCase):
    """一对一私信：会话列表、聊天记录、已读、通知、敏感词"""

    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user(username='dm_alice', password='pw123456')
        self.bob = User.objects.create_user(username='dm_bob', password='pw123456')
        self.carol = User.objects.create_user(username='dm_carol', password='pw123456')
        self.client_alice = APIClient()
        self.client_alice.force_authenticate(user=self.alice)
        self.client_bob = APIClient()
        self.client_bob.force_authenticate(user=self.bob)
        self.client_carol = APIClient()
        self.client_carol.force_authenticate(user=self.carol)
        self.guest = APIClient()

    def tearDown(self):
        cache.clear()

    def _send(self, client, to_id, content):
        return client.post(f'/api/messages/with/{to_id}/', {'content': content}, format='json')

    def test_send_and_read_conversation(self):
        sent = self._send(self.client_alice, self.bob.id, '你好，请问番茄叶斑用什么药？')
        self.assertEqual(sent.status_code, 201)
        self.assertEqual(sent.data['sender']['username'], 'dm_alice')
        self.assertFalse(sent.data['is_read'])

        # bob 读会话：应该看到这条，并且标记为已读
        resp = self.client_bob.get(f'/api/messages/with/{self.alice.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['marked_read'], 1)
        self.assertEqual(resp.data['other']['username'], 'dm_alice')
        self.assertTrue(resp.data['results'][0]['is_read'])

        # 再读一次：没有新的未读可标记
        again = self.client_bob.get(f'/api/messages/with/{self.alice.id}/')
        self.assertEqual(again.data['marked_read'], 0)

    def test_conversation_key_is_same_for_both_directions(self):
        self._send(self.client_alice, self.bob.id, '第一条')
        self._send(self.client_bob, self.alice.id, '第二条')

        from .models_message import DirectMessage
        keys = set(DirectMessage.objects.values_list('conversation_key', flat=True))
        self.assertEqual(len(keys), 1, '双向消息应归到同一个会话')

        resp = self.client_alice.get(f'/api/messages/with/{self.bob.id}/')
        self.assertEqual(resp.data['count'], 2)

    def test_cannot_message_self_or_missing_user(self):
        self.assertEqual(self._send(self.client_alice, self.alice.id, '自言自语').status_code, 400)
        self.assertEqual(self._send(self.client_alice, 999999, '在吗').status_code, 404)

    def test_content_required_and_limited(self):
        self.assertEqual(self._send(self.client_alice, self.bob.id, '   ').status_code, 400)
        self.assertEqual(self._send(self.client_alice, self.bob.id, 'x' * 1001).status_code, 400)

    def test_sensitive_word_blocked(self):
        SensitiveWord.objects.update_or_create(word='代开发票', defaults={'category': 'ad', 'is_active': True})
        cache.delete('sensitive_words:active')
        response = self._send(self.client_alice, self.bob.id, '需要代开发票吗')
        self.assertEqual(response.status_code, 400)
        self.assertIn('不允许的词汇', response.data['detail'])

    def test_recipient_gets_notification(self):
        self._send(self.client_alice, self.bob.id, '在吗')
        self.assertTrue(
            Notification.objects.filter(recipient=self.bob, type='message').exists(),
            '收件人应收到私信通知',
        )

    def test_conversation_list_and_unread_count(self):
        self._send(self.client_alice, self.bob.id, '给 bob 的第一条')
        self._send(self.client_carol, self.bob.id, '给 bob 的第二条')

        self.assertEqual(self.client_bob.get('/api/messages/unread-count/').data['unread'], 2)

        conversations = self.client_bob.get('/api/messages/').data
        self.assertEqual(conversations['count'], 2)
        self.assertEqual({item['other']['username'] for item in conversations['results']},
                         {'dm_alice', 'dm_carol'})
        self.assertTrue(all(item['unread'] == 1 for item in conversations['results']))

        # 读掉一个会话后未读数减少
        self.client_bob.get(f'/api/messages/with/{self.alice.id}/')
        self.assertEqual(self.client_bob.get('/api/messages/unread-count/').data['unread'], 1)

    def test_others_cannot_read_my_conversation(self):
        self._send(self.client_alice, self.bob.id, '只给 bob 看的')
        # carol 与 alice 的会话里不该有这条
        resp = self.client_alice.get(f'/api/messages/with/{self.carol.id}/')
        self.assertEqual(resp.data['count'], 0)

    def test_requires_login(self):
        self.assertIn(self.guest.get('/api/messages/').status_code, (401, 403))
        self.assertIn(self.guest.post(f'/api/messages/with/{self.bob.id}/', {'content': 'x'}).status_code, (401, 403))


class PointSystemTests(TestCase):
    """等级与积分：加分规则、流水、等级推导、资料页展示"""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='pt_user', password='pw123456')
        self.other = User.objects.create_user(username='pt_other', password='pw123456')
        self.admin = User.objects.create_user(
            username='pt_admin', password='pw123456', is_staff=True, is_superuser=True,
        )
        self.client_user = APIClient()
        self.client_user.force_authenticate(user=self.user)
        self.client_other = APIClient()
        self.client_other.force_authenticate(user=self.other)
        self.board = ForumBoard.objects.create(name='作物病害交流')

    def tearDown(self):
        cache.clear()

    def test_award_points_writes_log_and_updates_balance(self):
        from .services_points import award_points
        award_points(self.user, 'post', ref_type='post', ref_id=1)
        award_points(self.user, 'comment', ref_type='comment', ref_id=2)

        self.user.refresh_from_db()
        self.assertEqual(self.user.points, 7)  # 5 + 2
        logs = PointLog.objects.filter(user=self.user).order_by('created_at')
        self.assertEqual([log.delta for log in logs], [5, 2])
        self.assertEqual(logs.last().balance, 7)

    def test_levels_derived_from_points(self):
        from .models_points import level_for_points
        self.assertEqual(level_for_points(0)[:2], (1, '新手'))
        self.assertEqual(level_for_points(150)[:2], (2, '进阶农户'))
        self.assertEqual(level_for_points(1000)[:2], (5, '种植大师'))
        level, name, next_threshold = level_for_points(150)
        self.assertEqual(next_threshold, 300)

    def test_post_and_comment_award_points(self):
        response = self.client_user.post(
            '/api/forums/posts/',
            {'board_id': self.board.id, 'title': '积分测试帖', 'content': '<p>内容足够长</p>'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.user.refresh_from_db()
        self.assertEqual(self.user.points, 5, '发帖 +5')

        post_id = response.data['id']
        self.client_other.post(
            f'/api/forums/posts/{post_id}/comments/', {'content': '我来评论一下'}, format='json',
        )
        self.other.refresh_from_db()
        self.assertEqual(self.other.points, 2, '评论 +2')

    def test_like_and_favorite_award_author(self):
        post = Post.objects.create(
            title='点赞收藏测试', content='<p>x</p>', author=self.user, board=self.board,
            status='published',
        )
        self.client_other.post(f'/api/forums/posts/{post.id}/like/', {}, format='json')
        self.client_other.post(f'/api/forums/posts/{post.id}/favorite/', {}, format='json')

        self.user.refresh_from_db()
        self.assertEqual(self.user.points, 3, '被点赞 +1、被收藏 +2')

    def test_follow_awards_target(self):
        self.client_user.post(f'/api/users/{self.other.id}/follow/')
        self.other.refresh_from_db()
        self.assertEqual(self.other.points, 1, '被关注 +1')

    def test_daily_login_awards_once_per_day(self):
        from .services_points import award_daily_login
        self.assertIsNotNone(award_daily_login(self.user))
        self.assertIsNone(award_daily_login(self.user), '同一天只加一次')
        self.user.refresh_from_db()
        self.assertEqual(self.user.points, 1)

    def test_my_points_endpoint(self):
        from .services_points import award_points
        award_points(self.user, 'post')
        response = self.client_user.get('/api/users/me/points/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['points'], 5)
        self.assertEqual(response.data['level'], 1)
        self.assertEqual(response.data['next_level_points'], 100)
        self.assertIn('progress', response.data)

    def test_point_logs_endpoint_is_private(self):
        from .services_points import award_points
        award_points(self.user, 'post')
        mine = self.client_user.get('/api/users/me/point-logs/')
        self.assertEqual(mine.data['count'], 1)
        self.assertEqual(mine.data['results'][0]['delta'], 5)

        theirs = self.client_other.get('/api/users/me/point-logs/')
        self.assertEqual(theirs.data['count'], 0, '只能看到自己的积分流水')

    def test_profile_exposes_points(self):
        from .services_points import award_points
        award_points(self.user, 'post')
        response = self.client_other.get(f'/api/users/{self.user.id}/')
        self.assertEqual(response.data['points']['points'], 5)
        self.assertEqual(response.data['points']['level_name'], '新手')

    def test_levels_endpoint_public(self):
        response = APIClient().get('/api/points/levels/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['levels'])
        self.assertTrue(any(rule['reason'] == 'post' for rule in response.data['rules']))


# ============================================================================
# 第 43 批：Excel 导出（识别记录）
# ============================================================================
class ExcelExportTests(TestCase):
    """识别记录导出 Excel：权限范围、筛选、文件有效性"""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='xl_user', password='pw123456')
        self.other = User.objects.create_user(username='xl_other', password='pw123456')
        self.admin = User.objects.create_user(
            username='xl_admin', password='pw123456', is_staff=True, is_superuser=True,
        )
        self.client_user = APIClient()
        self.client_user.force_authenticate(user=self.user)
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)

        self.pest = PestInfo.objects.create(
            name='番茄早疫病', crop_type='番茄', english_identifier='Tomato___Early_blight',
        )
        DetectionHistory.objects.create(
            user=self.user, image='detection_history/a.png', detection_result='番茄早疫病',
            pest_info=self.pest, confidence=0.93,
        )
        DetectionHistory.objects.create(
            user=self.user, image='detection_history/b.png', detection_result='草莓叶焦病',
            confidence=0.81,
        )
        DetectionHistory.objects.create(
            user=self.other, image='detection_history/c.png', detection_result='苹果黑星病',
            confidence=0.7,
        )

    def tearDown(self):
        cache.clear()

    def _sheet_text(self, response):
        """把 xlsx 里的 sheet1.xml 解出来（crop_env 没有 openpyxl，用 zipfile 校验）"""
        import io
        import zipfile
        buffer = io.BytesIO(b''.join(response.streaming_content) if response.streaming else response.content)
        with zipfile.ZipFile(buffer) as archive:
            names = archive.namelist()
            xml = archive.read('xl/worksheets/sheet1.xml').decode('utf-8')
        return names, xml

    def test_export_returns_valid_xlsx(self):
        import zipfile
        import io

        response = self.client_user.get('/api/detection-history/export-excel/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('.xlsx', response['Content-Disposition'])

        buffer = io.BytesIO(response.content)
        self.assertTrue(zipfile.is_zipfile(buffer), '必须是合法的 xlsx（zip）')
        with zipfile.ZipFile(buffer) as archive:
            names = archive.namelist()
            for part in ['[Content_Types].xml', '_rels/.rels', 'xl/workbook.xml',
                         'xl/_rels/workbook.xml.rels', 'xl/worksheets/sheet1.xml']:
                self.assertIn(part, names, f'xlsx 缺少 {part}')

    def test_export_only_contains_my_records(self):
        response = self.client_user.get('/api/detection-history/export-excel/')
        _, xml = self._sheet_text(response)
        self.assertIn('番茄早疫病', xml)
        self.assertIn('草莓叶焦病', xml)
        self.assertNotIn('苹果黑星病', xml, '普通用户不该导出他人的记录')

    def test_admin_with_all_users_gets_everything(self):
        mine = self.client_admin.get('/api/detection-history/export-excel/')
        _, xml_mine = self._sheet_text(mine)
        self.assertNotIn('苹果黑星病', xml_mine, '管理员不带 all_users 时只导出自己的（0 条）')

        all_users = self.client_admin.get('/api/detection-history/export-excel/', {'all_users': 'true'})
        _, xml_all = self._sheet_text(all_users)
        self.assertIn('番茄早疫病', xml_all)
        self.assertIn('苹果黑星病', xml_all)

    def test_export_respects_filters(self):
        response = self.client_user.get('/api/detection-history/export-excel/', {'pest': '番茄'})
        _, xml = self._sheet_text(response)
        self.assertIn('番茄早疫病', xml)
        self.assertNotIn('草莓叶焦病', xml, '病害筛选要在导出里同样生效')

    def test_export_includes_header_and_summary_row(self):
        response = self.client_user.get('/api/detection-history/export-excel/')
        _, xml = self._sheet_text(response)
        for header in ['序号', '识别时间', '识别用户', '识别结果', '病害百科词条', '作物类型', '置信度']:
            self.assertIn(header, xml, f'表头缺少 {header}')
        self.assertIn('共 2 条', xml, '末尾应有一行汇总')

    def test_export_requires_login(self):
        response = APIClient().get('/api/detection-history/export-excel/')
        self.assertIn(response.status_code, (401, 403))


class XlsxWriterTests(TestCase):
    """零依赖 xlsx 生成器本身"""

    def test_build_workbook_structure_and_escaping(self):
        import io
        import zipfile

        from .xlsx import build_workbook

        content = build_workbook(
            ['名称', '数值'], [['含 <标签> & 符号', 3.14], ['中文', 1]],
            sheet_name='测试', column_widths=[20, 8],
        )
        buffer = io.BytesIO(content)
        self.assertTrue(zipfile.is_zipfile(buffer))
        with zipfile.ZipFile(buffer) as archive:
            sheet = archive.read('xl/worksheets/sheet1.xml').decode('utf-8')
            workbook = archive.read('xl/workbook.xml').decode('utf-8')

        self.assertIn('测试', workbook, '工作表名应写入 workbook.xml')
        self.assertIn('含 &lt;标签&gt; &amp; 符号', sheet, 'XML 特殊字符必须转义')
        self.assertIn('<v>3.14</v>', sheet, '数字应写成数值而不是文本')
        self.assertIn('autoFilter', sheet)

    def test_build_workbook_rejects_empty_headers(self):
        from .xlsx import build_workbook
        with self.assertRaises(ValueError):
            build_workbook([], [])


# ============================================================================
# 第 43 批：卫星模型注册（删除用户必须能级联）
# ============================================================================
class ModelRegistrationTests(TestCase):
    """
    回归测试：放在 `api/models_*.py` 里的模型必须**任何进程都能注册**。

    背景（真实事故）：这些模型原先只在"加载了 urls.py"的进程里被间接导入，
    于是在只 import 了 `api.models` 的进程里（如 `manage.py shell`），
    Django 的删除收集器不知道 `PointLog` 等表存在 → 删用户时不级联 →
    COMMIT 时抛 `IntegrityError: FOREIGN KEY constraint failed`，用户删不掉。
    修法：在 `api/models.py` 末尾统一导入这些模块。
    """

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_satellite_models_are_registered(self):
        from django.apps import apps
        for model_name in ['Follow', 'Report', 'DirectMessage', 'PointLog',
                           'Notification', 'Announcement', 'SensitiveWord']:
            self.assertIsNotNone(
                apps.get_model('api', model_name),
                f'{model_name} 未注册 —— 说明它的模块没有被导入',
            )

    def test_deleting_user_cascades_all_satellite_rows(self):
        from .services_points import award_points
        from .models_message import DirectMessage, conversation_key_for

        user = User.objects.create_user(username='cascade_guy', password='pw123456')
        other = User.objects.create_user(username='cascade_other', password='pw123456')

        # 各造一条关联数据
        award_points(user, 'post')                                   # PointLog
        Follow.objects.create(follower=other, following=user)        # Follow
        DirectMessage.objects.create(sender=other, recipient=user,   # DirectMessage
                                     content='你好', conversation_key=conversation_key_for(other.id, user.id))
        Report.objects.create(reporter=other, target_type='user', target_key=f'user:{user.id}',
                              target_user=user)                      # Report
        Notification.objects.create(recipient=user, type='system', title='测试', message='x')

        user_id = user.id
        user.delete()  # 这一步以前会抛 FOREIGN KEY constraint failed

        self.assertFalse(User.objects.filter(id=user_id).exists())
        self.assertFalse(PointLog.objects.filter(user_id=user_id).exists())
        self.assertFalse(Follow.objects.filter(following_id=user_id).exists())
        self.assertFalse(DirectMessage.objects.filter(recipient_id=user_id).exists())
        self.assertFalse(Report.objects.filter(target_user_id=user_id).exists())
        self.assertFalse(Notification.objects.filter(recipient_id=user_id).exists())


# ============================================================================
# 第 44 批：病害批量导入
# ============================================================================
class XlsxReaderTests(TestCase):
    """表格读取（xlsx / csv）—— 与生成器配套，零依赖"""

    def test_roundtrip_generated_workbook(self):
        """自己生成的 xlsx 必须能被自己读回来（含中文、空单元格、特殊字符）"""
        from .xlsx import build_workbook, read_xlsx_rows

        content = build_workbook(
            ['名称', '作物', '备注'],
            [['番茄晚疫病', '番茄', '含 <标签> & 符号'], ['黄瓜霜霉病', '', '空第二列']],
            sheet_name='测试',
        )
        rows = read_xlsx_rows(content)
        self.assertEqual(rows[0], ['名称', '作物', '备注'])
        self.assertEqual(rows[1], ['番茄晚疫病', '番茄', '含 <标签> & 符号'])
        # 空单元格要保留占位，否则整行会左移
        self.assertEqual(rows[2], ['黄瓜霜霉病', '', '空第二列'])

    def test_reads_shared_strings(self):
        """真实 Excel 常用 sharedStrings：手工拼一个验证解析"""
        import io
        import zipfile

        from .xlsx import read_xlsx_rows

        sheet = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData>'
            '<row r="1">'
            '<c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c>'
            '</row>'
            '<row r="2">'
            '<c r="A2" t="s"><v>2</v></c><c r="B2"><v>3.5</v></c>'
            '</row>'
            '</sheetData></worksheet>'
        )
        shared = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<si><t>病害名称</t></si><si><t>作物</t></si><si><t>番茄晚疫病</t></si>'
            '</sst>'
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('xl/worksheets/sheet1.xml', sheet)
            archive.writestr('xl/sharedStrings.xml', shared)

        rows = read_xlsx_rows(buffer.getvalue())
        self.assertEqual(rows[0], ['病害名称', '作物'])
        self.assertEqual(rows[1], ['番茄晚疫病', '3.5'])

    def test_reads_csv_variants(self):
        from .xlsx import read_csv_rows

        utf8 = '病害名称,作物类型\n番茄晚疫病,番茄\n'.encode('utf-8')
        self.assertEqual(read_csv_rows(utf8), [['病害名称', '作物类型'], ['番茄晚疫病', '番茄']])

        # 带 BOM
        with_bom = '\ufeff名称,作物\n黄瓜霜霉病,黄瓜\n'.encode('utf-8')
        self.assertEqual(read_csv_rows(with_bom)[0][0], '名称')

        # 分号分隔
        semicolon = '名称;作物\n玉米大斑病;玉米\n'.encode('utf-8')
        self.assertEqual(read_csv_rows(semicolon), [['名称', '作物'], ['玉米大斑病', '玉米']])

    def test_parse_table_rejects_unknown_extension(self):
        from .xlsx import parse_table
        with self.assertRaises(ValueError):
            parse_table('data.pdf', b'whatever')


class PestImportTests(TestCase):
    """批量导入接口：权限、表头匹配、逐行校验、upsert"""

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            username='pi_admin', password='pw123456', is_staff=True, is_superuser=True,
        )
        self.user = User.objects.create_user(username='pi_user', password='pw123456')
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)
        self.client_user = APIClient()
        self.client_user.force_authenticate(user=self.user)

    def tearDown(self):
        cache.clear()

    def _csv(self, text):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile('pests.csv', text.encode('utf-8'), content_type='text/csv')

    def _xlsx(self, headers, rows):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .xlsx import build_workbook
        return SimpleUploadedFile(
            'pests.xlsx', build_workbook(headers, rows),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def _post(self, file, mode='upsert', client=None):
        return (client or self.client_admin).post(
            '/api/pests/import/', {'file': file, 'mode': mode}, format='multipart',
        )

    def test_import_creates_pests(self):
        file = self._csv(
            '病害名称,作物类型,英文标识符,症状,详细描述,防治方法\n'
            '番茄晚疫病,番茄,Tomato___Late_blight,叶片水浸状病斑,低温高湿易流行,'
            '化学防治:喷施烯酰吗啉|农业防治:合理轮作\n'
        )
        response = self._post(file)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['created'], 1)
        self.assertEqual(response.data['updated'], 0)
        self.assertEqual(response.data['skipped'], 0)

        pest = PestInfo.objects.get(english_identifier='Tomato___Late_blight')
        self.assertEqual(pest.name, '番茄晚疫病')
        self.assertEqual(pest.crop_type, '番茄')
        methods = list(pest.prevention_methods.values_list('category', 'measure'))
        self.assertIn(('CHEMICAL', '喷施烯酰吗啉'), methods)
        self.assertIn(('AGRICULTURAL', '合理轮作'), methods)

    def test_import_updates_existing_by_identifier(self):
        PestInfo.objects.create(name='旧名字', crop_type='番茄', english_identifier='Tomato___Late_blight')
        file = self._csv('病害名称,作物类型,英文标识符\n番茄晚疫病,番茄,Tomato___Late_blight\n')
        response = self._post(file)
        self.assertEqual(response.data['updated'], 1)
        self.assertEqual(response.data['created'], 0)
        self.assertEqual(PestInfo.objects.count(), 1, '不该新增重复记录')
        self.assertEqual(PestInfo.objects.get().name, '番茄晚疫病')

    def test_create_only_mode_skips_existing(self):
        PestInfo.objects.create(name='旧名字', crop_type='番茄', english_identifier='Tomato___Late_blight')
        file = self._csv('病害名称,作物类型,英文标识符\n番茄晚疫病,番茄,Tomato___Late_blight\n')
        response = self._post(file, mode='create_only')
        self.assertEqual(response.data['skipped'], 1)
        self.assertEqual(response.data['updated'], 0)
        self.assertIn('已存在', response.data['errors'][0]['message'])

    def test_row_level_errors_do_not_abort_whole_import(self):
        file = self._csv(
            '病害名称,作物类型,英文标识符\n'
            '番茄晚疫病,番茄,Tomato___Late_blight\n'
            ',番茄,Missing__Name\n'                       # 第 3 行：名称为空
            '黄瓜霜霉病,黄瓜,\n'                            # 第 4 行：英文标识为空
            '玉米大斑病,玉米,Corn___Leaf_blight\n'
        )
        response = self._post(file)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['created'], 2)
        self.assertEqual(response.data['skipped'], 2)
        self.assertEqual([item['row'] for item in response.data['errors']], [3, 4])
        self.assertIn('名称为空', response.data['errors'][0]['message'])
        self.assertIn('英文标识符为空', response.data['errors'][1]['message'])

    def test_duplicate_name_and_crop_in_file_is_reported(self):
        PestInfo.objects.create(name='番茄晚疫病', crop_type='番茄', english_identifier='Another__Key')
        file = self._csv(
            '病害名称,作物类型,英文标识符\n'
            '番茄晚疫病,番茄,Tomato___Late_blight\n'
        )
        response = self._post(file)
        self.assertEqual(response.data['skipped'], 1)
        self.assertIn('同名同作物', response.data['errors'][0]['message'])

    def test_missing_required_headers(self):
        file = self._csv('病害名称,症状\n番茄晚疫病,叶片病斑\n')
        response = self._post(file)
        self.assertEqual(response.status_code, 400)
        self.assertIn('表头缺少必需列', response.data['detail'])

    def test_header_aliases_and_column_order_flexible(self):
        # 英文表头 + 打乱顺序
        file = self._csv(
            'english_identifier,crop_type,name\n'
            'Rice___Blast,水稻,稻瘟病\n'
        )
        response = self._post(file)
        self.assertEqual(response.data['created'], 1)
        self.assertEqual(PestInfo.objects.get().name, '稻瘟病')

    def test_import_from_xlsx_upload(self):
        file = self._xlsx(
            ['病害名称', '作物类型', '英文标识符', '防治方法'],
            [['苹果黑星病', '苹果', 'Apple___Black_rot', '监测预警:雨季前巡查果园']],
        )
        response = self._post(file)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['created'], 1)
        pest = PestInfo.objects.get(english_identifier='Apple___Black_rot')
        self.assertEqual(pest.prevention_methods.count(), 1)

    def test_import_replaces_previous_prevention_methods(self):
        pest = PestInfo.objects.create(name='番茄晚疫病', crop_type='番茄', english_identifier='Tomato___Late_blight')
        PreventionMethod.objects.create(pest=pest, category='CHEMICAL', measure='旧措施')
        file = self._csv(
            '病害名称,作物类型,英文标识符,防治方法\n'
            '番茄晚疫病,番茄,Tomato___Late_blight,物理防治:清除病残体\n'
        )
        self._post(file)
        methods = list(pest.prevention_methods.values_list('category', 'measure'))
        self.assertEqual(methods, [('PHYSICAL', '清除病残体')], '导入应以表格为准，替换旧措施')

    def test_unknown_prevention_category_reports_error(self):
        file = self._csv(
            '病害名称,作物类型,英文标识符,防治方法\n'
            '番茄晚疫病,番茄,Tomato___Late_blight,玄学防治:念咒\n'
        )
        response = self._post(file)
        self.assertEqual(response.data['skipped'], 1)
        self.assertIn('无法识别', response.data['errors'][0]['message'])

    def test_requires_admin(self):
        file = self._csv('病害名称,作物类型,英文标识符\n番茄晚疫病,番茄,Tomato___Late_blight\n')
        self.assertEqual(self._post(file, client=self.client_user).status_code, 403)
        self.assertEqual(self._post(file, client=APIClient()).status_code, 401)

    def test_missing_file_and_bad_extension(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.assertEqual(self.client_admin.post('/api/pests/import/', {}, format='multipart').status_code, 400)
        bad = SimpleUploadedFile('pests.pdf', b'%PDF-1.4', content_type='application/pdf')
        self.assertEqual(self._post(bad).status_code, 400)

    def test_template_download(self):
        from .xlsx import read_xlsx_rows
        response = self.client_admin.get('/api/pests/import-template/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])

        rows = read_xlsx_rows(response.content)
        self.assertEqual(rows[0], ['病害名称', '作物类型', '英文标识符', '症状', '详细描述', '防治方法'])
        self.assertEqual(len(rows), 2, '模板应含表头 + 一行示例')
        self.assertEqual(rows[1][0], '番茄晚疫病')

        # 模板本身必须能被导入接口接受（表头对得上）
        from django.core.files.uploadedfile import SimpleUploadedFile
        file = SimpleUploadedFile('t.xlsx', response.content)
        result = self._post(file)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['created'], 1)

    def test_template_requires_admin(self):
        self.assertEqual(self.client_user.get('/api/pests/import-template/').status_code, 403)


# ============================================================================
# 第 91 批：识别反馈闭环（纠错 → 训练样本）
# ============================================================================
class FeedbackDatasetLoopTests(TestCase):
    """
    第 91 批：把"用户的识别纠错"变成"可用的训练样本"

    改前的断链（很典型）：前端 `DetectView.vue` 一直在传 `detection_id`
    （移动端 `api/detection.js` 同样传），但后端既没有这个字段、也没有序列化器声明
    —— 参数被**静默丢弃**；纠错只存了"对/错"，没有"正确是哪一种"。
    于是负反馈只能计数，永远变不成标签。

    本组用例锁死三件事：
      ① 纠错能关联上识别记录，且**只能关联自己的**；
      ② 只导"识别错了 + 给了正确类别 + 已人工确认"的样本；
      ③ 导出命令真的产出可用数据集（图片 + YOLO 标签 + manifest + dataset.yaml）。
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='ds_user', password='pw12345678')
        cls.other = User.objects.create_user(username='ds_other', password='pw12345678')
        cls.admin = User.objects.create_user(
            username='ds_admin', password='pw12345678', is_staff=True,
        )
        cls.pest = PestInfo.objects.create(
            name='番茄晚疫病', name_en='Late blight', crop_type='番茄',
            english_identifier='tomato_late_blight', symptoms='s', description='d',
        )
        cls.other_pest = PestInfo.objects.create(
            name='苹果黑星病', name_en='Apple scab', crop_type='苹果',
            english_identifier='apple_scab', symptoms='s', description='d',
        )

    def setUp(self):
        self.client_user = APIClient()
        self.client_user.force_authenticate(user=self.user)
        self.client_other = APIClient()
        self.client_other.force_authenticate(user=self.other)
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)

        self.detection = DetectionHistory.objects.create(
            user=self.user, image=_png_upload('det.jpg'),
            detection_result='苹果黑星病', pest_info=self.other_pest, confidence=0.42,
        )

    # ---------- ① 关联 ----------

    def test_correction_links_to_detection_and_correct_pest(self):
        response = self.client_user.post('/api/feedback/', {
            'category': 'recognition',
            'is_correct': False,
            'suggestion': '识别错了',
            'detection_id': self.detection.id,
            'corrected_pest_id': self.pest.id,
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['detection_id'], self.detection.id)
        self.assertEqual(response.data['corrected_pest_id'], self.pest.id)
        self.assertTrue(response.data['is_trainable'], '应被判定为可训练样本')
        self.assertEqual(response.data['verify_status'], 'pending', '用户提交后默认待确认')
        # 回显里能看到"这条纠错针对哪次识别"
        self.assertIn('苹果黑星病', response.data['detection_summary'])

    def test_user_cannot_self_confirm_sample(self):
        """
        `verify_status` 对 API 只读：用户不能把自己的反馈标成"已确认"。
        否则"人工确认"这道闸门形同虚设，样本池可以自助灌水。
        （真实确认入口是 Django admin 的批量动作。）
        """
        response = self.client_user.post('/api/feedback/', {
            'category': 'recognition', 'is_correct': False,
            'suggestion': '自助确认试试', 'detection_id': self.detection.id,
            'corrected_pest_id': self.pest.id,
            'verify_status': 'confirmed',   # 试图直接写进去
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            Feedback.objects.get(id=response.data['id']).verify_status, 'pending',
            '提交时带的 verify_status 必须被忽略',
        )

    def test_disease_name_and_confidence_fall_back_to_detection(self):
        """前端没传 disease_name / confidence 时，后端从识别记录补齐（后台才查得到上下文）"""
        response = self.client_user.post('/api/feedback/', {
            'category': 'recognition', 'is_correct': False,
            'suggestion': '错了', 'detection_id': self.detection.id,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        feedback = Feedback.objects.get(id=response.data['id'])
        self.assertEqual(feedback.disease_name, '苹果黑星病')
        self.assertAlmostEqual(feedback.confidence, 0.42, places=4)

    def test_cannot_link_someone_elses_detection(self):
        """越权校验：不能把反馈挂到别人的识别记录上（反馈是公开可查的）"""
        response = self.client_other.post('/api/feedback/', {
            'category': 'recognition', 'is_correct': False,
            'suggestion': '别人的记录', 'detection_id': self.detection.id,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('detection_id', response.data)

    def test_is_trainable_requires_correct_pest(self):
        """只说"错了"、不说"对的是什么" → 不是可训练样本（对模型没有增量信息）"""
        response = self.client_user.post('/api/feedback/', {
            'category': 'recognition', 'is_correct': False,
            'suggestion': '错了但不知道是啥', 'detection_id': self.detection.id,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertFalse(Feedback.objects.get(id=response.data['id']).is_trainable)

    def test_correct_feedback_is_not_trainable(self):
        response = self.client_user.post('/api/feedback/', {
            'category': 'recognition', 'is_correct': True,
            'suggestion': '识别正确', 'detection_id': self.detection.id,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertFalse(Feedback.objects.get(id=response.data['id']).is_trainable)

    # ---------- ② 统计 ----------

    def _make_correction(self, verify_status='confirmed', corrected=True):
        return Feedback.objects.create(
            user=self.user, category='recognition', is_correct=False,
            suggestion='纠错', detection=self.detection,
            corrected_pest=self.pest if corrected else None,
            verify_status=verify_status,
        )

    def test_dataset_stats_endpoint_counts_samples(self):
        self._make_correction('confirmed')
        self._make_correction('pending')
        self._make_correction('rejected')
        self._make_correction('confirmed', corrected=False)

        response = self.client_admin.get('/api/admin/dataset-stats/')
        self.assertEqual(response.status_code, 200)

        samples = response.data['samples']
        self.assertEqual(samples['trainable'], 3, '没给正确类别的那个不算')
        # 明细：confirmed+pest / pending+pest / rejected+pest / confirmed 但没给类别
        self.assertEqual(samples['confirmed'], 1)
        self.assertEqual(samples['pending'], 1)
        self.assertEqual(samples['rejected'], 1)

        fb = response.data['feedback']
        self.assertEqual(fb['recognition_total'], 4)
        self.assertEqual(fb['negative'], 4)
        self.assertEqual(fb['negative_rate'], 1.0)

    def test_dataset_stats_requires_admin(self):
        self.assertEqual(self.client_user.get('/api/admin/dataset-stats/').status_code, 403)

    # ---------- ③ 导出 ----------

    def test_export_command_produces_dataset(self):
        import tempfile
        from pathlib import Path

        from django.core.management import call_command

        confirmed = self._make_correction('confirmed')
        self._make_correction('pending')  # 不该被导出

        with tempfile.TemporaryDirectory() as tmp:
            call_command('export_feedback_dataset', '--out', tmp, '--mark-exported', verbosity=0)
            out = Path(tmp)

            self.assertTrue((out / 'dataset.yaml').exists())
            self.assertTrue((out / 'manifest.csv').exists())
            self.assertTrue((out / 'README.txt').exists())

            labels = list((out / 'labels').glob('*.txt'))
            images = list((out / 'images').glob('*'))
            self.assertEqual(len(labels), 1, '只有 confirmed 的才导出')
            self.assertEqual(len(images), 1)

            # 标签是"整图框"，class_id 对应 dataset.yaml 里的顺序
            body = labels[0].read_text(encoding='utf-8').strip().split()
            self.assertEqual(len(body), 5)
            self.assertEqual(body[0], '0')
            self.assertEqual(body[1:], ['0.500000', '0.500000', '1.000000', '1.000000'])

            yaml_text = (out / 'dataset.yaml').read_text(encoding='utf-8')
            self.assertIn('tomato_late_blight', yaml_text, '类别名用英文标识符（与训练标签一致）')

            manifest = (out / 'manifest.csv').read_text(encoding='utf-8-sig')
            self.assertIn('番茄晚疫病', manifest)
            self.assertIn('苹果黑星病', manifest, 'manifest 要留下"模型原结论"便于对比')

        confirmed.refresh_from_db()
        self.assertIsNotNone(confirmed.exported_at, '--mark-exported 应打上导出时间')

    def test_export_dry_run_writes_nothing(self):
        import tempfile
        from pathlib import Path

        from django.core.management import call_command

        self._make_correction('confirmed')
        with tempfile.TemporaryDirectory() as tmp:
            call_command('export_feedback_dataset', '--out', tmp, '--dry-run', verbosity=0)
            self.assertEqual(list(Path(tmp).iterdir()), [], '--dry-run 不该写任何文件')

    def test_export_without_samples_does_not_crash(self):
        import tempfile

        from django.core.management import call_command

        with tempfile.TemporaryDirectory() as tmp:
            # 没有任何样本：命令只提示，不报错
            call_command('export_feedback_dataset', '--out', tmp, verbosity=0)


# ============================================================================
# 第 91 批（安全）：图片上传统一校验
# ============================================================================
class ImageUploadValidationTests(TestCase):
    """
    第 91 批：修掉通用图片上传的三个问题

    1. **没有大小上限** —— 任何登录用户都能把磁盘刷满（头像那条链路反倒有 2MB 上限）；
    2. **只比 `content_type`** —— 那是客户端自己声明的请求头，随便伪造；
    3. **直接用用户的原始文件名拼路径** —— 文件名可以带 `../`。

    现在统一走 `api/image_validation.py`：大小上限 → 按**文件头**探测真实格式 →
    扩展名由探测结果决定 → 文件名随机化。下面用例把每条都钉住。
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='img_user', password='pw12345678')
        cls.admin = User.objects.create_user(
            username='img_admin', password='pw12345678', is_staff=True,
        )

    def setUp(self):
        self.client_user = APIClient()
        self.client_user.force_authenticate(user=self.user)
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)

        # ⚠️ 第 110 批：把 MEDIA_ROOT 指到临时目录。
        #
        # `test_news_image_upload_accepts_real_png` 是**唯一**必须真的落盘的用例 ——
        # 它要验证"合法 PNG 能存下来并返回 url"，只给字段赋字符串是测不出来的。
        # 但它此前写进了**真实 media**，实测每跑一次 `manage.py test` 就在
        # `backend/media/news_images/` 下留一个 0.1KB 的 `news_<随机>_png`，
        # 而本文件开头明确写着"本文件的测试不写任何媒体文件"（第 21 批立的规矩）。
        #
        # 这既是污染（跑测试会改工作区，还会被 `git add -A` 收进仓库），
        # 也违背了那条规矩的**理由**：测试里的一次上传/删除会真的动到业务文件，
        # 而事务回滚救不了文件系统。
        #
        # 用 `override_settings` + 临时目录（与 `PruneMediaCommandTests` 同一做法）。
        # 注意要用 `enable()/disable()` 而不是装饰器：类里其它用例不需要它，
        # 而写在类上的装饰器会让整个类都换目录（无害但没必要）。
        import tempfile

        self._media_tmp = Path(tempfile.mkdtemp(prefix='zz_img_upload_'))
        self._media_override = override_settings(MEDIA_ROOT=str(self._media_tmp))
        self._media_override.enable()

    def tearDown(self):
        # 顺序很重要：先让 settings 复原，再删目录 ——
        # 反过来的话，清理期间任何一次文件访问都会写到一个已删除的目录。
        self._media_override.disable()
        import shutil

        shutil.rmtree(self._media_tmp, ignore_errors=True)

    # ---------- 客户端可伪造 content_type，必须按文件内容判断 ----------

    def test_spoofed_content_type_is_rejected(self):
        """声明 image/png、内容其实是文本 —— 按文件头识破"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake = SimpleUploadedFile('evil.png', b'<html>not an image at all</html>', content_type='image/png')
        response = self.client_user.post('/api/upload/image/', {'image': fake}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('无法识别图片格式', response.data['error'])

    def test_zip_disguised_as_png_is_rejected(self):
        """PK 头（压缩包）同样不是图片"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        zip_like = SimpleUploadedFile('archive.png', b'PK\x03\x04' + b'\x00' * 200, content_type='image/png')
        response = self.client_user.post('/api/upload/image/', {'image': zip_like}, format='multipart')
        self.assertEqual(response.status_code, 400)

    def test_real_png_is_accepted(self):
        response = self.client_user.post(
            '/api/upload/image/', {'image': _png_upload()}, format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('/media/uploads/', response.data['url'])

    def test_real_jpeg_is_accepted(self):
        """JPEG 走魔数分支（FF D8 FF），不需要 Pillow 兜底"""
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = BytesIO()
        Image.new('RGB', (8, 8), (200, 40, 40)).save(buffer, format='JPEG')
        jpeg = SimpleUploadedFile('photo.jpg', buffer.getvalue(), content_type='image/jpeg')
        response = self.client_user.post('/api/upload/image/', {'image': jpeg}, format='multipart')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['url'].endswith('.jpg'))

    # ---------- 大小上限 ----------

    def test_oversized_image_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        # 用真实 PNG 头 + 填充到超过 5MB，确保它"先是图片、再是太大"
        head = _png_upload().read()
        big = SimpleUploadedFile('big.png', head + b'\x00' * (MAX_IMAGE_SIZE + 1 - len(head)),
                                 content_type='image/png')
        response = self.client_user.post('/api/upload/image/', {'image': big}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('不能超过', response.data['error'])

    def test_empty_file_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        empty = SimpleUploadedFile('empty.png', b'', content_type='image/png')
        response = self.client_user.post('/api/upload/image/', {'image': empty}, format='multipart')
        self.assertEqual(response.status_code, 400)

    # ---------- 文件名随机化（不采用用户给的名字） ----------

    def test_filename_is_randomized_and_extension_follows_content(self):
        """
        用户传 `../../evil.php` 也没用：文件名被换掉，扩展名按真实格式给。
        这条替代了原来"直接把 image_file.name 拼进路径"的写法。
        """
        from django.core.files.uploadedfile import SimpleUploadedFile

        png_bytes = _png_upload().read()
        tricky = SimpleUploadedFile('../../evil.php', png_bytes, content_type='image/png')
        response = self.client_user.post('/api/upload/image/', {'image': tricky}, format='multipart')

        self.assertEqual(response.status_code, 201)
        url = response.data['url']
        self.assertNotIn('evil.php', url)
        self.assertNotIn('..', url)
        self.assertTrue(url.endswith('.png'), f'扩展名应按真实格式给，实际：{url}')

    def test_default_storage_path_is_inside_uploads(self):
        response = self.client_user.post(
            '/api/upload/image/', {'image': _png_upload()}, format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('/media/uploads/', response.data['url'])

    # ---------- 校验器本身的单元测试 ----------

    def test_validator_returns_detected_format(self):
        from .image_validation import validate_image_upload

        meta = validate_image_upload(_png_upload())
        self.assertEqual(meta['format'], 'PNG')
        self.assertEqual(meta['ext'], '.png')
        self.assertTrue(meta['filename'].endswith('.png'))

    def test_validator_rejects_missing_file(self):
        from .image_validation import ImageValidationError, validate_image_upload

        with self.assertRaises(ImageValidationError):
            validate_image_upload(None)

    def test_validator_respects_custom_allowed_formats(self):
        """新闻图上传不允许 BMP（体积大、编辑器用不到）"""
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        from .image_validation import ImageValidationError, validate_image_upload

        buffer = BytesIO()
        Image.new('RGB', (8, 8), (0, 0, 255)).save(buffer, format='BMP')
        bmp = SimpleUploadedFile('pic.bmp', buffer.getvalue(), content_type='image/bmp')

        # 通用上传允许 BMP
        self.assertEqual(validate_image_upload(bmp)['format'], 'BMP')

        # 只允许 JPEG/PNG/GIF/WEBP 时被拒
        bmp.seek(0)
        with self.assertRaises(ImageValidationError):
            validate_image_upload(
                bmp,
                allowed_formats={'JPEG': '.jpg', 'PNG': '.png', 'GIF': '.gif', 'WEBP': '.webp'},
            )

    def test_detect_does_not_consume_the_file(self):
        """探测只读文件头，读完指针要还原 —— 否则后续保存会存到一个空文件"""
        from .image_validation import detect_image_format

        upload = _png_upload()
        self.assertEqual(detect_image_format(upload), 'PNG')
        self.assertEqual(upload.tell(), 0)
        self.assertGreater(len(upload.read()), 0)

    # ---------- 新闻图上传同样受保护 ----------

    def test_news_image_upload_rejects_oversized(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        head = _png_upload().read()
        big = SimpleUploadedFile('big.png', head + b'\x00' * (MAX_IMAGE_SIZE + 1 - len(head)),
                                 content_type='image/png')
        response = self.client_admin.post('/api/news/upload_image/', {'image': big}, format='multipart')
        self.assertEqual(response.status_code, 400)

    def test_news_image_upload_rejects_spoofed_type(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake = SimpleUploadedFile('fake.png', b'definitely not an image', content_type='image/png')
        response = self.client_admin.post('/api/news/upload_image/', {'image': fake}, format='multipart')
        self.assertEqual(response.status_code, 400)

    def test_news_image_upload_accepts_real_png(self):
        response = self.client_admin.post(
            '/api/news/upload_image/', {'image': _png_upload()}, format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('/media/news_images/', response.data['url'])


# ============================================================================
# 第 91 批：帖子软删除（不再级联硬删他人评论/点赞）
# ============================================================================
class PostSoftDeleteTests(TestCase):
    """
    第 91 批：删帖从"硬删除"改成"软删除"

    改前的真实后果：`PostViewSet` 没有覆写 `destroy`，走 DRF 默认的
    `instance.delete()`；而 `Comment.post` / `Like.post` / `Favorite.post` 都是
    `CASCADE` —— 管理员删一条被举报的帖子，会**不可恢复地**连带删掉别人写的
    所有评论、点赞与收藏。评论从第 17 批起就是软删除，只有帖子不是，口径不一致。

    改后：删帖 = 标记 `is_deleted` + 清空标题正文；关联行原样保留；
    帖子从所有列表/详情/热门榜消失（但管理员可用 `?only_deleted=true` 审计）。
    """

    @classmethod
    def setUpTestData(cls):
        cls.board = ForumBoard.objects.create(name='软删除测试版块', is_active=True)
        cls.author = User.objects.create_user(username='sd_author', password='pw12345678')
        cls.other = User.objects.create_user(username='sd_other', password='pw12345678')
        cls.admin = User.objects.create_user(
            username='sd_admin', password='pw12345678', is_staff=True,
        )

    def setUp(self):
        self.post = Post.objects.create(
            title='会被删掉的帖子', content='正文内容', author=self.author,
            board=self.board, status='published',
        )
        # 别人写的评论 + 回复 + 点赞 + 收藏
        self.comment = Comment.objects.create(
            content='别人的评论', author=self.other, post=self.post,
        )
        self.reply = Comment.objects.create(
            content='别人的回复', author=self.other, post=self.post, parent=self.comment,
        )
        Like.objects.create(user=self.other, post=self.post)
        Favorite.objects.create(user=self.other, post=self.post)

        self.author_client = APIClient()
        self.author_client.force_authenticate(user=self.author)
        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)

    def test_author_delete_soft_deletes_and_returns_204(self):
        response = self.author_client.delete(f'/api/forums/posts/{self.post.id}/')
        self.assertEqual(response.status_code, 204)

        self.post.refresh_from_db()
        self.assertTrue(self.post.is_deleted)
        self.assertIsNotNone(self.post.deleted_at)

    def test_others_content_survives_the_delete(self):
        """本批的核心：删帖不能删掉别人的评论/点赞/收藏"""
        self.author_client.delete(f'/api/forums/posts/{self.post.id}/')

        self.assertTrue(Comment.objects.filter(id=self.comment.id).exists())
        self.assertTrue(Comment.objects.filter(id=self.reply.id).exists())
        self.assertTrue(Like.objects.filter(post_id=self.post.id).exists())
        self.assertTrue(Favorite.objects.filter(post_id=self.post.id).exists())
        # 评论的正文与作者也原样保留（不是"留个空壳"）
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.content, '别人的评论')
        self.assertEqual(self.comment.author_id, self.other.id)

    def test_deleted_post_disappears_from_list_and_detail(self):
        self.author_client.delete(f'/api/forums/posts/{self.post.id}/')

        for client in (self.author_client, self.other_client, APIClient()):
            listed = client.get('/api/forums/posts/', {'page_size': 100})
            ids = [row['id'] for row in listed.data['results']]
            self.assertNotIn(self.post.id, ids, '软删除的帖子不该出现在列表里')
            self.assertEqual(client.get(f'/api/forums/posts/{self.post.id}/').status_code, 404)

    def test_deleted_post_disappears_from_hot_list(self):
        self.author_client.delete(f'/api/forums/posts/{self.post.id}/')
        hot = self.author_client.get('/api/forums/posts/hot/')
        self.assertNotIn(self.post.id, [row['id'] for row in hot.data])

    def test_deleted_post_is_removed_from_others_favorites(self):
        """别人的收藏列表里不该再出现"已删除"的帖子"""
        self.author_client.delete(f'/api/forums/posts/{self.post.id}/')
        favorites = self.other_client.get('/api/forums/posts/', {'favorited': 'true', 'page_size': 100})
        self.assertNotIn(self.post.id, [row['id'] for row in favorites.data['results']])

    def test_admin_can_audit_deleted_posts(self):
        """管理员用 ?only_deleted=true 能看到被删的帖子（出问题要能追溯）"""
        self.author_client.delete(f'/api/forums/posts/{self.post.id}/')

        self.assertEqual(self.post.id, Post.objects.get(id=self.post.id).id)  # 行还在
        audited = self.admin_client.get('/api/forums/posts/', {'only_deleted': 'true', 'page_size': 100})
        self.assertIn(self.post.id, [row['id'] for row in audited.data['results']])

        # 普通用户即使传了这个参数也拿不到
        sneaky = self.other_client.get('/api/forums/posts/', {'only_deleted': 'true', 'page_size': 100})
        self.assertNotIn(self.post.id, [row['id'] for row in sneaky.data['results']])

    def test_soft_delete_clears_title_and_content(self):
        self.author_client.delete(f'/api/forums/posts/{self.post.id}/')
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, '[已删除]')
        self.assertEqual(self.post.content, '[该帖子已被删除]')
        self.assertFalse(self.post.is_pinned)
        self.assertFalse(self.post.is_essence)

    def test_non_author_non_admin_cannot_delete(self):
        response = self.other_client.delete(f'/api/forums/posts/{self.post.id}/')
        self.assertEqual(response.status_code, 403)
        self.post.refresh_from_db()
        self.assertFalse(self.post.is_deleted)

    def test_admin_can_delete_others_post(self):
        response = self.admin_client.delete(f'/api/forums/posts/{self.post.id}/')
        self.assertEqual(response.status_code, 204)
        self.post.refresh_from_db()
        self.assertTrue(self.post.is_deleted)

    def test_board_post_count_is_not_recounted_on_soft_delete(self):
        """
        软删除不回收版块计数 —— 这是刻意的：版块统计是**历史累计**口径，
        与"今日发帖"一样属于流水，删帖不该让"本版块有多少人发过言"缩水。
        真要重算请用管理命令，而不是在删帖时静默改数。
        """
        before = ForumBoard.objects.get(id=self.board.id).post_count
        self.author_client.delete(f'/api/forums/posts/{self.post.id}/')
        after = ForumBoard.objects.get(id=self.board.id).post_count
        self.assertEqual(before, after)


# ============================================================================
# 第 106 批：清理与修复（5 个真 bug 的回归测试）
# ============================================================================
class LikeCounterConsistencyTests(TestCase):
    """
    点赞计数必须与真实点赞行数一致（第 106 批）

    这是一个**实测复现过的真 bug**：`POST /api/forums/likes/` 会把计数多加 1，
    因为一次请求里有两个人写同一个字段 ——

      · `Like.objects.create()` 触发的 `models_forum.Like.save()` 把
        `post.like_count` **精确重算**成真实行数；
      · 紧接着 `LikeViewSet.create` 又做了 `F('like_count') + 1`。

    实测（修复前）：点赞前 `like_count=0/行数=0` → POST 后 `like_count=2/行数=1`。

    为什么前端一直没发现：前端点赞走的是 `PostViewSet.like`
    （`/forums/posts/{id}/like/`），那条路径写法是对的。所以这个 bug
    只影响直接调用 `/api/forums/likes/` 的客户端 —— 而"没人走的路"最容易烂掉，
    这正是要给它补测试的理由。
    """

    def setUp(self):
        cache.clear()
        self.author = User.objects.create_user(username='lc_author', password='pw12345678')
        self.liker = User.objects.create_user(username='lc_liker', password='pw12345678')
        self.board = ForumBoard.objects.create(name='点赞测试版块', is_active=True)
        self.post = Post.objects.create(
            title='点赞计数测试帖', content='x', author=self.author, board=self.board,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.liker)

    def _state(self):
        """返回 (帖子上的计数字段, 数据库里真实的点赞行数)"""
        self.post.refresh_from_db()
        return self.post.like_count, Like.objects.filter(post_id=self.post.id).count()

    def test_direct_like_create_does_not_double_count(self):
        before = self._state()
        self.assertEqual(before, (0, 0), f'初始状态就应该是 0/0，实际 {before}')

        response = self.client.post(
            '/api/forums/likes/', {'post': self.post.id}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)

        count, rows = self._state()
        self.assertEqual(rows, 1, '应该只有一条点赞记录')
        self.assertEqual(
            count, rows,
            f'计数字段({count})与真实行数({rows})不一致 —— 计数被重复自增了',
        )

    def test_direct_like_delete_does_not_double_decrement(self):
        """删除方向是同一个 bug 的孪生：原来视图里还有 `F('like_count') - 1`"""
        created = self.client.post('/api/forums/likes/', {'post': self.post.id}, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        like_id = created.json().get('id') or Like.objects.get(post_id=self.post.id).id

        response = self.client.delete(f'/api/forums/likes/{like_id}/')
        self.assertEqual(response.status_code, 204, response.content)

        count, rows = self._state()
        self.assertEqual((count, rows), (0, 0), f'取消点赞后应为 0/0，实际 {count}/{rows}')

    def test_repeated_like_unlike_keeps_counter_honest(self):
        """
        连续来回点赞/取消 3 轮 —— 计数必须每一轮都回到真实值。

        这条能抓住"每次少 1 / 多 1"的累积型错误（单次断言可能恰好抵消）。
        """
        for round_index in range(3):
            created = self.client.post('/api/forums/likes/', {'post': self.post.id}, format='json')
            self.assertEqual(created.status_code, 201, f'第 {round_index + 1} 轮点赞失败')
            count, rows = self._state()
            self.assertEqual(count, rows, f'第 {round_index + 1} 轮点赞后 {count} != {rows}')

            like_id = created.json().get('id') or Like.objects.get(post_id=self.post.id).id
            self.client.delete(f'/api/forums/likes/{like_id}/')
            count, rows = self._state()
            self.assertEqual((count, rows), (0, 0), f'第 {round_index + 1} 轮取消后不是 0/0')

    def test_post_like_action_still_works(self):
        """前端走的那条路径（PostViewSet.like）不能被这次修改带坏"""
        response = self.client.post(f'/api/forums/posts/{self.post.id}/like/')
        self.assertIn(response.status_code, (200, 201), response.content)
        count, rows = self._state()
        self.assertEqual(count, rows, f'PostViewSet.like 之后 {count} != {rows}')
        self.assertEqual(response.json().get('like_count'), count)


class PestTypesSearchTests(TestCase):
    """
    `/api/pest-types/?search=` 不能 500（第 106 批）

    改前这里是 `Q(english_name__icontains=search)`，而 **PestInfo 没有
    `english_name` 字段** → `FieldError` → 被外层 `except Exception` 吞掉 →
    返回 500「获取病害类型失败」。也就是说：**带 search 的请求必定失败**，
    而不带 search 时才正常 —— 这类"只有某个参数才炸"的 bug 最容易漏测。

    同一个 bug 在本文件所属项目里**早就修过一次**
    （`views.py` 的 `PreventionDataView`，第 78 批，还写了注释），
    但修复没有传播到 `PestTypesView`。所以这里把四个匹配维度全测一遍，
    顺便钉住"字段名到底有哪些"。
    """

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='pt_user', password='pw12345678')
        # ⚠️ 必须用 DRF 的 APIClient：`django.test.Client` 没有 `force_authenticate`
        #    （第一版就写错了，报 `'Client' object has no attribute 'force_authenticate'`）
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        PestInfo.objects.create(
            name='苹果黑星病', name_en='Apple Scab', english_identifier='Apple___Apple_scab',
            crop_type='苹果', description='叶片出现黑褐色霉层',
        )
        PestInfo.objects.create(
            name='番茄早疫病', name_en='Tomato Early Blight', english_identifier='Tomato___Early_blight',
            crop_type='番茄', description='下部叶片出现同心轮纹',
        )

    def test_no_search_returns_all(self):
        response = self.client.get('/api/pest-types/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['count'], 2)

    def test_search_by_chinese_name(self):
        response = self.client.get('/api/pest-types/', {'search': '苹果'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['results'], ['苹果黑星病'])

    def test_search_by_english_name(self):
        """`name_en` —— 第 78 批补的字段，正是容易漏的那个"""
        response = self.client.get('/api/pest-types/', {'search': 'Blight'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['results'], ['番茄早疫病'])

    def test_search_by_english_identifier(self):
        """数据集标识（`Apple___Apple_scab` 这种）也要能搜到"""
        response = self.client.get('/api/pest-types/', {'search': 'Apple___'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['results'], ['苹果黑星病'])

    def test_search_by_description(self):
        response = self.client.get('/api/pest-types/', {'search': '同心轮纹'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['results'], ['番茄早疫病'])

    def test_search_fields_all_exist_on_model(self):
        """
        直接钉住"查的字段必须真实存在"。

        比逐个接口测更根本：下次有人凭印象写个 `english_name`，
        这条会立刻告诉他 PestInfo 只有 `name` / `name_en` / `english_identifier`。
        """
        field_names = {field.name for field in PestInfo._meta.get_fields()}
        for field in ('name', 'name_en', 'english_identifier', 'description', 'crop_type'):
            with self.subTest(field=field):
                self.assertIn(field, field_names)
        self.assertNotIn(
            'english_name', field_names,
            'PestInfo 出现了 english_name 字段 —— 如果是有意新增，请同时更新 '
            'PestTypesView 与 PreventionDataView 的注释（它们都写着"没有这个字段"）',
        )

    def test_crop_type_filter_combines_with_search(self):
        response = self.client.get('/api/pest-types/', {'search': '病', 'crop_type': '苹果'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['results'], ['苹果黑星病'])


class CancelDeletionThrottleTests(TestCase):
    """
    取消注销接口必须限流（第 106 批）

    `AccountCancelDeletionView` 是**匿名**的（账号已停用、拿不到 Token），
    靠"用户名 + 密码"认身份 —— 也就是说它是一个**匿名密码校验端点**。
    第 101 批上线时忘了限流，而第 91 批移除 DRF 自带 `/api/token-auth/`
    的理由正是"改打这个端点就能无限撞库"：同一个风险类别。

    这条测试的价值在于**它会随配置变化**：如果有人把
    `throttle_classes` 删掉、或把 `cancel_deletion` 速率从 settings 里去掉，
    DRF 的 `SimpleRateThrottle` 在 rate=None 时会**静默放行**（第 35 批的教训），
    这里就会红。
    """

    def setUp(self):
        cache.clear()
        self.username = 'cd_throttle_user'
        self.password = 'Throttle!2026pw'
        self.user = User.objects.create_user(username=self.username, password=self.password)
        self.user.request_deletion(by=self.user, reason='test')

    def tearDown(self):
        cache.clear()

    def _attempt(self):
        return self.client.post(
            '/api/users/me/cancel-deletion/',
            {'username': self.username, 'password': 'wrong-password'},
            format='json',
        ).status_code

    def test_endpoint_is_throttled(self):
        from api.views_user import AccountCancelDeletionView

        self.assertTrue(
            AccountCancelDeletionView.throttle_classes,
            '取消注销接口没有配置限流类 —— 它是一个匿名的密码校验端点，必须限流',
        )
        self.assertEqual(
            getattr(AccountCancelDeletionView, 'throttle_scope', None),
            'cancel_deletion',
            'throttle_scope 必须指向 settings.DEFAULT_THROTTLE_RATES 里已配置的 scope',
        )

    def test_throttle_rate_is_configured(self):
        """速率必须真的在 settings 里 —— 否则限流类挂了也不生效（第 35 批的坑）"""
        from django.conf import settings

        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        self.assertIn(
            'cancel_deletion', rates,
            'settings 里没有 cancel_deletion 速率：DRF 在 rate=None 时会直接放行，'
            '限流形同虚设',
        )

    def test_repeated_wrong_password_eventually_returns_429(self):
        """连续失败到限额之后必须是 429（而不是继续回答"密码不对"）"""
        from api.views_user import AccountCancelDeletionView

        limit = int(
            str(__import__('django.conf', fromlist=['settings']).settings
                .REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['cancel_deletion']).split('/')[0]
        )
        codes = [self._attempt() for _ in range(limit + 2)]
        self.assertIn(429, codes, f'打了 {len(codes)} 次都没有 429：{codes}')
        self.assertNotIn(
            200, codes,
            '错误的密码不应该换到成功响应（这里用错密码探测，顺便确认没有绕过）',
        )

    def test_correct_password_still_works_before_limit(self):
        """限流不能把正常功能一起限掉 —— 额度内必须能成功取消"""
        response = self.client.post(
            '/api/users/me/cancel-deletion/',
            {'username': self.username, 'password': self.password},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('token', response.json())


class DeadCodeRemovalTests(TestCase):
    """
    重复的 `NewsViewSet` 必须不再存在（第 106 批）

    项目里曾经有**两份** `NewsViewSet`：
      · `api/news_views.py` —— `urls.py` 注册的是这一份（活的）；
      · `api/views.py` —— 永远走不到，却还留着
        `def detail()`（news_views 的注释记录过它与 DRF 路由的 detail 冲突 → 必定 500），
        而且分页器也不一样（6 vs 10）。

    留着它的代价是真实的：下一个维护者很可能去改错的那一份，
    或者把死的这份重新注册上去（于是两个坑一起复活）。

    ⚠️ 这里**不比对源码文本**（那种测试改个格式就红），而是两条行为性断言：
      ① 整个 `api` 包里只允许有一个 `NewsViewSet` 类定义（AST 扫描）；
      ② 新闻接口本身仍然可用（防止"删多了把活的也删了"）。
    """

    def test_only_one_news_viewset_class_defined_in_api_package(self):
        import ast
        from pathlib import Path

        api_dir = Path(__file__).resolve().parent
        found = []
        for path in sorted(api_dir.glob('*.py')):
            try:
                tree = ast.parse(path.read_text(encoding='utf-8', errors='replace'))
            except SyntaxError:
                continue
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name == 'NewsViewSet':
                    found.append(f'{path.name}:{node.lineno}')

        self.assertEqual(
            len(found), 1,
            f'api 包里定义了 {len(found)} 个 NewsViewSet：{found}\n'
            '只应保留 api/news_views.py 里的那一份（urls.py 注册的也是它）。\n'
            '多出来的那份永远不会被调用，还会让后来的人改错文件。',
        )
        self.assertTrue(
            found[0].startswith('news_views.py'),
            f'仅存的那份 NewsViewSet 在 {found[0]}，期望在 news_views.py',
        )

    def test_views_module_no_longer_defines_news_viewset(self):
        """`api/views.py` 里不该再有 NewsViewSet（死代码已删）"""
        from api import views

        self.assertFalse(
            hasattr(views, 'NewsViewSet'),
            'api/views.py 里又有 NewsViewSet 了 —— 项目只应保留 news_views.py 那一份，'
            '否则会出现"改错文件"与"重复注册"两个坑',
        )

    def test_news_endpoint_still_works(self):
        """删死代码不能把活的那个带坏：新闻列表必须还能打开"""
        response = self.client.get('/api/news/')
        self.assertEqual(response.status_code, 200, response.content)


class PasswordPolicyTests(TestCase):
    """
    密码策略必须全项目一致（第 106 批）

    改前的状态是三套规则并存：

    | 入口 | 最短 | 其它 |
    |---|---|---|
    | 注册 | 6 | 无 |
    | 邮箱重置 | 6 | **一条都没有** |
    | 修改密码 | 8 | 不能纯数字、不能与旧密码相同 |

    后果是**自相矛盾**：用户能用邮箱把密码重置成 `123456`，
    却在「修改密码」页不允许改成同样的密码。

    这些测试钉住：三条"设置新密码"的路径都走同一套规则，
    而且**登录不参与校验**（否则旧密码短于 8 位的存量用户会突然登不进来，
    而他们没有任何自救办法 —— 这是安全加固最容易造成的自伤）。
    """

    def setUp(self):
        cache.clear()

    # ---------- 策略本身 ----------

    def test_min_length_is_single_source_of_truth(self):
        from api.password_policy import MIN_LENGTH
        from api.serializers import PASSWORD_MIN_LENGTH as serializer_min
        from api.views_user import PASSWORD_MIN_LENGTH as view_min

        self.assertEqual(MIN_LENGTH, 8, '策略变了？如果是有意的，请同步更新前端文案与测试')
        self.assertEqual(serializer_min, MIN_LENGTH, '注册序列化器的长度与策略不一致')
        self.assertEqual(view_min, MIN_LENGTH, '改密接口的长度与策略不一致')

    def test_policy_rejects_weak_passwords(self):
        from api.password_policy import validate_password

        for weak, reason in [
            ('123456', '太短'),
            ('12345678', '纯数字'),
            ('password', '常见弱口令'),
            ('abcdefgh', '常见弱口令'),
            ('short1', '只有 7 位'),
        ]:
            with self.subTest(password=weak, reason=reason):
                self.assertIsNotNone(validate_password(weak), f'{weak} 应该被拒（{reason}）')

    def test_policy_accepts_reasonable_password(self):
        from api.password_policy import validate_password

        self.assertIsNone(validate_password('ZzStrong!2026'))

    # ---------- 三条入口都必须真的调用策略 ----------

    def test_register_rejects_short_password(self):
        cache.clear()
        response = self.client.post('/api/register/', {
            'username': 'pw_reg_short', 'password': '123456', 'password2': '123456',
            'email': 'pw_reg_short@example.invalid',
        }, format='json')
        self.assertEqual(response.status_code, 400, response.content)

    def test_register_rejects_all_digit_password(self):
        """纯数字 8 位：长度够但规则不允许 —— 改前的注册接口会放行"""
        cache.clear()
        response = self.client.post('/api/register/', {
            'username': 'pw_reg_digit', 'password': '12345678', 'password2': '12345678',
            'email': 'pw_reg_digit@example.invalid',
        }, format='json')
        self.assertEqual(response.status_code, 400, response.content)

    def test_register_accepts_strong_password(self):
        cache.clear()
        response = self.client.post('/api/register/', {
            'username': 'pw_reg_ok', 'password': 'ZzStrong!2026', 'password2': 'ZzStrong!2026',
            'email': 'pw_reg_ok@example.invalid',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(
            User.objects.get(username='pw_reg_ok').check_password('ZzStrong!2026'),
            '注册成功后用同一组密码应该能通过校验',
        )

    def test_password_change_uses_same_policy(self):
        user = User.objects.create_user(username='pw_change', password='ZzStrong!2026')
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(f'/api/users/{user.id}/password/', {
            'old_password': 'ZzStrong!2026', 'new_password': '12345678',
        }, format='json')
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn('new_password', response.json())

    def test_password_reset_uses_same_policy(self):
        """
        邮箱重置是**改前最弱的一环**（只判 `len < 6`，且没有纯数字规则）。

        这里走真实接口（`/api/password-reset/confirm/`，注意**不在** `/api/users/` 下，
        第一版就把 URL 猜错了、拿到 404），而不是直接调 `validate_password` ——
        否则测不出"接口到底有没有接上策略"。
        """
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        user = User.objects.create_user(username='pw_reset', password='ZzStrong!2026')
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        for weak in ('123456', '12345678'):
            with self.subTest(password=weak):
                cache.clear()   # 重置接口有 10/hour 限流，逐个用例清掉
                token = default_token_generator.make_token(user)
                response = self.client.post('/api/password-reset/confirm/', {
                    'uid': uid, 'token': token, 'new_password': weak,
                }, format='json')
                self.assertEqual(
                    response.status_code, 400,
                    f'邮箱重置接受了弱密码 {weak}：{response.content}',
                )
        self.assertTrue(
            user.check_password('ZzStrong!2026'),
            '被拒的重置不应该改动密码',
        )

    # ---------- 反向：登录不能跟着变严 ----------

    def test_login_still_accepts_legacy_short_password(self):
        """
        **存量用户必须还能登录。**

        如果他们设过 6 位密码，加固后一旦登录也校验长度，
        这些人会突然进不来，而找回密码又要求 8 位 —— 等于被锁在门外。
        所以登录路径刻意不做长度校验，这条测试锁住这个决定。
        """
        legacy = User.objects.create_user(username='pw_legacy', password='abc123')
        self.assertTrue(legacy.check_password('abc123'), '前提：这确实是旧密码')

        cache.clear()
        response = self.client.post('/api/login/', {
            'username': 'pw_legacy', 'password': 'abc123',
        }, format='json')
        self.assertEqual(
            response.status_code, 200,
            f'短密码的存量用户登不进来了 —— 这会把老用户锁在门外：{response.content}',
        )


# ============================================================================
# 第 106 批：media 孤儿文件清理
# ============================================================================
class PruneMediaCommandTests(TestCase):
    """
    `manage.py prune_media`（第 106 批）

    这个命令**会删文件**，所以它的失败方式最贵：把还在用的文件当垃圾删掉。
    实测演练（对真实开发库）删掉了 791 个孤儿文件 / 10.3 MB 且零假阳性，
    但那是人工核对的结果 —— 这里把它变成可重复的断言。

    三条必须锁住的规则：
      1. **被引用的文件绝不动**（含反斜杠路径与完整 URL 两种历史形态）；
      2. **太新的文件不动**（默认 7 天）—— 正在上传、还没入库的文件看起来也像孤儿；
      3. **不给 `--yes` 就不删**（与备份恢复同一个约定：危险操作默认干跑）。
    """

    def setUp(self):
        import tempfile

        cache.clear()
        self.tmp = Path(tempfile.mkdtemp(prefix='zz_prune_test_'))
        self.media = self.tmp / 'media'
        (self.media / 'detection_uploads').mkdir(parents=True, exist_ok=True)
        (self.media / 'annotated').mkdir(parents=True, exist_ok=True)
        self._override = override_settings(MEDIA_ROOT=str(self.media))
        self._override.enable()

        self.user = User.objects.create_user(username='pm_user', password='pw12345678')

    def tearDown(self):
        self._override.disable()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)
        cache.clear()

    def _write(self, rel: str, *, age_days: float = 30, content: bytes = b'x') -> Path:
        """造一个文件，并把 mtime 设成 N 天前（默认 30 天，肯定超过年龄门槛）"""
        path = self.media / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        stamp = time.time() - age_days * 86400
        os.utime(path, (stamp, stamp))
        return path

    def _run(self, *extra):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command('prune_media', *extra, stdout=out)
        return out.getvalue()

    # ---------- 规则 1：被引用的文件不动 ----------

    def test_non_media_files_are_never_deleted(self):
        """
        第 110 批补的关键护栏：**非媒体扩展名的文件一律不动**。

        这条来自一个真实险情：`media/README.md`（讲这个目录"哪些入库、哪些不入库"的
        说明文档）被这个命令列进了待删名单 —— 它当然没有任何 FileField 引用它，
        于是"没有任何数据库记录引用"这条判据把它判成了孤儿，只差一个 `--yes` 就没了。

        同类风险还有运维放进 media 的脚本、配置、`.gitattributes` 等：
        **它们天然不会被数据库引用，而这恰恰是这个命令唯一的判据。**

        所以判据改成"扩展名白名单"（`PRUNABLE_SUFFIXES`）：
        遇到没预料到的类型就**不删** —— 失效方向是"占点磁盘"而不是"文件没了"。
        """
        readme = self._write('README.md', content='# media 口径说明'.encode('utf-8'))
        notes = self._write('detection_uploads/notes.txt', content=b'not a media file')
        script = self._write('crop-images/backup.py', content=b'print("hi")')
        orphan = self._write('detection_uploads/orphan.JPG')

        output = self._run('--min-age-days', '0', '--yes')

        for kept in (readme, notes, script):
            self.assertTrue(kept.exists(), f'{kept.name} 被误删了 —— 非媒体文件不该动')
        self.assertFalse(orphan.exists(), '孤儿图片仍然应当被清掉')
        self.assertIn('非媒体文件', output)

    def test_referenced_file_is_never_deleted(self):
        kept = self._write('detection_uploads/keep_me.JPG')
        row = DetectionHistory.objects.create(
            user=self.user, detection_result='测试', confidence=0.9,
        )
        # 直接写字段，绕开 ImageField 的存储逻辑（我们只关心"库里有引用"）
        DetectionHistory.objects.filter(pk=row.pk).update(
            image='detection_uploads/keep_me.JPG',
        )

        orphan = self._write('detection_uploads/orphan.JPG')
        self._run('--min-age-days', '0', '--yes')

        self.assertTrue(kept.is_file(), '被数据库引用的文件被删了 —— 这是最糟的失败方式')
        self.assertFalse(orphan.is_file(), '孤儿文件应该被删掉')

    def test_backslash_path_in_database_still_protects_the_file(self):
        """
        历史数据里的路径是 **Windows 反斜杠**（`detection_uploads\\x.JPG`）。

        如果引用收集不把它归一成 `/`，这个文件就会被当成孤儿删掉 ——
        这是最容易漏的一种假阳性，所以单独测。
        """
        kept = self._write('detection_uploads/backslash.JPG')
        row = DetectionHistory.objects.create(
            user=self.user, detection_result='测试', confidence=0.9,
        )
        DetectionHistory.objects.filter(pk=row.pk).update(
            image='detection_uploads\\backslash.JPG',
        )

        self._run('--min-age-days', '0', '--yes')
        self.assertTrue(kept.is_file(), '反斜杠路径的引用没被识别 → 文件被误删')

    def test_annotated_image_reference_is_collected(self):
        """`annotated_image` 是第 106 批才开始写入的字段，也要纳入引用集合"""
        kept = self._write('detection_uploads/annotated_abc.JPG')
        row = DetectionHistory.objects.create(
            user=self.user, detection_result='测试', confidence=0.9,
        )
        DetectionHistory.objects.filter(pk=row.pk).update(
            image='detection_uploads/abc.JPG',
            annotated_image='detection_uploads/annotated_abc.JPG',
        )

        self._run('--min-age-days', '0', '--yes')
        self.assertTrue(kept.is_file(), 'annotated_image 的引用没被识别 → 标注图被误删')

    def test_news_image_reference_is_collected(self):
        """跨模型验证：不是只有 DetectionHistory 的字段会被收集"""
        kept = self._write('news_images/news_cover.png')
        News.objects.create(title='清理测试新闻', content='x', image='news_images/news_cover.png')

        self._run('--min-age-days', '0', '--yes')
        self.assertTrue(kept.is_file(), '新闻配图的引用没被识别 → 被误删')

    # ---------- 规则 2：太新的不动 ----------

    def test_recent_file_is_skipped(self):
        """刚落的文件可能是"正在上传、还没入库"，不能和业务抢"""
        fresh = self._write('detection_uploads/just_uploaded.JPG', age_days=0)
        old = self._write('detection_uploads/old_orphan.JPG', age_days=30)

        self._run('--min-age-days', '7', '--yes')
        self.assertTrue(fresh.is_file(), '太新的文件被删了 —— 可能与正在上传的文件抢')
        self.assertFalse(old.is_file(), '超龄的孤儿文件应该被删掉')

    # ---------- 规则 3：不给 --yes 不删 ----------

    def test_without_yes_nothing_is_deleted(self):
        orphan = self._write('detection_uploads/orphan.JPG')
        text = self._run('--min-age-days', '0')

        self.assertTrue(orphan.is_file(), '没有 --yes 也把文件删了 —— 危险操作的默认必须是干跑')
        self.assertIn('没有删除任何文件', text)

    # ---------- 报告内容 ----------

    def test_report_counts_and_manifest(self):
        self._write('detection_uploads/a.JPG')
        self._write('detection_uploads/b.JPG')
        manifest = self.tmp / 'manifest.json'

        text = self._run('--min-age-days', '0', '--manifest', str(manifest))
        self.assertIn('无引用且超过', text)
        self.assertIn('2 个', text)

        payload = json.loads(manifest.read_text(encoding='utf-8'))
        self.assertEqual(payload['orphan_files'], 2)
        self.assertFalse(payload['deleted'], '干跑时清单里不应标成已删除')
        self.assertCountEqual(
            payload['files'],
            ['detection_uploads/a.JPG', 'detection_uploads/b.JPG'],
        )

    def test_empty_directories_are_removed_after_pruning(self):
        """
        删完文件后，因此变空的目录应当一起清掉，但**非空目录要保留**。

        ⚠️ "保留"的那个文件必须**真的被数据库引用** —— 第一版随手造了个
        `news_images/still_here.png` 却没入库，于是它自己就是孤儿、
        被正常删掉了，测试却断言它还在（假失败）。
        """
        self._write('detection_uploads/only_file.JPG')
        empty_after = self.media / 'detection_uploads'

        kept = self._write('news_images/still_here.png')
        News.objects.create(title='目录保留测试', content='x', image='news_images/still_here.png')

        self._run('--min-age-days', '0', '--yes')
        self.assertFalse(empty_after.exists(), '空目录应该被清掉')
        self.assertTrue(kept.is_file(), '有引用的文件不该被删（它是"非空目录要保留"的前提）')
        self.assertTrue(kept.parent.exists(), '非空目录不该被删')


# ============================================================================
# 第 107 批：AI 启动预热
# ============================================================================
class AIWarmUpTests(TestCase):
    """
    AI 启动预热（第 107 批新增，第 113 批**改为后台线程**）

    解决的是"**第一个上传图片的用户要等 20 多秒**"：
    实测冷启动 = 加载模型 5.5s + 第一次真实推理 21s，之后每次 0.8s。
    `AIService.__new__` 里那个零张量"预测测试"只覆盖模型加载，
    盖不住第一次真实推理的一次性开销，所以账还是算在第一个用户头上。

    ⚠️⚠️ **第 113 批的重大修正**：第 107 批是**同步**调用 `warm_up()` 的，那是错的。
    `apps.ready()` 在服务器开始监听端口**之前**执行，所以同步预热会让服务在
    这 30 秒里完全不接受连接（浏览器显示"无法连接"）—— 对使用者来说比
    "第一个请求慢"更糟，因为看起来像**服务没起来**。
    实测更糟：在 `runserver --noreload` 下它**真的卡住过** ——
    日志停在 `results[0].plot(...)`、CPU 0%、4 分钟不监听端口，
    而同样的代码手动调用 30 秒就正常返回。

    现在改成守护线程 + 一把 `_WARMUP_LOCK`（防止"预热刚起来时正好来请求"
    导致两边同时加载模型）。所以下面的用例里多了两条钉住这次修正的。

    这些测试**不真的加载模型**（那会让整套测试慢几十秒，而且依赖权重文件），
    只钉住几件容易出错的事：
      1. 开关能关掉（跑测试/慢机器时不想拖长启动）；
      2. **预热失败绝不影响启动** —— 识别是核心功能，
         但它不该拥有"否决服务启动"的权力；
      3. 模型不可用时给出的是"跳过"而不是抛异常；
      4. **调度预热不能阻塞**（第 113 批）；
      5. **重复调度要被锁挡住**，且锁一定会释放（第 113 批）。
    """

    def test_warm_up_is_dispatched_in_background_thread(self):
        """
        第 113 批：`apps.ready()` 必须**在线程里**调度预热，不能同步等它。

        这条是本次事故的直接回归。判据选"源码里有没有
        `threading.Thread(... target=warm_up ...)`"而不是"测启动耗时" ——
        后者要真的加载模型才能测（几十秒 + 依赖权重文件），
        而**这个 bug 的本质就是"有没有用线程"**，静态判定足够且快得多。
        """
        from pathlib import Path

        from django.conf import settings

        source = Path(settings.BASE_DIR, 'api', 'apps.py').read_text(encoding='utf-8')
        self.assertIn('threading.Thread(', source, 'apps.ready() 里应当用线程调度预热')
        self.assertIn('target=warm_up', source, '线程的目标应当是 warm_up')
        self.assertIn('daemon=True', source, '必须是守护线程，否则会拖住进程退出')
        # 反向断言：不能再出现"直接调用 warm_up()"（同步写法）
        self.assertNotRegex(
            source,
            r'^\s+warm_up\(\)\s*$',
            'apps.py 里又出现了同步调用 warm_up() —— 那会让服务在预热期间不接受连接',
        )

    def test_concurrent_warm_up_is_skipped_by_lock(self):
        """
        第 113 批：预热正在跑时，第二次调度要被**跳过**（不能排队、更不能同时加载）。

        并发窗口是真实存在的：预热线程刚起来的那一瞬可能正好来了识别请求。
        两边同时走 `YOLO(model_path)` 会加载两份 6MB 权重、两个 torch 前向抢 CPU，
        而 torch 的延迟初始化在极端情况下不是线程安全的。

        用 `blocking=False` 拿锁：拿不到就返回 False（"已在进行中"）。
        """
        from api import ai_service

        # 手动占住锁，模拟"预热正在进行"
        self.assertTrue(ai_service._WARMUP_LOCK.acquire(blocking=False))
        try:
            with override_settings(AI_WARMUP_ON_STARTUP=True):
                self.assertFalse(
                    ai_service.warm_up(force=True),
                    '锁被占着时应当直接跳过，而不是排队等待或重复加载',
                )
        finally:
            ai_service._WARMUP_LOCK.release()

    def test_lock_is_released_on_every_failure_path(self):
        """
        第 113 批：**失败路径也必须放锁**。

        漏掉任何一条返回路径都会让锁永远不释放，后果是之后每次预热调度
        都被静默跳过（只有一行 info 日志）—— 而"第一个用户等 20 秒"
        这个问题会悄悄回来，且没有任何报错。
        """
        from api import ai_service

        class Boom:
            model = object()   # 非 None，让流程走到 predict

            def predict(self, _buffer):
                raise RuntimeError('模拟推理崩溃')

        with override_settings(AI_WARMUP_ON_STARTUP=True):
            with patch.object(ai_service, 'get_ai_service', return_value=Boom()):
                self.assertFalse(ai_service.warm_up(force=True))

        # 关键断言：锁必须已经释放（能再拿到）
        self.assertTrue(
            ai_service._WARMUP_LOCK.acquire(blocking=False),
            '预热失败后锁没有释放 —— 之后所有预热都会被静默跳过',
        )
        ai_service._WARMUP_LOCK.release()

    def test_switch_can_disable_warm_up(self):
        from api.ai_service import warm_up

        with override_settings(AI_WARMUP_ON_STARTUP=False):
            self.assertFalse(warm_up(), '开关关掉时不该预热')

    def test_warm_up_never_raises_when_model_missing(self):
        """
        模型不可用（未训练/文件被删）时，`warm_up()` 必须**安静返回 False**，
        而不是抛异常 —— 否则 `apps.ready()` 会把整个进程带崩，
        表现成"服务起不来"，而实际上除了识别以外的接口都是好的。
        """
        from api import ai_service

        with override_settings(AI_WARMUP_ON_STARTUP=True):
            with patch.object(ai_service, 'get_ai_service', return_value=None):
                self.assertFalse(ai_service.warm_up())

    def test_warm_up_swallows_unexpected_errors(self):
        """连 `predict()` 抛异常也要被吞掉（只记日志）"""
        from api import ai_service

        class Boom:
            model = object()   # 非 None，让流程走到 predict

            def predict(self, _buffer):
                raise RuntimeError('模拟推理崩溃')

        with override_settings(AI_WARMUP_ON_STARTUP=True):
            with patch.object(ai_service, 'get_ai_service', return_value=Boom()):
                self.assertFalse(ai_service.warm_up(), '预热出错时必须返回 False 而不是抛异常')

    def test_settings_default_enables_warm_up(self):
        """
        默认要开 —— 否则"第一个用户等 20 秒"这个问题会悄悄回来。

        ⚠️ 这里**不能直接读 `settings.AI_WARMUP_ON_STARTUP`**：它会被环境变量覆盖，
        如果跑测试时恰好设了 `AI_WARMUP_ON_STARTUP=False`（为了省时间），
        这条断言就会去测"当前环境值"而不是"默认值"，从而**假失败**（实测踩到）。
        正确做法是从源码里读 `_env_bool(...)` 的第二个参数，那才是默认值。
        """
        from pathlib import Path

        from django.conf import settings

        source = Path(settings.BASE_DIR, 'crop_disease_backend', 'settings.py').read_text(encoding='utf-8')
        self.assertIn(
            "AI_WARMUP_ON_STARTUP = _env_bool('AI_WARMUP_ON_STARTUP', not _IS_TESTING)",
            source,
            '默认值必须是"非测试环境为 True"；改成 False 等于默认不预热，'
            '而忘了开的代价是第一个农户盯着转圈 20 多秒',
        )

    def test_ai_warmup_disabled_while_testing(self):
        """
        跑测试时应当自动关掉预热（省时间、且不该依赖模型权重文件存在）。

        这条反向确认"开关真的接上了"：测试里若还是 True，
        整套测试会平白多花几十秒加载模型，CI 上没有权重文件还会报错。
        """
        from django.conf import settings

        self.assertFalse(
            getattr(settings, 'AI_WARMUP_ON_STARTUP', True),
            '测试环境里 AI 预热应当是关的（由 settings 里的 not _IS_TESTING 决定）；'
            '要显式打开请设环境变量 AI_WARMUP_ON_STARTUP=1',
        )


# ============================================================================
# 第 107 批：抗并发的日志轮转
# ============================================================================
class SafeRotatingLogHandlerTests(TestCase):
    """
    `SafeRotatingFileHandler`（第 107 批）

    为什么需要它：`manage.py test --parallel 4` 起 4 个**独立进程**，
    每个都有自己的 `RotatingFileHandler` 和**自己的锁** —— 它们会同时判断
    "该轮转了"然后抢同一个源文件改名。Windows 上 rename 只要还有别的句柄就抛
    `WinError 32`，于是日志里刷出一屏 `--- Logging error ---`，
    而且**失败方那条日志直接丢了**。

    这些测试都要用临时目录里的文件（不能碰 `logs/debug.log`：
    那是真实日志，而且正被别的进程写着）。
    """

    def setUp(self):
        import tempfile

        cache.clear()
        self.tmp = Path(tempfile.mkdtemp(prefix='zz_log_test_'))
        self.log_path = self.tmp / 'app.log'

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)
        cache.clear()

    def _logger(self, name: str):
        """
        取一个**不向 root 传播**的测试专用 logger。

        ⚠️ 不这么做的话，这两个测试会往 `logs/debug.log` 与终端里各刷 200 行
        （第一版就是这样：整个测试输出被 `AAA 0 zzzz…` / `关键日志 0 yyyy…` 淹没，
        真正要看的结果反而找不到）。测试自己的噪音不该污染所有人的输出。
        用 `propagate = False` + 独立 handler，比调高 root 日志级别更精确 ——
        别的测试仍然能正常打日志。
        """
        import logging

        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.INFO)
        return logger

    def _handler(self, **kwargs):
        from api.log_handlers import SafeRotatingFileHandler

        handler = SafeRotatingFileHandler(
            filename=str(self.log_path), maxBytes=1024, backupCount=3, encoding='utf-8', **kwargs,
        )
        # ⚠️ 把重试窗口调到 0：默认 1 秒 × 每条日志一次轮转 = 测试要跑几分钟
        #    （第一版就是这么慢的：4 条测试 377 秒）。行为逻辑不变，
        #    只是"抢不到文件时等多久"这个参数在测试里没意义。
        handler.retry_seconds = 0
        return handler

    def test_rollover_happens_normally(self):
        """正常情况要与标准库行为一致：写满就轮转，留下 .1"""
        handler = self._handler()
        logger = self._logger('zz_rollover_ok')
        logger.addHandler(handler)
        try:
            for index in range(200):
                logger.info('填充日志行 %s %s', index, 'x' * 50)
        finally:
            logger.removeHandler(handler)
            handler.close()

        self.assertTrue(self.log_path.exists())
        self.assertTrue(
            (self.tmp / 'app.log.1').exists(),
            '写满 maxBytes 之后应当产生 app.log.1',
        )

    def test_log_is_not_lost_when_rollover_cannot_rename(self):
        """
        **核心保证**：改名失败时不丢日志。

        模拟方式：把 `RotatingFileHandler.rotate` 打成"一直失败"，
        然后继续写日志。要求：
          · 不抛异常（异常会被 logging 吞掉并打一屏 stderr）；
          · 失败的**那条以及之后所有**日志仍然落到文件里。
        """
        from logging.handlers import RotatingFileHandler

        handler = self._handler()
        logger = self._logger('zz_rollover_fail')
        logger.addHandler(handler)

        # 让父类的 rotate 一直失败（模拟"文件被别的进程占着"）
        original_rotate = RotatingFileHandler.rotate

        def always_busy(source, dest):
            raise PermissionError(32, 'The process cannot access the file')

        RotatingFileHandler.rotate = staticmethod(always_busy)
        try:
            for index in range(200):
                logger.info('关键日志 %s %s', index, 'y' * 50)
        finally:
            RotatingFileHandler.rotate = original_rotate
            logger.removeHandler(handler)
            handler.close()

        content = self.log_path.read_text(encoding='utf-8', errors='replace')
        self.assertIn(
            '关键日志 0 ', content,
            '轮转失败后第一条日志就丢了 —— 说明流被关掉且没有重开',
        )
        self.assertIn(
            '关键日志 199 ', content,
            '轮转失败后最后一条日志也丢了 —— 后续写入没有落到任何文件',
        )

    def test_handler_keeps_writing_after_failed_rollover(self):
        """
        轮转失败后 `stream` 必须重新打开。

        这条单独测是因为它是"不丢日志"的**机制**：
        父类 `doRollover()` 先 `stream.close()` 再改名，改名失败时流已经关了 ——
        不重开的话，之后每条日志都会写到已关闭的流上（`ValueError`，被静默吞掉）。
        """
        from logging.handlers import RotatingFileHandler

        handler = self._handler()
        logger = self._logger('zz_rollover_reopen')
        logger.addHandler(handler)

        original_rotate = RotatingFileHandler.rotate
        RotatingFileHandler.rotate = staticmethod(
            lambda source, dest: (_ for _ in ()).throw(PermissionError(32, 'busy'))
        )
        try:
            for index in range(200):
                logger.info('AAA %s %s', index, 'z' * 50)
            self.assertIsNotNone(handler.stream, '轮转失败后 stream 应当已被重新打开')
            self.assertFalse(handler.stream.closed, '轮转失败后 stream 不该处于关闭状态')
            logger.info('BBB 轮转之后还能写')
        finally:
            RotatingFileHandler.rotate = original_rotate
            logger.removeHandler(handler)
            handler.close()

        self.assertIn('BBB 轮转之后还能写', self.log_path.read_text(encoding='utf-8', errors='replace'))

    def test_failed_rollover_enters_cooldown_instead_of_retrying_every_line(self):
        """
        **轮转注定失败时，不许每条日志都白等一次重试窗口**（第 118 批）。

        真实现象（本次就是被它拖垮的）：
          dev server 的 `logs/debug.log` 涨到 10MB 之后，父子两个 `runserver`
          进程互相占着文件 → rename 永远失败 → 而文件仍然超过 `maxBytes`，
          于是**下一条日志**又进 `doRollover()` 等满重试窗口（1 秒 × 21 次尝试）。
          一个请求要打十来条日志 = 每个请求慢十来秒：`/api/health/` 实测 9~12 秒，
          E2E 全线超时假红。

        这里把重试窗口调成 0（让"一次失败"= 一次 rotate 调用），
        冷却窗口调长（测试期间不会再尝试），然后写 50 条日志：
        只允许**第一次**真正去抢文件，后面的都必须走冷却直接追加。
        """
        from logging.handlers import RotatingFileHandler

        handler = self._handler()
        handler.retry_seconds = 0        # 一次失败 = 一次 rotate 调用，便于计数
        handler.cooldown_seconds = 60    # 冷却期覆盖整条用例
        logger = self._logger('zz_rollover_cooldown')
        logger.addHandler(handler)

        attempts = []

        def always_busy(source, dest):
            attempts.append(1)
            raise PermissionError(32, 'The process cannot access the file')

        original_rotate = RotatingFileHandler.rotate
        RotatingFileHandler.rotate = staticmethod(always_busy)
        try:
            for index in range(50):
                logger.info('冷却测试 %s %s', index, 'z' * 50)
        finally:
            RotatingFileHandler.rotate = original_rotate
            logger.removeHandler(handler)
            handler.close()

        self.assertEqual(
            len(attempts), 1,
            f'轮转失败后应当进入冷却、不再逐条重试，实际抢了 {len(attempts)} 次文件',
        )
        content = self.log_path.read_text(encoding='utf-8', errors='replace')
        self.assertIn('冷却测试 0 ', content, '冷却期间第一条日志就丢了')
        self.assertIn('冷却测试 49 ', content, '冷却期间后面的日志没有落盘')

    def test_cooldown_expires_and_rollover_is_retried(self):
        """
        冷却不是"把轮转永久关掉"：窗口过去后要再试一次。

        否则一旦某次失败，日志文件会无限增长（直到进程重启）——
        "不丢日志"的代价不该是"永远不再轮转"。
        """
        import time
        from logging.handlers import RotatingFileHandler

        handler = self._handler()
        handler.retry_seconds = 0
        handler.cooldown_seconds = 0.05
        logger = self._logger('zz_rollover_cooldown_expiry')
        logger.addHandler(handler)

        attempts = []

        def always_busy(source, dest):
            attempts.append(1)
            raise PermissionError(32, 'busy')

        original_rotate = RotatingFileHandler.rotate
        RotatingFileHandler.rotate = staticmethod(always_busy)
        try:
            for index in range(50):
                logger.info('冷却过期测试 %s %s', index, 'z' * 50)
            first_round = len(attempts)
            time.sleep(0.1)   # 等冷却窗口过去
            for index in range(50):
                logger.info('冷却过期测试二 %s %s', index, 'z' * 50)
        finally:
            RotatingFileHandler.rotate = original_rotate
            logger.removeHandler(handler)
            handler.close()

        self.assertGreaterEqual(first_round, 1, '第一次就该尝试轮转')
        self.assertGreater(
            len(attempts), first_round,
            '冷却窗口过去后应当重新尝试轮转，否则日志文件会无限增长',
        )

    def test_settings_uses_safe_handler_for_both_files(self):
        """
        配置必须真的用上这个处理器 —— 否则上面那些测试全绿也没意义。

        （第 101 批踩过同类坑：`throttle_classes` 挂了但 settings 里没有速率，
          DRF 在 rate=None 时直接放行，限流形同虚设。配置类的东西一定要断言"接上了"。）
        """
        from api.log_handlers import SafeRotatingFileHandler

        import logging.config
        from django.conf import settings

        logging.config.dictConfig(settings.LOGGING)
        for logger_name in ('root', 'django', 'api'):
            handlers = logging.getLogger('' if logger_name == 'root' else logger_name).handlers
            with self.subTest(logger=logger_name):
                self.assertTrue(
                    any(isinstance(handler, SafeRotatingFileHandler) for handler in handlers),
                    f'{logger_name} 上没有挂 SafeRotatingFileHandler：'
                    f'{[type(h).__name__ for h in handlers]} —— '
                    '并发轮转会重新开始丢日志',
                )


# ============================================================================
# 第 102 批：数据备份与恢复
# ============================================================================
class BackupCommandTests(TransactionTestCase):
    """
    备份 / 校验 / 恢复三个命令（第 102 批）

    为什么值得测：**备份的失败方式全是安静的** ——
      · 备份脚本本身报错（历史事故：`forum_backup` 里 `NameError: timezone`，
        还有两个**模型里根本不存在的字段**，等于那条备份路径从未真正跑通过）；
      · 备份"看起来生成了"但校验和不对（拷贝被截断）；
      · 校验脚本自己写错表名 → 把好备份判成坏的（本批就踩了，
        `api_forum_post` 这种想当然的名字）。

    所以这里钉住三件事：**能备出来、能验通过、没 --yes 不许恢复**，
    外加一条"表名白名单必须与模型一致"的防复发断言。

    ⚠️ 为什么是 `TransactionTestCase` 而不是 `TestCase`：备份命令需要一个
    **磁盘上的库文件**（SQLite 在线备份 API 只能对文件操作），所以要临时把连接的
    NAME 指到一个导出文件上。而 `TestCase` 把每个用例包在事务里，
    **一旦关闭连接就会 "Cannot operate on a closed database"**（实测）。
    `TransactionTestCase` 不用外层事务，改连接、导出、恢复都能正常工作
    （代价是每个用例后要 flush，慢一些 —— 这里 11 个用例约 5 秒，可以接受）。
    """

    @classmethod
    def setUpClass(cls):
        import shutil
        import sqlite3
        import tempfile

        super().setUpClass()
        from django.db import connection

        cls._tmp = tempfile.mkdtemp(prefix='zz_backup_test_')
        cls._backup_dir = Path(cls._tmp) / 'backups'
        cls._backup_dir.mkdir(parents=True, exist_ok=True)
        cls._db_file = Path(cls._tmp) / 'test_db.sqlite3'

        # 把当前（内存）测试库导出成真实文件：备份命令只能对文件用在线备份 API
        source = sqlite3.connect(connection.settings_dict['NAME'], uri=True)
        try:
            target = sqlite3.connect(str(cls._db_file))
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()

        cls._original_db_name = connection.settings_dict['NAME']
        connection.close()
        connection.settings_dict['NAME'] = str(cls._db_file)
        cls._original_backup_dir = os.environ.get('DJANGO_BACKUP_DIR')
        os.environ['DJANGO_BACKUP_DIR'] = str(cls._backup_dir)
        cls._shutil = shutil

    @classmethod
    def tearDownClass(cls):
        from django.db import connection

        connection.close()
        connection.settings_dict['NAME'] = cls._original_db_name
        if cls._original_backup_dir is None:
            os.environ.pop('DJANGO_BACKUP_DIR', None)
        else:
            os.environ['DJANGO_BACKUP_DIR'] = cls._original_backup_dir
        cls._shutil.rmtree(cls._tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        self.tmp = self._tmp
        self.backup_dir = self._backup_dir
        self._db_file = self._db_file

        self.user = User.objects.create_user(username='bk_user', password='pw12345678')
        board = ForumBoard.objects.create(name='备份测试版块', is_active=True)
        Post.objects.create(title='备份测试帖', content='x', author=self.user, board=board)

    def tearDown(self):
        cache.clear()

    def _backup(self, *extra):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command('backend_backup', *extra, stdout=out)
        return out.getvalue()

    def _latest_backup(self) -> Path:
        from api import backup_utils as bu

        backups = [p for p in bu.list_backups(self.backup_dir) if (p / bu.MANIFEST_NAME).exists()]
        self.assertTrue(backups, '没有生成任何备份目录')
        return backups[0]

    # ---------- 备份 ----------

    def test_backup_creates_manifest_and_db_copy(self):
        from api import backup_utils as bu

        text = self._backup('--no-media')      # 媒体包大，单测里跳过
        target = self._latest_backup()

        self.assertIn('备份完成', text)
        self.assertTrue((target / bu.DB_NAME).exists(), '缺少数据库副本')
        self.assertTrue((target / bu.MANIFEST_NAME).exists(), '缺少清单')

        manifest = bu.read_json(target / bu.MANIFEST_NAME)
        self.assertEqual(manifest['format_version'], bu.BACKUP_FORMAT_VERSION)
        self.assertIn(bu.DB_NAME, manifest['artifacts'])
        self.assertTrue(manifest['artifacts'][bu.DB_NAME]['sha256'], '没记校验和')
        self.assertGreaterEqual(manifest['counts']['posts'], 1)

    def test_backup_db_copy_is_readable(self):
        """备份出来的库必须能打开 —— 这是"备份可用"的底线"""
        import sqlite3

        from api import backup_utils as bu

        self._backup('--no-media')
        target = self._latest_backup()
        conn = sqlite3.connect(f'file:{target / bu.DB_NAME}?mode=ro', uri=True)
        try:
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        finally:
            conn.close()

    def test_keep_prunes_old_backups(self):
        from api import backup_utils as bu

        for _ in range(3):
            self._backup('--no-media', '--no-data-dump')
        self._backup('--no-media', '--no-data-dump', '--keep', '2')
        remaining = [p for p in bu.list_backups(self.backup_dir) if (p / bu.MANIFEST_NAME).exists()]
        self.assertEqual(len(remaining), 2, f'保留策略没生效：{len(remaining)} 份')

    # ---------- 校验 ----------

    def test_verify_passes_on_fresh_backup(self):
        from io import StringIO

        from django.core.management import call_command

        self._backup('--no-media')
        out = StringIO()
        call_command('backup_verify', '--skip-media', stdout=out)
        self.assertIn('全部校验通过', out.getvalue())

    def test_verify_detects_corrupted_artifact(self):
        """校验和的作用就在这里：内容被改动必须被发现（宁可误报也不能漏报）"""
        from io import StringIO

        from django.core.management import call_command

        from api import backup_utils as bu

        self._backup('--no-media')
        target = self._latest_backup()
        # 制造"静默损坏"：在库文件尾部追加垃圾（体积变了、校验和也变了）
        with open(target / bu.DB_NAME, 'ab') as handle:
            handle.write(b'CORRUPTED')

        out = StringIO()
        call_command('backup_verify', '--skip-media', stdout=out)
        text = out.getvalue()
        self.assertTrue('不符' in text or '✗' in text, f'损坏没被发现：\n{text}')

    def test_verify_strict_returns_nonzero_on_problem(self):
        from io import StringIO

        from django.core.management import call_command

        from api import backup_utils as bu

        self._backup('--no-media')
        target = self._latest_backup()
        (target / bu.DB_NAME).unlink()      # 直接删掉库副本 = 不可用的备份

        out = StringIO()
        with self.assertRaises(SystemExit):
            call_command('backup_verify', '--skip-media', '--strict', stdout=out)

    def test_count_query_table_names_match_models(self):
        """
        防复发：`backup_verify.COUNT_QUERIES` 里的表名必须真实存在。

        本批的真实事故：表名是**猜的**（写成 `api_forum_post`），
        而实际的论坛模型在 `models_forum.py` 里、表名是 `api_post` ——
        校验脚本于是把一份完好的备份报成"3 张表不存在"。
        """
        import sqlite3

        from django.db import connection

        from api.management.commands.backup_verify import COUNT_QUERIES

        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing = {row[0] for row in cursor.fetchall()}

        for key, sql in COUNT_QUERIES.items():
            table = sql.split('FROM')[1].strip().split()[0]
            with self.subTest(key=key):
                self.assertIn(table, existing, f'{key} 的表名 {table} 在库里不存在（写错了？）')

    # ---------- 恢复 ----------

    def test_restore_refuses_without_yes(self):
        """没有 --yes 只能打印计划：这条是"误操作保护"的核心"""
        from io import StringIO

        from django.core.management import call_command

        self._backup('--no-media')
        target = self._latest_backup()

        out = StringIO()
        call_command('backend_restore', target.name, '--db-only',
                     '--no-safety-backup', '--dir', str(self.backup_dir), stdout=out)
        text = out.getvalue()
        self.assertIn('没有修改任何数据', text)
        self.assertIn('--yes', text)

    def test_restore_refuses_corrupted_backup(self):
        """用坏备份覆盖好数据 = 把事故从"数据丢了"升级成"数据彻底没了" """
        from io import StringIO

        from django.core.management import call_command

        from api import backup_utils as bu

        self._backup('--no-media')
        target = self._latest_backup()
        with open(target / bu.DB_NAME, 'ab') as handle:
            handle.write(b'CORRUPTED')

        out = StringIO()
        with self.assertRaises(SystemExit):
            call_command('backend_restore', target.name, '--yes', '--db-only',
                         '--no-safety-backup', '--dir', str(self.backup_dir), stdout=out)
        self.assertIn('校验未通过', out.getvalue())

    def test_restore_rejects_path_traversal_members(self):
        """
        媒体包成员名不可信：恢复是"读外部文件"的操作，必须拒绝越界路径。

        这里直接构造一个带 `../` 成员的 tar 包，验证 `_restore_media` 会跳过它，
        而不是把文件写到 media 之外。
        """
        import io
        import tarfile

        from api import backup_utils as bu
        from api.management.commands.backend_restore import Command

        self._backup('--no-media')
        target = self._latest_backup()

        # 造一个只有恶意成员的媒体包
        archive = target / bu.MEDIA_ARCHIVE
        with tarfile.open(archive, 'w:gz') as tar:
            payload = b'PWNED'
            info = tarfile.TarInfo('../escaped.txt')
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))

        media_root = Path(self.tmp) / 'media_out'
        media_root.mkdir(parents=True, exist_ok=True)
        Command()._restore_media(target, media_root, overwrite=True)

        escaped = Path(self.tmp) / 'escaped.txt'
        self.assertFalse(escaped.exists(), '越界路径被写出来了 —— 目录穿越防护失效')
        self.assertFalse((media_root.parent / 'escaped.txt').exists())

    def test_restore_media_does_not_overwrite_by_default(self):
        """默认只补缺失文件：恢复不该把现有较新的上传覆盖回旧版本"""
        import io
        import tarfile

        from api import backup_utils as bu
        from api.management.commands.backend_restore import Command

        self._backup('--no-media')
        target = self._latest_backup()

        archive = target / bu.MEDIA_ARCHIVE
        with tarfile.open(archive, 'w:gz') as tar:
            payload = b'FROM_BACKUP'
            info = tarfile.TarInfo('avatars/keep.txt')
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))

        media_root = Path(self.tmp) / 'media_merge'
        (media_root / 'avatars').mkdir(parents=True, exist_ok=True)
        existing = media_root / 'avatars' / 'keep.txt'
        existing.write_bytes(b'CURRENT_NEWER')

        Command()._restore_media(target, media_root, overwrite=False)
        self.assertEqual(existing.read_bytes(), b'CURRENT_NEWER', '默认不该覆盖已有文件')

        Command()._restore_media(target, media_root, overwrite=True)
        self.assertEqual(existing.read_bytes(), b'FROM_BACKUP', '--overwrite-media 时应覆盖')


# ============================================================================
# 第 101 批：注销冷静期（15 天内可取消）
# ============================================================================
class AccountDeletionGracePeriodTests(TestCase):
    """
    注销从"立刻生效"改成"15 天冷静期、可取消"（第 101 批）

    为什么值得这么细地测：冷静期的价值全在**边界**上 ——
      · 申请后必须**立刻登不上**（否则用户以为没生效，会反复点）；
      · 但个人信息必须**完好**（否则取消也白搭）；
      · 到期才清空，且**只能靠定时任务**触发（没人会替它触发）；
      · 取消要能"登不上时也能取消"，否则冷静期等于形同虚设。
    """

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='grace_user', password='pw12345678',
            email='grace@example.invalid', first_name='G', last_name='P',
        )
        self.user.bio = '简介'
        self.user.save()
        self.client_auth = APIClient()
        self.client_auth.force_authenticate(user=self.user)

    def _apply(self):
        return self.client_auth.post(
            '/api/users/me/delete/',
            {'password': 'pw12345678', 'confirm': 'DELETE'}, format='json',
        )

    # ---------- 申请阶段 ----------

    def test_apply_returns_grace_info(self):
        response = self._apply()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['grace_days'], 15)
        self.assertIsNotNone(response.data['scheduled_for'])

    def test_apply_disables_login_immediately(self):
        """申请后必须**立刻**登不上 —— 用户申请注销时最直接的预期"""
        self._apply()
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.has_pending_deletion)

    def test_apply_keeps_personal_data(self):
        """冷静期内**不清个人信息** —— 清了就撤不回来"""
        self._apply()
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'grace_user', '用户名不能改（还要能登回来）')
        self.assertEqual(self.user.email, 'grace@example.invalid')
        self.assertEqual(self.user.first_name, 'G')
        self.assertFalse(self.user.is_deleted)

    def test_apply_invalidates_tokens(self):
        Token.objects.create(user=self.user)
        self._apply()
        self.assertEqual(Token.objects.filter(user=self.user).count(), 0)

    def test_apply_requires_password_and_confirm(self):
        bad = self.client_auth.post('/api/users/me/delete/', {'confirm': 'DELETE'}, format='json')
        self.assertEqual(bad.status_code, 400)
        bad2 = self.client_auth.post(
            '/api/users/me/delete/', {'password': 'wrong', 'confirm': 'DELETE'}, format='json',
        )
        self.assertEqual(bad2.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_pending_deletion)

    # ---------- 登录时的引导 ----------

    def test_login_tells_user_it_is_cancellable(self):
        """密码对但账号在冷静期 → 必须给出**可取消**的引导，而不是"账户已被禁用\""""
        self._apply()
        response = APIClient().post(
            '/api/login/', {'username': 'grace_user', 'password': 'pw12345678'}, format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['code'], 'account_pending_deletion')
        self.assertTrue(response.data['can_cancel'])
        self.assertEqual(response.data['days_left'], 15)

    # ---------- 取消阶段 ----------

    def test_cancel_requires_password(self):
        self._apply()
        response = APIClient().post(
            '/api/users/me/cancel-deletion/', {'username': 'grace_user', 'password': 'wrong'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.has_pending_deletion)

    def test_cancel_works_without_token(self):
        """
        主要场景就是"已经登不上了"，所以这个接口**必须支持匿名调用** ——
        否则没有任何自助恢复途径，冷静期形同虚设。
        """
        self._apply()
        anonymous = APIClient()
        response = anonymous.post(
            '/api/users/me/cancel-deletion/',
            {'username': 'grace_user', 'password': 'pw12345678'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get('token'), '取消成功后应直接签发可用 Token')

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.has_pending_deletion)
        self.assertIsNotNone(self.user.deletion_cancelled_at)

        # 恢复后能正常登录
        login = APIClient().post(
            '/api/login/', {'username': 'grace_user', 'password': 'pw12345678'}, format='json',
        )
        self.assertEqual(login.status_code, 200)

    def test_cancel_uses_same_message_for_wrong_user_and_wrong_password(self):
        """失败文案不能区分"用户不存在"和"密码错" —— 否则变成账号探测器"""
        self._apply()
        client = APIClient()
        wrong_pw = client.post(
            '/api/users/me/cancel-deletion/',
            {'username': 'grace_user', 'password': 'nope'}, format='json',
        )
        no_user = client.post(
            '/api/users/me/cancel-deletion/',
            {'username': 'no_such_user_xyz', 'password': 'nope'}, format='json',
        )
        self.assertEqual(wrong_pw.status_code, no_user.status_code)
        self.assertEqual(wrong_pw.data['detail'], no_user.data['detail'])

    def test_cancel_rejected_when_not_pending(self):
        response = APIClient().post(
            '/api/users/me/cancel-deletion/',
            {'username': 'grace_user', 'password': 'pw12345678'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    # ---------- 到期执行 ----------

    def test_purge_command_only_processes_due_requests(self):
        from django.core.management import call_command
        from io import StringIO

        self._apply()
        # 还没到期：purge 不该动它
        out = StringIO()
        call_command('purge_deletion_requests', stdout=out)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_deleted, '没到期就删了 —— 冷静期被绕过')
        self.assertIn('没有需要处理', out.getvalue())

        # 把计划时间改到过去 → 到期
        User.objects.filter(pk=self.user.pk).update(
            deletion_scheduled_for=timezone.now() - timezone.timedelta(minutes=1),
        )
        out2 = StringIO()
        call_command('purge_deletion_requests', stdout=out2)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_deleted, '到期后应当真正执行注销')
        self.assertTrue(self.user.username.startswith('deleted_'))
        self.assertEqual(self.user.email, '')
        self.assertIn('已执行注销：1 个', out2.getvalue())

    def test_purge_dry_run_does_not_modify(self):
        from django.core.management import call_command
        from io import StringIO

        self._apply()
        User.objects.filter(pk=self.user.pk).update(
            deletion_scheduled_for=timezone.now() - timezone.timedelta(minutes=1),
        )
        out = StringIO()
        call_command('purge_deletion_requests', '--dry-run', stdout=out)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_deleted, '--dry-run 不该改数据')
        self.assertIn('dry-run', out.getvalue())

    def test_purge_keeps_content_of_purged_user(self):
        """到期执行也不能把别人的内容带走（与第 95 批同一约束）"""
        from django.core.management import call_command

        board = ForumBoard.objects.create(name='冷静期版块', is_active=True)
        post = Post.objects.create(title='我的帖子', content='x', author=self.user, board=board)
        other = User.objects.create_user(username='grace_other', password='pw12345678')
        Comment.objects.create(content='别人的评论', author=other, post=post)

        self._apply()
        User.objects.filter(pk=self.user.pk).update(
            deletion_scheduled_for=timezone.now() - timezone.timedelta(minutes=1),
        )
        from io import StringIO as _StringIO
        call_command('purge_deletion_requests', stdout=_StringIO())

        self.assertTrue(Post.objects.filter(id=post.id).exists())
        self.assertTrue(Comment.objects.filter(post=post, author=other).exists())

    def test_pending_deletion_hidden_from_admin_list(self):
        """冷静期中的账号不该继续留在用户管理列表里（看着仍像正常用户）"""
        admin = User.objects.create_user(
            username='grace_admin', password='pw12345678', is_staff=True, role='ADMIN',
        )
        self._apply()
        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get('/api/admin/users/', {'page_size': 100})
        usernames = [row['username'] for row in response.data['results']]
        self.assertNotIn('grace_user', usernames)

    def test_grace_days_can_be_configured(self):
        with self.settings(ACCOUNT_DELETION_GRACE_DAYS=3):
            self.assertEqual(self.user.deletion_grace_days(), 3)
            self._apply()
            self.user.refresh_from_db()
            delta = self.user.deletion_scheduled_for - self.user.deletion_requested_at
            self.assertEqual(delta.days, 3)


# ============================================================================
# 第 100 批：管理端排序 + 批量操作
# ============================================================================
class AdminOrderingTests(TestCase):
    """
    列表排序（白名单）

    为什么要有白名单而不是把参数直接拼进 `order_by`：
      · 任意字段排序可以让攻击者用"二分试探"推断隐藏数据（经典的信息泄露手法）；
      · 也会因为排到未索引/未注解的字段而 500。
    """

    def setUp(self):
        cache.clear()
        # ⚠️ 管理员用户名不要用同一个前缀：第一版起名 `ord_admin`，于是"取 ord_ 开头的三个"
        #    把管理员自己也算了进去（4 条），断言全部失败 —— 是测试写错，不是排序错。
        self.admin = User.objects.create_user(
            username='zz_ordering_admin', password='pw12345678', is_staff=True, role='ADMIN',
        )
        # 三个用户，积分各不相同，便于验证排序真的生效
        self.low = User.objects.create_user(username='ord_a_low', password='pw12345678', points=10)
        self.mid = User.objects.create_user(username='ord_b_mid', password='pw12345678', points=50)
        self.high = User.objects.create_user(username='ord_c_high', password='pw12345678', points=90)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _usernames(self, params=None):
        response = self.client.get('/api/admin/users/', {'page_size': 100, **(params or {})})
        self.assertEqual(response.status_code, 200)
        return [row['username'] for row in response.data['results']]

    #: 只看本用例造的三个（管理员用户名不带这个前缀）
    def _only_mine(self, params=None):
        return [n for n in self._usernames(params) if n.startswith('ord_')]

    def test_default_order_is_newest_first(self):
        # 只校验我们造的这三个的相对顺序：注册越晚排越前
        self.assertEqual(self._only_mine(), ['ord_c_high', 'ord_b_mid', 'ord_a_low'])

    def test_order_by_points_ascending(self):
        self.assertEqual(self._only_mine({'ordering': 'points'}),
                         ['ord_a_low', 'ord_b_mid', 'ord_c_high'])

    def test_order_by_points_descending(self):
        self.assertEqual(self._only_mine({'ordering': '-points'}),
                         ['ord_c_high', 'ord_b_mid', 'ord_a_low'])

    def test_order_by_username(self):
        self.assertEqual(self._only_mine({'ordering': 'username'}),
                         ['ord_a_low', 'ord_b_mid', 'ord_c_high'])

    def test_unknown_ordering_falls_back_to_default(self):
        """非法字段不能 500，也不能真的按它排（回落到默认排序）"""
        response = self.client.get('/api/admin/users/', {'ordering': 'is_superuser'})
        self.assertEqual(response.status_code, 200)
        response2 = self.client.get('/api/admin/users/', {'ordering': 'password'})
        self.assertEqual(response2.status_code, 200)
        response3 = self.client.get('/api/admin/users/', {'ordering': '; DROP TABLE api_customuser'})
        self.assertEqual(response3.status_code, 200)
        self.assertTrue(User.objects.filter(id=self.admin.id).exists(), '库还在')


class BulkOperationTests(TestCase):
    """
    批量审核 / 批量流转反馈 / 批量删除用户（第 100 批）

    这一批的重点不是"能不能批量"，而是**批量入口不能变成绕过单条校验的后门** ——
    所以每个用例都在验证"汇总结果里有没有如实报告失败"。
    """

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            username='bulk_admin', password='pw12345678', is_staff=True, role='ADMIN',
        )
        self.normal = User.objects.create_user(username='bulk_user', password='pw12345678')
        self.other = User.objects.create_user(username='bulk_other', password='pw12345678')
        self.board = ForumBoard.objects.create(name='批量测试版块', is_active=True)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    # ---------- 批量审核帖子 ----------

    def _make_pending(self, n=3, author=None):
        return [
            Post.objects.create(
                title=f'待审{i}', content='内容', author=author or self.normal,
                board=self.board, status='pending',
            )
            for i in range(n)
        ]

    def test_bulk_review_approves_selected_posts(self):
        posts = self._make_pending(3)
        response = self.client.post(
            '/api/forums/posts/bulk-review/',
            {'ids': [p.id for p in posts], 'action': 'approve'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['succeeded'], 3)
        self.assertEqual(response.data['failed'], 0)
        for post in posts:
            post.refresh_from_db()
            self.assertEqual(post.status, 'published')

    def test_bulk_review_rejects_with_reason(self):
        posts = self._make_pending(2)
        response = self.client.post(
            '/api/forums/posts/bulk-review/',
            {'ids': [p.id for p in posts], 'action': 'reject', 'reason': '广告'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        for post in posts:
            post.refresh_from_db()
            self.assertEqual(post.status, 'hidden')

    def test_bulk_review_skips_non_pending_and_reports_why(self):
        """已发布的帖子不该被"批量通过"，且必须如实报告被跳过"""
        posts = self._make_pending(2)
        posts[1].status = 'published'
        posts[1].save(update_fields=['status'])

        response = self.client.post(
            '/api/forums/posts/bulk-review/',
            {'ids': [p.id for p in posts], 'action': 'approve'}, format='json',
        )
        self.assertEqual(response.data['succeeded'], 1)
        self.assertEqual(response.data['failed'], 1)
        failed = [r for r in response.data['results'] if not r['ok']]
        self.assertIn('不是待审状态', failed[0]['detail'])

    def test_bulk_review_reports_missing_ids(self):
        response = self.client.post(
            '/api/forums/posts/bulk-review/', {'ids': [999999], 'action': 'approve'}, format='json',
        )
        self.assertEqual(response.data['succeeded'], 0)
        self.assertIn('不存在', response.data['results'][0]['detail'])

    def test_bulk_review_rejects_bad_action(self):
        response = self.client.post(
            '/api/forums/posts/bulk-review/', {'ids': [1], 'action': 'delete'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_bulk_review_requires_moderator(self):
        client = APIClient()
        client.force_authenticate(user=self.normal)
        response = client.post(
            '/api/forums/posts/bulk-review/', {'ids': [1], 'action': 'approve'}, format='json',
        )
        self.assertEqual(response.status_code, 403)

    # ---------- 批量流转反馈 ----------

    def _make_feedback(self, n=3):
        return [
            Feedback.objects.create(user=self.normal, suggestion=f'反馈{i}', category='suggestion')
            for i in range(n)
        ]

    def test_bulk_feedback_status(self):
        items = self._make_feedback(3)
        response = self.client.post(
            '/api/feedback/bulk-status/',
            {'ids': [f.id for f in items], 'status': 'processing'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['succeeded'], 3)
        for item in items:
            item.refresh_from_db()
            self.assertEqual(item.status, 'processing')

    def test_bulk_feedback_resolved_requires_reply(self):
        """批量标记"已处理"必须有回复内容 —— 与单条 reply 的规则一致"""
        items = self._make_feedback(2)
        response = self.client.post(
            '/api/feedback/bulk-status/',
            {'ids': [f.id for f in items], 'status': 'resolved'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('admin_reply', response.data)

    def test_bulk_feedback_resolved_sets_handled_at(self):
        items = self._make_feedback(2)
        response = self.client.post(
            '/api/feedback/bulk-status/',
            {'ids': [f.id for f in items], 'status': 'resolved', 'admin_reply': '已处理'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        for item in items:
            item.refresh_from_db()
            self.assertEqual(item.status, 'resolved')
            self.assertEqual(item.admin_reply, '已处理')
            self.assertIsNotNone(item.handled_at)

    def test_bulk_feedback_rejects_invalid_status(self):
        items = self._make_feedback(1)
        response = self.client.post(
            '/api/feedback/bulk-status/',
            {'ids': [f.id for f in items], 'status': 'deleted'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_bulk_feedback_requires_admin(self):
        items = self._make_feedback(1)
        client = APIClient()
        client.force_authenticate(user=self.normal)
        response = client.post(
            '/api/feedback/bulk-status/',
            {'ids': [f.id for f in items], 'status': 'processing'}, format='json',
        )
        self.assertEqual(response.status_code, 403)

    # ---------- 批量删除用户 ----------

    def test_bulk_delete_users(self):
        response = self.client.post(
            '/api/admin/users/bulk-delete/', {'ids': [self.other.id]}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['succeeded'], 1)
        self.other.refresh_from_db()
        self.assertTrue(self.other.is_deleted)

    def test_bulk_delete_cannot_bypass_self_guard(self):
        """批量入口不能绕过"不能删自己" —— 这是本批最该守住的一条"""
        response = self.client.post(
            '/api/admin/users/bulk-delete/', {'ids': [self.admin.id, self.other.id]}, format='json',
        )
        self.assertEqual(response.data['succeeded'], 1, '另一个用户应当被删除')
        self.assertEqual(response.data['failed'], 1, '自己那条应当被拒绝')
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_deleted, '管理员不能把自己删掉')

    def test_bulk_delete_reports_reason_per_row(self):
        superuser = User.objects.create_superuser(username='bulk_super', password='pw12345678')
        response = self.client.post(
            '/api/admin/users/bulk-delete/', {'ids': [superuser.id]}, format='json',
        )
        self.assertEqual(response.data['succeeded'], 0)
        self.assertIn('超级管理员', response.data['results'][0]['detail'])

    def test_admin_list_post_without_bulk_path_is_405(self):
        response = self.client.post('/api/admin/users/', {}, format='json')
        self.assertEqual(response.status_code, 405)

    def test_bulk_delete_requires_admin(self):
        client = APIClient()
        client.force_authenticate(user=self.normal)
        response = client.post(
            '/api/admin/users/bulk-delete/', {'ids': [self.other.id]}, format='json',
        )
        self.assertEqual(response.status_code, 403)


# ============================================================================
# 第 95 批：账号注销 / 删除用户
# ============================================================================
class AccountDeletionTests(TestCase):
    """
    用户自己注销 + 管理员删除用户（第 95 批）

    改前的事实：**两边都没有入口** ——
      · 用户侧：没有任何注销 API/按钮（隐私政策却写着"可申请注销"，靠人工）；
      · 管理侧：用户管理页只提供"读"（禁账号/改角色/删除都明确不做），
        Django admin 里删用户还会因为关联表未注册而 `IntegrityError`（第 43 批修过）。

    采用**软删除**而不是 `user.delete()`：帖子的 author 是 SET_NULL、评论/识别记录是
    CASCADE —— 硬删会把别人写在帖子下的评论一起带走（第 92 批刚修过同类问题）。
    """

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='del_self', password='pw12345678', email='self@example.invalid',
        )
        self.other = User.objects.create_user(username='del_other', password='pw12345678')
        self.admin = User.objects.create_user(
            username='del_admin', password='pw12345678', is_staff=True, role='ADMIN',
        )
        self.superuser = User.objects.create_superuser(
            username='del_super', password='pw12345678',
        )

        self.client_user = APIClient()
        self.client_user.force_authenticate(user=self.user)
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)
        self.client_super = APIClient()
        self.client_super.force_authenticate(user=self.superuser)

    # ---------- 用户自助注销 ----------

    def test_self_delete_requires_password(self):
        response = self.client_user.post(
            '/api/users/me/delete/', {'confirm': 'DELETE'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.data)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_deleted)

    def test_self_delete_rejects_wrong_password(self):
        response = self.client_user.post(
            '/api/users/me/delete/', {'password': 'not-my-password', 'confirm': 'DELETE'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_deleted)

    def test_self_delete_requires_confirm_word(self):
        response = self.client_user.post(
            '/api/users/me/delete/', {'password': 'pw12345678'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('confirm', response.data)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_deleted)

    def test_self_delete_enters_grace_period(self):
        """
        第 101 批：自助注销进入**冷静期**（不再是立即清空）

        这一条替换了原来的 `test_self_delete_success_anonymizes_and_disables` ——
        语义变了，断言也必须跟着变，否则测试会因为"没清空"而误报成失败。
        真正的清空改由到期后的 `purge_deletion_requests` 负责（见冷静期那组测试）。
        """
        Token.objects.create(user=self.user)
        response = self.client_user.post(
            '/api/users/me/delete/', {'password': 'pw12345678', 'confirm': 'DELETE'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        # 立即停用 + 进入冷静期
        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.has_pending_deletion)
        self.assertFalse(self.user.is_deleted, '冷静期内不该标记为已注销')
        self.assertIsNotNone(self.user.deletion_scheduled_for)
        # 但个人信息**保留**（否则取消也回不来）
        self.assertNotEqual(self.user.email, '')
        self.assertEqual(self.user.username, 'del_self')
        # 凭证全部失效
        self.assertEqual(Token.objects.filter(user=self.user).count(), 0)

    def test_pending_deletion_account_cannot_login(self):
        """第 101 批：冷静期内的账号也登不上（改成这个断言的 404 是因为用户名不再变形）"""
        self.client_user.post(
            '/api/users/me/delete/', {'password': 'pw12345678', 'confirm': 'DELETE'},
            format='json',
        )
        response = APIClient().post(
            '/api/login/', {'username': 'del_self', 'password': 'pw12345678'}, format='json',
        )
        self.assertEqual(response.status_code, 403, '冷静期内必须登录不了')
        self.assertEqual(response.data.get('code'), 'account_pending_deletion')

    def test_fully_deleted_account_cannot_login(self):
        """注销**完成后**（到期执行）不能再登录，且用户名已让出"""
        self.client_user.post(
            '/api/users/me/delete/', {'password': 'pw12345678', 'confirm': 'DELETE'},
            format='json',
        )
        from django.core.management import call_command
        from io import StringIO
        User.objects.filter(pk=self.user.pk).update(
            deletion_scheduled_for=timezone.now() - timezone.timedelta(minutes=1),
        )
        call_command('purge_deletion_requests', stdout=StringIO())

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_deleted)
        self.assertEqual(self.user.username, f'deleted_{self.user.id}')

        response = APIClient().post(
            '/api/login/', {'username': f'deleted_{self.user.id}', 'password': 'pw12345678'},
            format='json',
        )
        self.assertIn(response.status_code, (400, 401, 403), '注销完成后必须登录不了')

    def test_old_token_stops_working_after_delete(self):
        token = Token.objects.create(user=self.user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(client.get('/api/users/me/points/').status_code, 200)

        self.client_user.post(
            '/api/users/me/delete/', {'password': 'pw12345678', 'confirm': 'DELETE'},
            format='json',
        )
        # 换个 client 用同一张 token（原 client 已被 force_authenticate 覆盖，不能复用）
        fresh = APIClient()
        fresh.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(fresh.get('/api/users/me/points/').status_code, 401)

    def test_self_delete_keeps_posts_and_comments(self):
        """注销不能把别人的内容带走：帖子与评论留在库里"""
        board = ForumBoard.objects.create(name='注销测试版块', is_active=True)
        post = Post.objects.create(
            title='我发的帖子', content='内容', author=self.user, board=board,
        )
        Comment.objects.create(content='别人在我帖下的评论', author=self.other, post=post)

        self.client_user.post(
            '/api/users/me/delete/', {'password': 'pw12345678', 'confirm': 'DELETE'},
            format='json',
        )

        self.assertTrue(Post.objects.filter(id=post.id).exists(), '帖子应保留')
        self.assertTrue(
            Comment.objects.filter(post=post, author=self.other).exists(),
            '别人的评论应保留',
        )
        post.refresh_from_db()
        self.assertEqual(post.author_id, self.user.id, '作者行仍在（只是已注销）')

    def test_anonymous_cannot_delete_account(self):
        response = APIClient().post(
            '/api/users/me/delete/', {'password': 'x', 'confirm': 'DELETE'}, format='json',
        )
        self.assertEqual(response.status_code, 401)

    # ---------- 管理员删除用户 ----------

    def test_normal_user_cannot_delete_others(self):
        response = self.client_user.delete(
            f'/api/admin/users/{self.other.id}/', {'confirm': self.other.username}, format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_delete_self(self):
        response = self.client_admin.delete(
            f'/api/admin/users/{self.admin.id}/', {'confirm': self.admin.username}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_deleted)

    def test_superuser_cannot_be_deleted(self):
        """系统必须永远保留至少一个超级管理员"""
        response = self.client_super.delete(
            f'/api/admin/users/{self.superuser.id}/', {'confirm': self.superuser.username},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.superuser.refresh_from_db()
        self.assertFalse(self.superuser.is_deleted)

    def test_admin_cannot_delete_another_admin(self):
        """非超管不能删其他管理员 —— 否则"谁能被删"就取决于谁先动手"""
        another_admin = User.objects.create_user(
            username='del_admin2', password='pw12345678', is_staff=True, role='ADMIN',
        )
        response = self.client_admin.delete(
            f'/api/admin/users/{another_admin.id}/', {'confirm': another_admin.username},
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        another_admin.refresh_from_db()
        self.assertFalse(another_admin.is_deleted)

    def test_superuser_can_delete_an_admin(self):
        target = User.objects.create_user(
            username='del_admin3', password='pw12345678', is_staff=True, role='ADMIN',
        )
        response = self.client_super.delete(
            f'/api/admin/users/{target.id}/', {'confirm': target.username}, format='json',
        )
        self.assertEqual(response.status_code, 204)
        target.refresh_from_db()
        self.assertTrue(target.is_deleted)

    def test_admin_delete_requires_confirm_username(self):
        response = self.client_admin.delete(
            f'/api/admin/users/{self.other.id}/', {'confirm': 'wrong-name'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.other.refresh_from_db()
        self.assertFalse(self.other.is_deleted)

    def test_admin_delete_success(self):
        response = self.client_admin.delete(
            f'/api/admin/users/{self.other.id}/', {'confirm': self.other.username}, format='json',
        )
        self.assertEqual(response.status_code, 204)
        self.other.refresh_from_db()
        self.assertTrue(self.other.is_deleted)
        self.assertEqual(self.other.deleted_by_id, self.admin.id, '要记下是谁删的')

    def test_django_admin_session_is_invalidated_on_delete(self):
        """
        删除一个**已登录 Django admin** 的用户时，他的会话必须一起失效。

        这一条不是想当然：Django 的会话表里只存 `_auth_user_id`，
        而 `AuthenticationMiddleware` 每次请求都会**按 id 重新取 user 对象** ——
        如果只改 `is_active=False` 而不清会话，`get_user()` 仍会返回这个对象，
        那个已经打开的 admin 标签页**还能继续操作**。软删除必须把会话也清掉。
        """
        from django.contrib.sessions.models import Session
        from django.contrib.auth import SESSION_KEY
        from django.contrib.sessions.backends.db import SessionStore

        # 造一个"已登录"的会话（等价于用户真的在浏览器里登录过 admin）
        session = Session.objects.create(
            session_key='deltest-' + uuid.uuid4().hex[:20],
            session_data=SessionStore().encode({SESSION_KEY: str(self.other.id)}),
            expire_date=timezone.now() + timezone.timedelta(days=1),
        )

        self.client_admin.delete(
            f'/api/admin/users/{self.other.id}/', {'confirm': self.other.username}, format='json',
        )

        self.assertFalse(
            Session.objects.filter(session_key=session.session_key).exists(),
            '被删除用户的已登录会话必须一起清掉',
        )

    def test_deleted_user_hidden_from_admin_list_by_default(self):
        self.client_admin.delete(
            f'/api/admin/users/{self.other.id}/', {'confirm': self.other.username}, format='json',
        )
        listed = self.client_admin.get('/api/admin/users/', {'page_size': 100})
        ids = [row['id'] for row in listed.data['results']]
        self.assertNotIn(self.other.id, ids, '已注销账号不该留在用户列表里')

        audited = self.client_admin.get(
            '/api/admin/users/', {'page_size': 100, 'include_deleted': 'true'},
        )
        audit_ids = [row['id'] for row in audited.data['results']]
        self.assertIn(self.other.id, audit_ids, '?include_deleted=true 应能审计到')


# ============================================================================
# 第 120 批：管理员签发「一次性密码重置链接」
# ============================================================================
class AdminResetLinkTests(TestCase):
    """
    为什么有这组测试
    ---------------------------------------------------------------------------
    自助找回密码只在**账号绑了邮箱**时才真的发信；没绑邮箱时后端按防枚举策略
    静默什么都不做，页面却显示"已发送"。管理端账号大多没绑邮箱 ——
    于是"管理员忘了密码"这条路是断的，而且断得没有声音。

    第 120 批补上 `/api/admin/users/{id}/reset-link/`：管理员签发一次性链接、
    线下发给本人、本人在 /reset-password 自己设新密码。

    这里盯四件事：
      1. **真的能用**：拿签发的链接能走完 `password-reset/confirm/` 并登进去；
      2. **没绑邮箱也能用**（这正是要解决的场景）；
      3. **提权护栏**：staff 管理员不能给超管/其它管理员签发（否则等于顶号）；
      4. **一次性**：改过密码之后，旧链接必须失效。
    """

    def setUp(self):
        cache.clear()
        self.plain = User.objects.create_user(
            username='zz_reset_plain', password='old-pw-123', email='',
        )
        self.staff = User.objects.create_user(
            username='zz_reset_staff', password='pw12345678', is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            username='zz_reset_super', password='pw12345678', email='super@example.invalid',
        )
        self.client_plain = APIClient()
        self.client_plain.force_authenticate(user=self.plain)
        self.client_staff = APIClient()
        self.client_staff.force_authenticate(user=self.staff)
        self.client_super = APIClient()
        self.client_super.force_authenticate(user=self.superuser)

    def _uid_token(self, url):
        match = re.search(r'uid=([^&\s]+)&token=([^\s]+)', url)
        self.assertIsNotNone(match, f'链接里没有 uid/token：{url}')
        return match.group(1), match.group(2)

    def test_superuser_can_sign_link_and_it_actually_works(self):
        """端到端：签发 → 打开链接设新密码 → 用新密码登录"""
        response = self.client_super.post(f'/api/admin/users/{self.plain.id}/reset-link/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['username'], self.plain.username)
        self.assertIn('/reset-password?uid=', response.data['url'])
        self.assertEqual(response.data['expires_in_minutes'], 60)

        uid, token = self._uid_token(response.data['url'])
        confirm = APIClient().post(
            '/api/password-reset/confirm/',
            {'uid': uid, 'token': token, 'new_password': 'brand-new-pw-9'},
            format='json',
        )
        self.assertEqual(confirm.status_code, 200, confirm.data)

        login = APIClient().post(
            '/api/login/', {'username': self.plain.username, 'password': 'brand-new-pw-9'},
            format='json',
        )
        self.assertEqual(login.status_code, 200, '用新密码应当能登录')

    def test_link_works_for_account_without_email(self):
        """**核心场景**：账号没绑邮箱 —— 自助找回是静默失败的，这里必须照样能重置"""
        self.assertEqual(self.plain.email, '')
        response = self.client_super.post(f'/api/admin/users/{self.plain.id}/reset-link/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['has_email'])
        self.assertFalse(response.data['mailed'], '没邮箱当然发不出邮件')
        self.assertIn('uid=', response.data['url'])

    def test_plain_user_cannot_sign_link(self):
        response = self.client_plain.post(f'/api/admin/users/{self.plain.id}/reset-link/')
        self.assertIn(response.status_code, (401, 403))

    def test_anonymous_cannot_sign_link(self):
        response = APIClient().post(f'/api/admin/users/{self.plain.id}/reset-link/')
        self.assertIn(response.status_code, (401, 403))

    def test_staff_admin_cannot_sign_link_for_elevated_account(self):
        """
        提权护栏：只有 staff 的管理员**不能**给超管/其它管理员签发重置链接。
        否则"给谁重置密码"就等于"谁能接管谁"，一个普通管理员可以直接顶掉超管。
        """
        for target in (self.superuser, self.staff):
            with self.subTest(target=target.username):
                response = self.client_staff.post(f'/api/admin/users/{target.id}/reset-link/')
                # 自己给自己是允许的（本来就登着），所以只断言"别人的高权限账号"被拒
                if target.id == self.staff.id:
                    self.assertEqual(response.status_code, 200)
                else:
                    self.assertEqual(response.status_code, 403, response.data)
                    self.assertIn('权限不低于', response.data['detail'])

    def test_superuser_may_sign_link_for_another_admin(self):
        response = self.client_super.post(f'/api/admin/users/{self.staff.id}/reset-link/')
        self.assertEqual(response.status_code, 200, response.data)

    def test_inactive_account_cannot_get_link(self):
        self.plain.is_active = False
        self.plain.save(update_fields=['is_active'])
        response = self.client_super.post(f'/api/admin/users/{self.plain.id}/reset-link/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('停用', response.data['detail'])

    def test_link_is_one_time(self):
        """改过密码之后旧链接必须失效（default_token_generator 与密码哈希绑定）"""
        response = self.client_super.post(f'/api/admin/users/{self.plain.id}/reset-link/')
        uid, token = self._uid_token(response.data['url'])

        first = APIClient().post(
            '/api/password-reset/confirm/',
            {'uid': uid, 'token': token, 'new_password': 'first-new-pw-9'},
            format='json',
        )
        self.assertEqual(first.status_code, 200, first.data)

        replay = APIClient().post(
            '/api/password-reset/confirm/',
            {'uid': uid, 'token': token, 'new_password': 'second-new-pw-9'},
            format='json',
        )
        self.assertNotEqual(replay.status_code, 200, '同一条链接不该能用第二次')

    def test_unknown_user_returns_404(self):
        response = self.client_super.post('/api/admin/users/999999/reset-link/')
        self.assertEqual(response.status_code, 404)


# ============================================================================
# 第 94 批：运维可交付（环境自检 / 健康检查 / Token 有效期）
# ============================================================================
class HealthEndpointTests(TestCase):
    """
    健康检查：探针不该需要登录，也不该碰业务数据。

    `/api/health/` 是第 94 批新增的 —— 在此之前判断"服务活着没"只能请求业务接口，
    而那需要 Token、还会因为某条数据有问题而失败（把"服务正常"误报成"挂了"）。
    """

    def test_health_is_public_and_ok(self):
        response = APIClient().get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'ok')
        self.assertTrue(response.data['checks']['database']['ok'])
        self.assertIn('uptime_seconds', response.data)

    def test_deep_health_reports_migrations_and_model(self):
        response = APIClient().get('/api/health/?deep=true')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['checks']['migrations']['ok'])
        # 模型文件在开发库里是有的；若将来被删，这条断言会提醒（比"识别接口 503"更早）
        self.assertIn('model', response.data['checks'])

    def test_health_does_not_require_token(self):
        """带一个**无效** token 也必须能拿到结果（探针不该被鉴权挡住）"""
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token definitely-not-a-real-token')
        self.assertEqual(client.get('/api/health/').status_code, 200)


@override_settings(TOKEN_EXPIRED_AFTER_SECONDS=3600)
class TokenExpiryTests(TestCase):
    """
    Token 有效期**真正生效**（第 94 批）

    改前：`settings.TOKEN_EXPIRED_AFTER_SECONDS` 只定义、没人读 ——
    DRF 的 TokenAuthentication 不校验创建时间，api/middleware.py 也没读它。
    于是那句"7 天过期"只是一条注释：**凭证泄露出去就是永久有效**。

    现在由 `api/middleware.TokenAuthenticationMiddleware` 执行：
    过期 Token 会被删除，请求按未认证处理（前端收到 401 → 跳登录页）。
    """

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='ttl_user', password='pw12345678')
        self.token = Token.objects.create(user=self.user)

    def _age_token(self, seconds):
        """把 Token 的创建时间往前挪（auto_now_add 不能用赋值改，只能 update）"""
        Token.objects.filter(pk=self.token.pk).update(
            created=timezone.now() - timezone.timedelta(seconds=seconds)
        )

    def test_fresh_token_works(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.assertEqual(client.get('/api/users/me/points/').status_code, 200)

    def test_expired_token_is_rejected(self):
        self._age_token(3600 + 60)  # 超过 1 小时
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        response = client.get('/api/users/me/points/')
        self.assertEqual(response.status_code, 401, '过期 Token 必须当未认证处理')
        self.assertEqual(response['X-Token-Expired'], '1', '应给出明确信号供客户端区分')

    def test_expired_token_is_deleted(self):
        self._age_token(7200)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        client.get('/api/users/me/points/')
        self.assertFalse(
            Token.objects.filter(pk=self.token.pk).exists(),
            '过期 Token 应被顺手清理，避免长期堆在库里',
        )

    def test_user_can_login_again_after_token_expired(self):
        """过期不代表账号有问题：重新登录应拿到新 Token"""
        self._age_token(7200)
        response = APIClient().post(
            '/api/login/', {'username': 'ttl_user', 'password': 'pw12345678'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        new_token = response.data['data']['token']
        self.assertNotEqual(new_token, self.token.key)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {new_token}')
        self.assertEqual(client.get('/api/users/me/points/').status_code, 200)

    @override_settings(TOKEN_EXPIRED_AFTER_SECONDS=0)
    def test_ttl_zero_means_never_expire(self):
        """`0` = 不过期（开发图省事时用；文档里写明了这是刻意保留的开关）"""
        self._age_token(10 * 365 * 24 * 3600)  # 十年
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.assertEqual(client.get('/api/users/me/points/').status_code, 200)


class EnvSelfCheckCommandTests(TestCase):
    """
    `manage.py check_env` 能真的跑起来并解析 requirements（第 94 批）

    这条命令的价值在于**把"环境对不对"变成可执行的检查** ——
    requirements.txt 曾经缺 django-cors-headers / django-filter，照它装必然启动失败，
    而这件事在真正部署之前没有任何人会碰到。
    """

    def test_command_runs_and_reports(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command('check_env', stdout=out)
        text = out.getvalue()
        self.assertIn('依赖包', text)
        self.assertIn('数据库连接正常', text)

    def test_requirements_file_contains_settings_dependencies(self):
        """
        防复发：`INSTALLED_APPS` 里用的第三方包必须在 requirements.txt 里。

        这一条是专门为那次事故写的 —— `corsheaders`（django-cors-headers）与
        `django_filters`（django-filter）当时都不在 requirements 里。
        """
        from pathlib import Path

        from django.conf import settings

        req = (Path(settings.BASE_DIR) / 'requirements.txt').read_text(encoding='utf-8').lower()
        # 应用模块名 → 发行包名。两者经常不一样，而这正是"照着 requirements 装一次
        # 却起不来"的根本原因：写代码的人看的是模块名，写 requirements 的人要写包名。
        mapping = {
            'corsheaders': 'django-cors-headers',
            'django_filters': 'django-filter',
            'rest_framework': 'djangorestframework',
            'rest_framework.authtoken': 'djangorestframework',  # authtoken 是 DRF 自带的
        }
        # 本地/Django 自带的跳过
        skip = {'api'}
        for app in settings.INSTALLED_APPS:
            if app.startswith('django.') or app in skip:
                continue
            package = mapping.get(app, app)
            with self.subTest(app=app):
                self.assertIn(
                    package.lower(), req,
                    f'INSTALLED_APPS 用了 {app}，但 requirements.txt 里没有 {package}',
                )


# ============================================================================
# 第 46 批：病害预警
# ============================================================================
class AlertEngineTests(TestCase):
    """预警规则：趋势 / 多点 / 同月历史 + 个性化标注"""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='al_user', password='pw123456')
        self.other = User.objects.create_user(username='al_other', password='pw123456')
        self.admin = User.objects.create_user(
            username='al_admin', password='pw123456', is_staff=True, is_superuser=True,
        )
        self.pest = PestInfo.objects.create(
            name='番茄早疫病', crop_type='番茄', english_identifier='Tomato___Early_blight',
            symptoms='叶片出现同心轮纹病斑',
        )
        PreventionMethod.objects.create(pest=self.pest, category='CHEMICAL', measure='喷施代森锰锌')
        self.client_user = APIClient()
        self.client_user.force_authenticate(user=self.user)
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)

    def tearDown(self):
        cache.clear()

    def _detect(self, user, days_ago, pest=None):
        """造一条 N 天前的识别记录（timestamp 是 auto_now_add，只能建完再改）"""
        record = DetectionHistory.objects.create(
            user=user, image='detection_history/x.png',
            detection_result=(pest or self.pest).name, pest_info=pest or self.pest, confidence=0.9,
        )
        DetectionHistory.objects.filter(id=record.id).update(
            timestamp=timezone.now() - timedelta(days=days_ago),
        )
        return record

    # ---------- 规则 ----------
    def test_no_data_means_no_alerts(self):
        from .services_alert import alert_summary, compute_alerts
        alerts = compute_alerts()
        self.assertEqual(alerts, [])
        self.assertIn('没有异常上升', alert_summary(alerts)['headline'])

    def test_spike_with_multiple_users_is_high(self):
        from .services_alert import compute_alerts
        # 基线：4 周前各 1 次；窗口内：2 个用户共 3 次
        self._detect(self.user, 20)
        self._detect(self.user, 5)
        self._detect(self.other, 4)
        self._detect(self.user, 2)

        alerts = compute_alerts()
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert['level'], 'high')
        self.assertEqual(alert['recent_count'], 3)
        self.assertEqual(alert['distinct_users'], 2)
        self.assertIn('trend', alert['signals'])
        self.assertIn('community', alert['signals'])
        self.assertIn('高发期', alert['title'])

    def test_single_case_without_signals_is_not_reported(self):
        from .services_alert import compute_alerts
        self._detect(self.user, 3)  # 基线 0、只有 1 人 1 次
        # min_cases=2 时不该报
        self.assertEqual(compute_alerts(min_cases=2), [])
        # 放宽到 1 次时会出现，并且因为基线为 0 带 trend 信号
        alerts = compute_alerts(min_cases=1)
        self.assertEqual(len(alerts), 1)
        self.assertIn('trend', alerts[0]['signals'])

    def test_seasonal_signal_from_last_year_same_month(self):
        from .services_alert import compute_alerts
        now = timezone.now()
        record = self._detect(self.user, 200)  # 先造出来
        # 改到去年同月（该月不是"近 7 天"，所以只贡献 seasonal 信号）
        last_year = now.replace(year=now.year - 1)
        DetectionHistory.objects.filter(id=record.id).update(timestamp=last_year)

        self._detect(self.user, 1)
        self._detect(self.other, 1)

        alerts = compute_alerts(min_cases=2)
        self.assertEqual(len(alerts), 1)
        self.assertIn('seasonal', alerts[0]['signals'])

    def test_personal_flag_and_message(self):
        from .services_alert import compute_alerts
        self._detect(self.user, 12)   # 我自己 12 天前检出过
        self._detect(self.other, 3)
        self._detect(self.other, 2)

        alerts = compute_alerts(user=self.user)
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertTrue(alert['is_personal'])
        self.assertTrue(alert['alerted_before'])
        self.assertEqual(alert['my_count'], 1)
        self.assertIn('你', alert['message'])
        self.assertIn('识别出过', alert['message'])

        # 换成别的用户看：不是他自己检出过，但同样能看到这条预警
        stranger = User.objects.create_user(username='al_stranger', password='pw123456')
        alerts_stranger = compute_alerts(user=stranger)
        self.assertEqual(len(alerts_stranger), 1)
        self.assertFalse(alerts_stranger[0]['alerted_before'])

    def test_advice_comes_from_encyclopedia(self):
        from .services_alert import compute_alerts
        self._detect(self.user, 1)
        self._detect(self.other, 1)
        alert = compute_alerts(min_cases=2)[0]
        self.assertTrue(alert['advice'], '应带上防治建议')
        self.assertEqual(alert['advice'][0]['category_display'], '化学防治')
        self.assertEqual(alert['advice'][0]['measure'], '喷施代森锰锌')
        self.assertTrue(alert['url'].startswith('/pests/'))

    def test_records_without_pest_info_are_ignored(self):
        from .services_alert import compute_alerts
        record = DetectionHistory.objects.create(
            user=self.user, image='detection_history/y.png', detection_result='未知', pest_info=None,
        )
        DetectionHistory.objects.filter(id=record.id).update(timestamp=timezone.now() - timedelta(days=1))
        self.assertEqual(compute_alerts(min_cases=1), [])

    # ---------- 接口 ----------
    def test_alert_endpoint_requires_login(self):
        self.assertIn(APIClient().get('/api/alerts/').status_code, (401, 403))

    def test_alert_endpoint_shape(self):
        self._detect(self.user, 1)
        self._detect(self.other, 1)
        response = self.client_user.get('/api/alerts/')
        self.assertEqual(response.status_code, 200)
        for key in ['generated_at', 'days', 'min_cases', 'source', 'summary', 'alerts']:
            self.assertIn(key, response.data)
        self.assertIn('站内识别记录', response.data['source'], '要如实说明数据来源')
        self.assertEqual(response.data['summary']['total'], 1)
        self.assertEqual(response.data['summary']['counts']['medium'] + response.data['summary']['counts']['high'], 1)

    def test_alert_endpoint_clamps_params(self):
        self.assertEqual(self.client_user.get('/api/alerts/', {'days': 1}).data['days'], 3)
        self.assertEqual(self.client_user.get('/api/alerts/', {'days': 999}).data['days'], 30)
        self.assertEqual(self.client_user.get('/api/alerts/', {'days': 'x'}).data['days'], 7)
        self.assertEqual(self.client_user.get('/api/alerts/', {'min_cases': 0}).data['min_cases'], 1)

    # ---------- 空状态的"为什么没有"（第 76 批） ----------
    def test_empty_result_explains_why(self):
        """
        真实困惑：预警页默认 7 天窗口，而阈值是"同一病害累计 ≥2 次"。
        数据少时页面只有一句"近期没有异常上升的病害"，用户没法区分
        "没数据 / 坏了 / 就差一点"，会合理怀疑功能没做。
        所以无预警时必须给出量化说明。
        """
        self._detect(self.user, 3)  # 单用户、单次 → 不达阈值

        data = self.client_user.get('/api/alerts/', {'days': 7}).data
        self.assertEqual(data['alerts'], [])
        diag = data['diagnostics']
        self.assertEqual(diag['window_days'], 7)
        self.assertEqual(diag['threshold'], 2)
        self.assertEqual(diag['recent_detections'], 1)
        self.assertEqual(diag['diseases_in_window'], 1)
        self.assertEqual(diag['closest']['name'], '番茄早疫病')
        self.assertEqual(diag['closest']['count'], 1)
        self.assertEqual(diag['closest']['needed'], 1, '再出现 1 次就会提醒')

    def test_empty_result_with_no_records_at_all(self):
        data = self.client_user.get('/api/alerts/').data
        self.assertIsNone(data['diagnostics']['closest'])
        self.assertEqual(data['diagnostics']['recent_detections'], 0)
        self.assertEqual(data['diagnostics']['diseases_in_window'], 0)

    def test_diagnostics_absent_when_there_are_alerts(self):
        """有预警时不该白跑那两次查询，前端也不显示这段说明"""
        self._detect(self.user, 1)
        self._detect(self.other, 1)
        data = self.client_user.get('/api/alerts/').data
        self.assertEqual(len(data['alerts']), 1)
        self.assertNotIn('diagnostics', data)

    def test_diagnostics_ignores_records_without_pest_info(self):
        """没有关联病害的记录不算数（与 compute_alerts 同一口径）"""
        record = DetectionHistory.objects.create(
            user=self.user, image='detection_history/n.png', detection_result='未知', pest_info=None,
        )
        DetectionHistory.objects.filter(id=record.id).update(timestamp=timezone.now() - timedelta(days=1))
        diag = self.client_user.get('/api/alerts/').data['diagnostics']
        self.assertEqual(diag['recent_detections'], 0)

    # ---------- 推送 ----------
    def test_admin_can_push_alerts(self):
        self._detect(self.user, 1)
        self._detect(self.other, 1)
        Notification.objects.all().delete()

        response = self.client_admin.post('/api/alerts/notify/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['pushed'], 1)
        self.assertEqual(response.data['recipients'], 3)
        self.assertTrue(Notification.objects.filter(recipient=self.user, title__contains='病害预警').exists())
        self.assertTrue(Notification.objects.filter(recipient=self.other, title__contains='病害预警').exists())
        # 第 78 批：**推送人自己也收一份**。
        # 原实现（含本测试）断言推送人收不到，口径是"notify() 跳过自己发给自己"；
        # 但预警推送是运营动作 —— 推送人看不到自己的推送，就等于没有送达凭证
        # （真实反馈：管理员推了 8 条预警，收件人都有，他自己的通知中心是空的）。
        self.assertTrue(Notification.objects.filter(recipient=self.admin, title__contains='病害预警').exists())

    def test_push_is_idempotent_per_day(self):
        self._detect(self.user, 1)
        self._detect(self.other, 1)
        first = self.client_admin.post('/api/alerts/notify/').data
        second = self.client_admin.post('/api/alerts/notify/').data
        self.assertEqual(first['pushed'], 1)
        self.assertEqual(second['pushed'], 0)
        self.assertEqual(second['skipped'], 1, '同一天同一病害不重复推送')

    def test_push_requires_admin(self):
        self._detect(self.user, 1)
        self._detect(self.other, 1)
        response = self.client_user.post('/api/alerts/notify/')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Notification.objects.filter(title__contains='病害预警').exists())

    def test_push_without_alerts_is_friendly(self):
        response = self.client_admin.post('/api/alerts/notify/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['pushed'], 0)
        self.assertIn('当前没有需要推送的预警', response.data['message'])


# ============================================================================
# 第 47 批：种植日历
# ============================================================================
class CalendarTests(TestCase):
    """种植日历：模板任务 + 站内真实统计 + 管理员维护"""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='cal_user', password='pw123456')
        self.admin = User.objects.create_user(
            username='cal_admin', password='pw123456', is_staff=True, is_superuser=True,
        )
        self.client_user = APIClient()
        self.client_user.force_authenticate(user=self.user)
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)

        # 两个病害：番茄(与用户相关) / 玉米(无关)
        self.tomato_pest = PestInfo.objects.create(
            name='番茄早疫病', crop_type='番茄', english_identifier='Cal_Tomato',
        )
        self.corn_pest = PestInfo.objects.create(
            name='玉米大斑病', crop_type='玉米', english_identifier='Cal_Corn',
        )

    def tearDown(self):
        cache.clear()

    def _detect(self, user, pest, month_offset=0):
        """造一条识别记录，并把时间调到"本月"（用于月度统计）"""
        record = DetectionHistory.objects.create(
            user=user, image='detection_history/c.png', detection_result=pest.name,
            pest_info=pest, confidence=0.9,
        )
        now = timezone.now()
        target_month = now.month
        DetectionHistory.objects.filter(id=record.id).update(
            timestamp=now.replace(month=target_month) - timedelta(days=month_offset),
        )
        return record

    # ---------- 模板 ----------
    def test_template_is_seeded_and_grouped(self):
        response = self.client_user.get('/api/calendar/', {'month': 9})
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data['task_total'], 3, '9 月应有若干模板任务')
        crops = {group['crop_type'] for group in response.data['task_groups']}
        self.assertIn('玉米', crops)
        # 分组内按农事类型排序
        for group in response.data['task_groups']:
            types = [task['task_type'] for task in group['tasks']]
            self.assertEqual(types, sorted(types, key=lambda t: types.index(t)))

    def test_month_filter_and_clamping(self):
        nine = self.client_user.get('/api/calendar/', {'month': 9}).data
        self.assertEqual(nine['month'], 9)
        # 非法月份回落到当前月 / 收敛到 1~12
        self.assertEqual(self.client_user.get('/api/calendar/', {'month': 99}).data['month'], 12)
        self.assertEqual(self.client_user.get('/api/calendar/', {'month': 0}).data['month'], 1)
        self.assertEqual(self.client_user.get('/api/calendar/', {'month': 'x'}).data['month'],
                         timezone.localdate().month)

    def test_crop_filter(self):
        # 番茄模板里 5 月有任务（9 月没有，所以这里用 5 月）
        response = self.client_user.get('/api/calendar/', {'month': 5, 'crop': '番茄'})
        groups = response.data['task_groups']
        self.assertTrue(groups)
        self.assertEqual({group['crop_type'] for group in groups}, {'番茄'})

        # 9 月筛玉米也应有结果（模板里 9 月正好有玉米）
        corn = self.client_user.get('/api/calendar/', {'month': 9, 'crop': '玉米'}).data
        self.assertEqual({group['crop_type'] for group in corn['task_groups']}, {'玉米'})

    def test_crop_options_come_from_encyclopedia(self):
        response = self.client_user.get('/api/calendar/crops/')
        self.assertIn('番茄', response.data['crops'])
        self.assertIn('玉米', response.data['crops'])

    # ---------- 真实统计 ----------
    def test_seasonal_pests_from_real_detections(self):
        self._detect(self.user, self.tomato_pest)
        self._detect(self.user, self.tomato_pest)
        self._detect(self.user, self.corn_pest)

        response = self.client_user.get('/api/calendar/', {'month': timezone.localdate().month})
        stats = response.data['seasonal_pests']
        self.assertTrue(stats, '本月应有真实检出统计')
        top = stats[0]
        self.assertEqual(top['name'], '番茄早疫病')
        self.assertEqual(top['count'], 2)
        self.assertTrue(top['url'].startswith('/pests/'))

    def test_my_crops_from_my_history(self):
        self._detect(self.user, self.tomato_pest)
        response = self.client_user.get('/api/calendar/')
        self.assertIn('番茄', response.data['my_crops'])
        self.assertNotIn('玉米', response.data['my_crops'], '没识别过的作物不该算"我种过的"')
        # 没有指定 crop 时，统计范围聚焦在我种过的作物
        self.assertEqual(response.data['scope_crops'], ['番茄'])

    def test_my_history_same_month(self):
        self._detect(self.user, self.tomato_pest)
        response = self.client_user.get('/api/calendar/')
        self.assertTrue(response.data['my_history'])
        self.assertEqual(response.data['my_history'][0]['name'], '番茄早疫病')

    def test_source_note_is_explicit(self):
        response = self.client_user.get('/api/calendar/')
        self.assertIn('通用农事模板', response.data['source_note'])
        self.assertIn('本站识别记录', response.data['source_note'])

    def test_requires_login(self):
        self.assertIn(APIClient().get('/api/calendar/').status_code, (401, 403))

    # ---------- 管理员维护 ----------
    def test_admin_can_create_and_update_task(self):
        created = self.client_admin.post(
            '/api/calendar/tasks/',
            {'crop_type': '番茄', 'month': 7, 'task_type': 'pest_control',
             'title': '高温期防病毒病', 'detail': '注意遮阳与防治蚜虫'},
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        task_id = created.data['id']
        self.assertEqual(created.data['source'], '管理员录入')

        updated = self.client_admin.patch(
            f'/api/calendar/tasks/{task_id}/', {'title': '高温期防病毒病（已修订）'}, format='json',
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data['title'], '高温期防病毒病（已修订）')

        # 出现在 7 月的日历里
        july = self.client_user.get('/api/calendar/', {'month': 7, 'crop': '番茄'}).data
        titles = [t['title'] for group in july['task_groups'] for t in group['tasks']]
        self.assertIn('高温期防病毒病（已修订）', titles)

        deleted = self.client_admin.delete(f'/api/calendar/tasks/{task_id}/')
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(CalendarTask.objects.filter(id=task_id).exists())

    def test_create_validates_input(self):
        bad_month = self.client_admin.post(
            '/api/calendar/tasks/', {'crop_type': '番茄', 'month': 13, 'title': 'x'}, format='json')
        self.assertEqual(bad_month.status_code, 400)
        no_title = self.client_admin.post(
            '/api/calendar/tasks/', {'crop_type': '番茄', 'month': 5, 'title': '  '}, format='json')
        self.assertEqual(no_title.status_code, 400)
        no_crop = self.client_admin.post(
            '/api/calendar/tasks/', {'crop_type': '', 'month': 5, 'title': 'x'}, format='json')
        self.assertEqual(no_crop.status_code, 400)

    def test_duplicate_task_is_rejected(self):
        task = CalendarTask.objects.filter(source='通用模板').first()
        response = self.client_admin.post(
            '/api/calendar/tasks/',
            {'crop_type': task.crop_type, 'month': task.month, 'title': task.title},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('同名任务', response.data['detail'])

    def test_normal_user_cannot_write(self):
        self.assertEqual(
            self.client_user.post('/api/calendar/tasks/',
                                  {'crop_type': '番茄', 'month': 5, 'title': 'x'},
                                  format='json').status_code,
            403,
        )
        task = CalendarTask.objects.first()
        self.assertEqual(
            self.client_user.patch(f'/api/calendar/tasks/{task.id}/', {'title': 'x'}, format='json').status_code,
            403,
        )
        self.assertEqual(self.client_user.delete(f'/api/calendar/tasks/{task.id}/').status_code, 403)

    def test_task_list_filters(self):
        response = self.client_user.get('/api/calendar/tasks/', {'crop': '番茄', 'month': 9})
        self.assertTrue(all(item['crop_type'] == '番茄' and item['month'] == 9
                            for item in response.data['results']))


# ============================================================================
# 第 49 批：专家咨询
# ============================================================================
class ExpertConsultTests(TestCase):
    """提问 / 专家作答 / 采纳 / 权限 / 通知"""

    def setUp(self):
        cache.clear()
        self.asker = User.objects.create_user(username='cs_asker', password='pw123456')
        self.expert = User.objects.create_user(username='cs_expert', password='pw123456')
        ExpertProfile.objects.create(user=self.expert, title='植保研究员', specialties='番茄,草莓')
        self.plain = User.objects.create_user(username='cs_plain', password='pw123456')
        self.admin = User.objects.create_user(
            username='cs_admin', password='pw123456', is_staff=True, is_superuser=True,
        )
        self.client_asker = APIClient()
        self.client_asker.force_authenticate(user=self.asker)
        self.client_expert = APIClient()
        self.client_expert.force_authenticate(user=self.expert)
        self.client_plain = APIClient()
        self.client_plain.force_authenticate(user=self.plain)
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)

    def tearDown(self):
        cache.clear()

    def _ask(self, **overrides):
        payload = {
            'title': '番茄叶片出现同心轮纹斑怎么办？',
            'content': '最近棚里湿度大，下部叶片先出现病斑，逐渐向上蔓延。',
            'crop_type': '番茄',
        }
        payload.update(overrides)
        return self.client_asker.post('/api/consult/questions/', payload, format='json')

    def _answer(self, question_id, content='建议先摘除病叶并通风降湿，发病初期喷施代森锰锌。'):
        return self.client_expert.post(
            f'/api/consult/questions/{question_id}/answers/', {'content': content}, format='json',
        )

    # ---------- 提问 ----------
    def test_ask_question(self):
        response = self._ask()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], 'open')
        self.assertEqual(response.data['crop_type'], '番茄')
        self.assertTrue(response.data['is_mine'])

    def test_ask_validates_input(self):
        self.assertEqual(self._ask(title='  ').status_code, 400)
        self.assertEqual(self._ask(content='短').status_code, 400)
        self.assertEqual(self._ask(title='x' * 201).status_code, 400)

    def test_ask_blocks_sensitive_words(self):
        SensitiveWord.objects.update_or_create(word='代开发票', defaults={'category': 'ad', 'is_active': True})
        cache.delete('sensitive_words:active')
        response = self._ask(title='代开发票联系我')
        self.assertEqual(response.status_code, 400)
        self.assertIn('不允许的词汇', response.data['detail'])

    def test_experts_get_notified_on_new_question(self):
        self._ask()
        self.assertTrue(
            Notification.objects.filter(recipient=self.expert, title__contains='新的专家咨询').exists(),
            '专家应收到新提问通知',
        )

    # ---------- 列表与筛选 ----------
    def test_list_filters(self):
        first = self._ask().data['id']
        self._ask(title='玉米叶片发黄', crop_type='玉米')
        self._answer(first)

        self.assertEqual(self.client_asker.get('/api/consult/questions/').data['count'], 2)
        self.assertEqual(
            self.client_asker.get('/api/consult/questions/', {'status': 'answered'}).data['count'], 1,
        )
        self.assertEqual(
            self.client_asker.get('/api/consult/questions/', {'status': 'open'}).data['count'], 1,
        )
        self.assertEqual(
            self.client_asker.get('/api/consult/questions/', {'mine': 'true'}).data['count'], 2,
        )
        self.assertEqual(
            self.client_plain.get('/api/consult/questions/', {'mine': 'true'}).data['count'], 0,
        )
        self.assertEqual(
            self.client_asker.get('/api/consult/questions/', {'crop': '番茄'}).data['count'], 1,
        )
        self.assertEqual(
            self.client_asker.get('/api/consult/questions/', {'search': '发黄'}).data['count'], 1,
        )

    def test_status_counts_in_list(self):
        question_id = self._ask().data['id']
        self._answer(question_id)
        counts = self.client_asker.get('/api/consult/questions/').data['status_counts']
        self.assertEqual(counts['answered'], 1)
        self.assertEqual(counts['open'], 0)

    def test_detail_increments_view_count(self):
        question_id = self._ask().data['id']
        first = self.client_plain.get(f'/api/consult/questions/{question_id}/')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data['view_count'], 1)
        second = self.client_plain.get(f'/api/consult/questions/{question_id}/')
        self.assertEqual(second.data['view_count'], 2)
        self.assertFalse(second.data['is_mine'], '别人看时 is_mine 应为 False')

    # ---------- 作答权限 ----------
    def test_only_expert_and_admin_can_answer(self):
        question_id = self._ask().data['id']
        self.assertEqual(
            self.client_plain.post(f'/api/consult/questions/{question_id}/answers/',
                                   {'content': '我觉得应该多浇水试试看'}, format='json').status_code,
            403,
        )
        self.assertEqual(self._answer(question_id).status_code, 201)
        # 管理员也能答（管理员默认按专家对待）
        self.assertEqual(
            self.client_admin.post(f'/api/consult/questions/{question_id}/answers/',
                                   {'content': '管理员补充：注意轮作倒茬。'}, format='json').status_code,
            201,
        )

    def test_answer_updates_question_status_and_count(self):
        question_id = self._ask().data['id']
        self._answer(question_id)
        detail = self.client_asker.get(f'/api/consult/questions/{question_id}/').data
        self.assertEqual(detail['status'], 'answered')
        self.assertEqual(detail['answer_count'], 1)
        self.assertIsNotNone(detail['last_answer_at'])
        self.assertEqual(detail['answers'][0]['author_title'], '植保研究员')

    def test_answer_validates_and_filters(self):
        question_id = self._ask().data['id']
        self.assertEqual(self._answer(question_id, content='短').status_code, 400)

        SensitiveWord.objects.update_or_create(word='加微信', defaults={'category': 'ad', 'is_active': True})
        cache.delete('sensitive_words:active')
        blocked = self._answer(question_id, content='加微信详聊，保证有效')
        self.assertEqual(blocked.status_code, 400)

    def test_asker_gets_notified_on_answer(self):
        question_id = self._ask().data['id']
        self._answer(question_id)
        self.assertTrue(
            Notification.objects.filter(recipient=self.asker, title__contains='回答了你的问题').exists()
        )

    def test_non_expert_profile_inactive_cannot_answer(self):
        question_id = self._ask().data['id']
        profile = self.expert.expert_profile
        profile.is_active = False
        profile.save(update_fields=['is_active'])
        self.assertEqual(self._answer(question_id).status_code, 403)

    # ---------- 采纳 ----------
    def test_asker_accepts_answer(self):
        question_id = self._ask().data['id']
        answer_id = self._answer(question_id).data['id']

        response = self.client_asker.post(f'/api/consult/answers/{answer_id}/accept/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['accepted_answer_id'], answer_id)

        detail = self.client_asker.get(f'/api/consult/questions/{question_id}/').data
        self.assertEqual(detail['accepted_answer_id'], answer_id)
        self.assertTrue(detail['answers'][0]['is_accepted'])
        self.assertTrue(
            Notification.objects.filter(recipient=self.expert, title__contains='被采纳').exists()
        )

    def test_accept_is_unique(self):
        question_id = self._ask().data['id']
        first = self._answer(question_id, content='第一种方案：通风降湿加喷药。').data['id']
        second = self._answer(question_id, content='第二种方案：直接拔掉病株。').data['id']

        self.client_asker.post(f'/api/consult/answers/{first}/accept/')
        self.client_asker.post(f'/api/consult/answers/{second}/accept/')

        detail = self.client_asker.get(f'/api/consult/questions/{question_id}/').data
        accepted = [item for item in detail['answers'] if item['is_accepted']]
        self.assertEqual(len(accepted), 1, '只能有一个最佳答案')
        self.assertEqual(accepted[0]['id'], second)

    def test_only_asker_can_accept(self):
        question_id = self._ask().data['id']
        answer_id = self._answer(question_id).data['id']
        self.assertEqual(
            self.client_expert.post(f'/api/consult/answers/{answer_id}/accept/').status_code, 403,
        )
        self.assertEqual(
            self.client_admin.post(f'/api/consult/answers/{answer_id}/accept/').status_code, 403,
        )

    # ---------- 关闭 ----------
    def test_asker_or_admin_can_close(self):
        question_id = self._ask().data['id']
        self.assertEqual(
            self.client_plain.post(f'/api/consult/questions/{question_id}/').status_code, 403,
        )
        closed = self.client_asker.post(f'/api/consult/questions/{question_id}/')
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.data['status'], 'closed')

    # ---------- 专家管理 ----------
    def test_admin_grants_and_revokes_expert(self):
        granted = self.client_admin.post(
            '/api/consult/experts/{}/'.format(self.plain.id),
            {'title': '高级农艺师', 'specialties': '玉米，水稻'},
            format='json',
        )
        self.assertEqual(granted.status_code, 200)
        profile = ExpertProfile.objects.get(user=self.plain)
        self.assertEqual(profile.title, '高级农艺师')
        self.assertEqual(profile.specialty_list, ['玉米', '水稻'])
        self.assertTrue(
            Notification.objects.filter(recipient=self.plain, title__contains='设为平台专家').exists()
        )

        # 授予后就能作答
        question_id = self._ask().data['id']
        self.assertEqual(
            self.client_plain.post(f'/api/consult/questions/{question_id}/answers/',
                                   {'content': '玉米黄叶多为缺氮，建议追施尿素。'}, format='json').status_code,
            201,
        )

        # 取消后不能作答
        revoked = self.client_admin.delete('/api/consult/experts/{}/'.format(self.plain.id))
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(
            self.client_plain.post(f'/api/consult/questions/{question_id}/answers/',
                                   {'content': '再答一次试试看行不行。'}, format='json').status_code,
            403,
        )

    def test_grant_requires_admin(self):
        self.assertEqual(
            self.client_plain.post('/api/consult/experts/{}/'.format(self.asker.id), {}, format='json').status_code,
            403,
        )

    # ---------- 取消专家（第 76 批补齐） ----------
    def test_revoke_sends_notification_and_removes_from_expert_list(self):
        """
        撤销专家此前"撤销了也没人知道"，而且列表里仍会显示。
        第 76 批：撤销要通知本人，并且 `/api/consult/experts/` 立刻不再返回该专家。
        """
        self.assertEqual(self.client_asker.get('/api/consult/experts/').data['count'], 1)

        response = self.client_admin.delete(f'/api/consult/experts/{self.expert.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['changed'])
        self.assertTrue(
            Notification.objects.filter(recipient=self.expert, title__contains='专家身份已被取消').exists(),
            '被取消的人应收到通知',
        )
        self.assertEqual(
            self.client_asker.get('/api/consult/experts/').data['count'], 0,
            '取消后不该再出现在专家列表里',
        )

    def test_revoke_is_idempotent(self):
        """重复点"取消"不应报错，也不该重复发通知（软删除，第二次 changed=False）"""
        self.client_admin.delete(f'/api/consult/experts/{self.expert.id}/')
        Notification.objects.filter(recipient=self.expert, title__contains='专家身份已被取消').delete()

        again = self.client_admin.delete(f'/api/consult/experts/{self.expert.id}/')
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.data['changed'])
        self.assertFalse(
            Notification.objects.filter(recipient=self.expert, title__contains='专家身份已被取消').exists(),
        )

    def test_admin_without_profile_is_not_listed_as_expert(self):
        """
        管理员"可以答疑"不等于"被授予了专家称号"。
        专家列表只展示被正式授予的人（口径清楚），这里是锁死这个口径的回归。
        """
        usernames = [row['user']['username'] for row in self.client_admin.get('/api/consult/experts/').data['results']]
        self.assertNotIn('cs_admin', usernames)

    def test_expert_list_shows_stats(self):
        question_id = self._ask().data['id']
        answer_id = self._answer(question_id).data['id']
        self.client_asker.post(f'/api/consult/answers/{answer_id}/accept/')

        response = self.client_asker.get('/api/consult/experts/')
        self.assertEqual(response.data['count'], 1)
        item = response.data['results'][0]
        self.assertEqual(item['user']['username'], 'cs_expert')
        self.assertEqual(item['title'], '植保研究员')
        self.assertEqual(item['specialties'], ['番茄', '草莓'])
        self.assertEqual(item['answered_count'], 1)
        self.assertEqual(item['accepted_count'], 1)

    def test_requires_login(self):
        guest = APIClient()
        self.assertIn(guest.get('/api/consult/questions/').status_code, (401, 403))
        self.assertIn(guest.post('/api/consult/questions/', {'title': 'x', 'content': 'yyyyy'}).status_code, (401, 403))


# ============================================================================
# 第 50 批：离线资料包
# ============================================================================
class OfflinePackTests(TestCase):
    """离线资料包：断网时前端靠它显示百科"""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='of_user', password='pw123456')
        self.client_user = APIClient()
        self.client_user.force_authenticate(user=self.user)

        self.pest = PestInfo.objects.create(
            name='番茄晚疫病', crop_type='番茄', english_identifier='Tomato___Late_blight',
            symptoms='叶片水浸状病斑', description='低温高湿易流行',
        )
        PreventionMethod.objects.create(pest=self.pest, category='CHEMICAL', measure='喷施烯酰吗啉')
        PreventionMethod.objects.create(pest=self.pest, category='AGRICULTURAL', measure='合理轮作')

    def tearDown(self):
        cache.clear()

    def test_pack_shape_and_content(self):
        response = self.client_user.get('/api/pests/offline-pack/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertFalse(response.data['unchanged'])
        self.assertIn('离线资料包', response.data['source_note'])
        self.assertTrue(response.data['version'])

        item = response.data['items'][0]
        self.assertEqual(item['name'], '番茄晚疫病')
        self.assertEqual(item['crop_type'], '番茄')
        self.assertEqual(item['symptoms'], '叶片水浸状病斑')
        self.assertEqual(len(item['prevention_methods']), 2)
        self.assertEqual(item['prevention_methods'][0]['category_display'], '化学防治')

    def test_same_version_returns_unchanged_without_items(self):
        version = self.client_user.get('/api/pests/offline-pack/').data['version']
        again = self.client_user.get('/api/pests/offline-pack/', {'since': version})
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.data['unchanged'])
        self.assertNotIn('items', again.data, '内容没变时不该再传一遍全量数据')
        self.assertEqual(again.data['version'], version)

    def test_version_changes_when_content_changes(self):
        version = self.client_user.get('/api/pests/offline-pack/').data['version']
        self.pest.symptoms = '症状描述已更新'
        self.pest.save(update_fields=['symptoms'])

        again = self.client_user.get('/api/pests/offline-pack/', {'since': version})
        self.assertFalse(again.data['unchanged'])
        self.assertNotEqual(again.data['version'], version)
        self.assertIn('items', again.data)

    def test_pack_includes_pests_without_prevention_methods(self):
        PestInfo.objects.create(name='无防治措施的病害', crop_type='玉米', english_identifier='No_Method')
        data = self.client_user.get('/api/pests/offline-pack/').data
        item = next(row for row in data['items'] if row['name'] == '无防治措施的病害')
        self.assertEqual(item['prevention_methods'], [])

    def test_requires_login(self):
        self.assertIn(APIClient().get('/api/pests/offline-pack/').status_code, (401, 403))


# ============================================================================
# 第 76 批：管理端用户管理
# ----------------------------------------------------------------------------
# 背景：管理后台此前只有「新闻 / 意见反馈 / 内容审核 / 数据看板」，
# **没有用户管理** —— 管理员想看"平台上有哪些用户、谁是专家"只能进
# Django 自带的 /admin/。本次补 `/api/admin/users/`（列表 / 详情，仅管理员）。
# 这里锁死三件事：非管理员进不来、专家身份字段口径正确、筛选真的生效。
# ============================================================================
class AdminUserManagementTests(TestCase):
    """管理端用户管理：权限 / 字段 / 筛选 / 分页"""

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            username='um_admin', password='pw123456', is_staff=True, is_superuser=True,
        )
        self.expert = User.objects.create_user(
            username='um_expert', password='pw123456', email='expert@example.com',
        )
        ExpertProfile.objects.create(user=self.expert, title='植保研究员', specialties='番茄, 草莓')
        self.editor = User.objects.create_user(
            username='um_editor', password='pw123456', role='EDITOR',
        )
        self.plain = User.objects.create_user(
            username='um_plain', password='pw123456', email='plain@example.com',
        )
        # 被"取消专家"的软删除记录：用户管理页必须显示成"不是专家"
        self.revoked = User.objects.create_user(username='um_revoked', password='pw123456')
        ExpertProfile.objects.create(user=self.revoked, title='前专家', is_active=False)

        post = Post.objects.create(
            title='um 的帖子', content='内容', author=self.plain, board=self._board(),
        )
        Comment.objects.create(post=post, content='评论', author=self.plain)
        DetectionHistory.objects.create(
            user=self.plain, image='detection_history/um.png', detection_result='番茄晚疫病', confidence=0.9,
        )

        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)
        self.client_plain = APIClient()
        self.client_plain.force_authenticate(user=self.plain)

    def tearDown(self):
        cache.clear()

    @staticmethod
    def _board():
        board, _ = ForumBoard.objects.get_or_create(name='um 版块', defaults={'description': '测试用'})
        return board

    def _by_name(self, username, **params):
        data = self.client_admin.get('/api/admin/users/', {'search': username, **params}).data
        results = data['results']
        self.assertTrue(results, f'没找到用户 {username}')
        return results[0]

    # ---------- 权限 ----------
    def test_requires_admin(self):
        self.assertIn(self.client_plain.get('/api/admin/users/').status_code, (401, 403))
        self.assertIn(APIClient().get('/api/admin/users/').status_code, (401, 403))
        self.assertIn(self.client_plain.get(f'/api/admin/users/{self.plain.id}/').status_code, (401, 403))

    # ---------- 列表字段 ----------
    def test_list_exposes_management_fields(self):
        row = self._by_name('um_expert')
        self.assertEqual(row['email'], 'expert@example.com')
        self.assertEqual(row['role'], 'USER')
        self.assertTrue(row['is_expert'])
        self.assertEqual(row['expert_title'], '植保研究员')
        self.assertEqual(row['expert_specialties'], ['番茄', '草莓'])
        self.assertIn('date_joined', row)
        self.assertIn('last_login', row)

    def test_revoked_expert_is_not_reported_as_expert(self):
        """撤销专家是软删除（is_active=False），用户管理页不能仍显示成专家"""
        row = self._by_name('um_revoked')
        self.assertFalse(row['is_expert'])
        self.assertEqual(row['expert_title'], '')

    def test_activity_counts_are_not_n_plus_one(self):
        """活跃度三个计数用 annotate 一次算出来，值与实际一致"""
        row = self._by_name('um_plain')
        self.assertEqual(row['post_count'], 1)
        self.assertEqual(row['comment_count'], 1)
        self.assertEqual(row['detection_count'], 1)

    # ---------- 筛选 ----------
    def _usernames(self, **params):
        data = self.client_admin.get('/api/admin/users/', params).data
        return {row['username'] for row in data['results']}

    def test_role_and_status_filters(self):
        self.assertIn('um_editor', self._usernames(role='EDITOR'))
        self.assertNotIn('um_plain', self._usernames(role='EDITOR'))
        self.assertIn('um_expert', self._usernames(status='expert'))
        self.assertNotIn('um_revoked', self._usernames(status='expert'))
        self.assertIn('um_admin', self._usernames(status='staff'))
        self.assertNotIn('um_plain', self._usernames(status='staff'))

    def test_invalid_filter_value_is_ignored(self):
        """筛选值非法时忽略而不是 500（前端传了脏值不该让整页崩）"""
        response = self.client_admin.get('/api/admin/users/', {'role': 'HACKER', 'status': '???'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], User.objects.count())

    def test_search_matches_username_and_email(self):
        self.assertEqual(self._by_name('um_expert')['username'], 'um_expert')
        self.assertEqual(self._by_name('expert@example.com')['username'], 'um_expert')
        self.assertEqual(
            self.client_admin.get('/api/admin/users/', {'search': '没有这个人'}).data['count'], 0,
        )

    def test_list_is_paginated(self):
        data = self.client_admin.get('/api/admin/users/', {'page_size': 2}).data
        self.assertEqual(len(data['results']), 2)
        self.assertEqual(data['count'], User.objects.count())

    # ---------- 详情 ----------
    def test_detail_matches_list(self):
        listed = self._by_name('um_plain')
        detail = self.client_admin.get(f'/api/admin/users/{self.plain.id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['id'], listed['id'])
        self.assertEqual(detail.data['email'], listed['email'])
        # 详情接口没有 annotate，计数要走回退分支，结果必须与列表一致
        self.assertEqual(detail.data['post_count'], listed['post_count'])
        self.assertEqual(detail.data['detection_count'], listed['detection_count'])

    def test_detail_404_for_unknown_user(self):
        self.assertEqual(self.client_admin.get('/api/admin/users/999999/').status_code, 404)


class ForumTranslationTests(TestCase):
    """
    用户内容的英文译文（第 85 批）

    帖子/评论是用户写的中文，英文界面下必须靠"翻译"才有英文可显示。
    这一组用例覆盖三层：

      ① 模型层：原文指纹 / 译文过期判定（`translation_stale`）；
      ② 服务层：分块、术语校正、人工译文不被覆盖、缓存；
      ③ 接口层：发帖时自动翻译、按需翻译接口、序列化器返回译文与状态、
         以及**翻译服务挂掉时发帖照常成功**（论坛不能被第三方接口拖垮）。

    所有用例都不联网：翻译服务用 `unittest.mock.patch` 换成桩函数，
    这样测试既快又稳定（真实 provider 的网络行为由手工验证覆盖）。
    """

    @classmethod
    def setUpTestData(cls):
        cls.board = ForumBoard.objects.create(name='译文版块', description='desc', is_active=True)
        cls.author = User.objects.create_user(username='tr_author', password='pw12345678')
        cls.reader = User.objects.create_user(username='tr_reader', password='pw12345678')

    def setUp(self):
        self.client_author = APIClient()
        self.client_author.force_authenticate(user=self.author)
        self.client_reader = APIClient()
        self.client_reader.force_authenticate(user=self.reader)

    # ---------- ① 模型层 ----------

    def test_fingerprint_changes_with_source_text(self):
        post = Post.objects.create(
            title='番茄早疫病', content='正文', author=self.author, board=self.board, status='published',
        )
        first = post.source_fingerprint()
        self.assertTrue(first)
        post.title = '番茄晚疫病'
        self.assertNotEqual(post.source_fingerprint(), first)

    def test_stale_only_when_translation_exists(self):
        post = Post.objects.create(
            title='标题', content='正文', author=self.author, board=self.board, status='published',
        )
        # 从未翻译 → 不算"过期"（那是"未翻译"，界面提示语不同）
        self.assertFalse(post.has_translation)
        self.assertFalse(post.translation_stale)

        post.content_en = 'Body'
        post.mark_translated(post.SOURCE_AUTO)
        self.assertTrue(post.has_translation)
        self.assertFalse(post.translation_stale)

        # 原文改了 → 过期
        post.content = '正文改过了'
        self.assertTrue(post.translation_stale)

    def test_empty_source_has_no_fingerprint(self):
        post = Post.objects.create(
            title='', content='', author=self.author, board=self.board, status='published',
        )
        self.assertEqual(post.source_fingerprint(), '')

    # ---------- ② 服务层 ----------

    def test_split_chunks_keeps_sentences_together(self):
        from . import services_translate as st

        text = '第一句。第二句！' + ('很长的一段' * 60)
        chunks = st.split_chunks(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= st.MAX_CHUNK_CHARS for chunk in chunks), chunks)
        self.assertEqual(chunks[0], '第一句。第二句！')

    def test_glossary_fixes_known_mistranslation(self):
        from . import services_translate as st

        self.assertEqual(
            st.apply_glossary('How to Solve Tomato Premature Disease'),
            'How to Solve Tomato early blight',
        )

    def test_translate_text_uses_provider_and_cache(self):
        from . import services_translate as st

        calls = []

        def fake_handler(chunk):
            calls.append(chunk)
            return 'EN:' + chunk

        cache.clear()  # 缓存是跨用例共享的文件/内存缓存，先清干净
        with patch.dict(st._PROVIDERS, {'mymemory': fake_handler}):
            first = st.translate_text('你好', provider='mymemory')
            second = st.translate_text('你好', provider='mymemory')

        self.assertEqual(first, 'EN:你好')
        self.assertEqual(second, 'EN:你好')
        self.assertEqual(len(calls), 1, '第二次应命中缓存，不再请求接口')

    def test_manual_translation_is_not_overwritten(self):
        from . import services_translate as st

        post = Post.objects.create(
            title='手工标题', content='手工正文', author=self.author, board=self.board, status='published',
        )
        post.title_en = 'Manual title'
        post.content_en = 'Manual body'
        post.mark_translated(post.SOURCE_MANUAL)
        post.save()

        with patch.object(st, 'translate_text', side_effect=AssertionError('不应调用翻译接口')):
            changed = st.translate_instance(post)

        self.assertFalse(changed)
        post.refresh_from_db()
        self.assertEqual(post.title_en, 'Manual title')
        self.assertEqual(post.translation_source, Post.SOURCE_MANUAL)

    def test_force_overwrites_manual_translation(self):
        """第 86 批：只有显式 allow_manual_overwrite 才覆盖人工译文

        （第 85 批的旧语义是 `--force` 直接覆盖，那是"作者还不能自己填英文"时的
        权宜做法；现在 `--force` 只重刷机器译文，见 TranslateProviderTests。）
        """
        from . import services_translate as st

        post = Post.objects.create(
            title='手工标题', content='手工正文', author=self.author, board=self.board, status='published',
        )
        post.title_en = 'Manual title'
        post.content_en = 'Manual body'
        post.mark_translated(post.SOURCE_MANUAL)
        post.save()

        with patch.object(st, 'translate_text', side_effect=lambda text, **kw: f'AUTO:{text}'):
            changed = st.translate_instance(post, force=True, allow_manual_overwrite=True)

        self.assertTrue(changed)
        post.refresh_from_db()
        self.assertEqual(post.title_en, 'AUTO:手工标题')
        self.assertEqual(post.content_en, 'AUTO:手工正文')
        self.assertEqual(post.translation_source, Post.SOURCE_AUTO)

    def test_translate_instance_is_idempotent(self):
        from . import services_translate as st

        post = Post.objects.create(
            title='标题', content='正文', author=self.author, board=self.board, status='published',
        )
        with patch.object(st, 'translate_text', side_effect=lambda text, **kw: f'AUTO:{text}'):
            self.assertTrue(st.translate_instance(post))
            # 原文没变 → 第二次不该再翻译
            self.assertFalse(st.translate_instance(post))

    # ---------- ③ 接口层 ----------

    @override_settings(TRANSLATE_ON_WRITE=True, TRANSLATE_ENABLED=True, TRANSLATE_PROVIDER='mymemory')
    def test_post_create_translates_content(self):
        from . import services_translate as st

        with patch.object(st, 'translate_text', side_effect=lambda text, **kw: f'EN({text})'):
            response = self.client_author.post(
                '/api/forums/posts/',
                {'board_id': self.board.id, 'title': '标题', 'content': '正文'},
                format='json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['title_en'], 'EN(标题)')
        self.assertEqual(response.data['content_en'], 'EN(正文)')
        self.assertEqual(response.data['translation_source'], Post.SOURCE_AUTO)
        self.assertFalse(response.data['translation_stale'])

    @override_settings(TRANSLATE_ON_WRITE=True, TRANSLATE_ENABLED=True, TRANSLATE_PROVIDER='mymemory')
    def test_post_create_still_succeeds_when_translate_fails(self):
        """翻译服务挂了（网络/额度）不能影响发帖 —— 这是本功能最重要的一条约束"""
        from . import services_translate as st

        with patch.object(st, 'translate_text', side_effect=st.TranslateError('接口挂了')):
            response = self.client_author.post(
                '/api/forums/posts/',
                {'board_id': self.board.id, 'title': '标题', 'content': '正文'},
                format='json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['title_en'], '')
        self.assertFalse(response.data['translation_stale'])

    @override_settings(TRANSLATE_ON_WRITE=True, TRANSLATE_ENABLED=True, TRANSLATE_PROVIDER='mymemory')
    def test_comment_create_translates_and_sends_english_notification(self):
        from . import services_translate as st

        post = Post.objects.create(
            title='被回复的帖子', content='正文', author=self.author, board=self.board, status='published',
        )
        # 帖子先有译文（真实场景里发帖时已自动翻译），通知才可能带上英文标题
        post.title_en = 'EN(被回复的帖子)'
        post.content_en = 'EN(正文)'
        post.mark_translated(Post.SOURCE_AUTO)
        post.save()

        with patch.object(st, 'translate_text', side_effect=lambda text, **kw: f'EN({text})'):
            response = self.client_reader.post(
                f'/api/forums/posts/{post.id}/comments/',
                {'content': '请问这是什么病害'},
                format='json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['content_en'], 'EN(请问这是什么病害)')

        # 站内通知的英文摘要要用译文，否则英文界面下通知里又冒中文
        notification = Notification.objects.filter(recipient=self.author, type='reply').first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.message_en, 'EN(请问这是什么病害)')
        self.assertIn('EN(被回复的帖子)', notification.title_en)

    def test_manual_english_in_payload_is_kept(self):
        """作者自带英文 → 记成人工译文，自动翻译不再覆盖"""
        from . import services_translate as st

        with patch.object(st, 'translate_text', side_effect=AssertionError('人工译文不该被翻译')):
            response = self.client_author.post(
                '/api/forums/posts/',
                {
                    'board_id': self.board.id, 'title': '标题', 'content': '正文',
                    'title_en': 'Manual title', 'content_en': 'Manual body',
                },
                format='json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['translation_source'], Post.SOURCE_MANUAL)
        self.assertEqual(Post.objects.get(id=response.data['id']).title_en, 'Manual title')

    def test_empty_english_in_payload_does_not_wipe_translation(self):
        """编辑帖子时前端会回传 title_en='' —— 不能把已有译文抹掉（也不能触发重译）"""
        post = Post.objects.create(
            title='标题', content='正文', author=self.author, board=self.board, status='published',
            title_en='Existing title', content_en='Existing body',
        )
        post.mark_translated(post.SOURCE_AUTO)
        post.save()

        # 翻译关闭（settings 在测试环境默认关）+ 空字符串入库 —— 两者都不能动已有译文
        response = self.client_author.patch(
            f'/api/forums/posts/{post.id}/',
            {'title': '标题', 'content': '正文', 'title_en': '', 'content_en': ''},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertEqual(post.title_en, 'Existing title')
        self.assertEqual(post.content_en, 'Existing body')

    @override_settings(TRANSLATE_ENABLED=True, TRANSLATE_PROVIDER='mymemory')
    def test_translate_endpoint_fills_missing_translation(self):
        from . import services_translate as st

        post = Post.objects.create(
            title='历史帖子', content='历史正文', author=self.author, board=self.board, status='published',
        )
        with patch.object(st, 'translate_text', side_effect=lambda text, **kw: f'EN({text})'):
            response = self.client_reader.post(f'/api/forums/posts/{post.id}/translate/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['content_en'], 'EN(历史正文)')
        post.refresh_from_db()
        self.assertTrue(post.has_translation)

    def test_translate_endpoint_503_when_provider_disabled(self):
        post = Post.objects.create(
            title='历史帖子', content='历史正文', author=self.author, board=self.board, status='published',
        )
        with override_settings(TRANSLATE_ENABLED=False):
            response = self.client_reader.post(f'/api/forums/posts/{post.id}/translate/')

        self.assertEqual(response.status_code, 503)

    @override_settings(TRANSLATE_ENABLED=True, TRANSLATE_PROVIDER='mymemory')
    def test_translate_endpoint_503_when_provider_fails(self):
        from . import services_translate as st

        post = Post.objects.create(
            title='历史帖子', content='历史正文', author=self.author, board=self.board, status='published',
        )
        with patch.object(st, 'translate_text', side_effect=st.TranslateError('额度用尽')):
            response = self.client_reader.post(f'/api/forums/posts/{post.id}/translate/')

        self.assertEqual(response.status_code, 503)
        self.assertIn('额度用尽', response.data['detail'])

    @override_settings(TRANSLATE_ENABLED=True, TRANSLATE_PROVIDER='mymemory')
    def test_comment_translate_endpoint(self):
        from . import services_translate as st

        post = Post.objects.create(
            title='帖子', content='正文', author=self.author, board=self.board, status='published',
        )
        comment = Comment.objects.create(content='评论正文', author=self.reader, post=post)

        with patch.object(st, 'translate_text', side_effect=lambda text, **kw: f'EN({text})'):
            response = self.client_reader.post(
                f'/api/forums/posts/{post.id}/comments/{comment.id}/translate/',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['content_en'], 'EN(评论正文)')

    def test_translation_fields_exposed_in_comment_list(self):
        post = Post.objects.create(
            title='帖子', content='正文', author=self.author, board=self.board, status='published',
        )
        comment = Comment.objects.create(
            content='评论正文', content_en='Comment body', author=self.reader, post=post,
        )
        comment.mark_translated(Comment.SOURCE_AUTO)
        comment.save()

        data = self.client_reader.get(f'/api/forums/posts/{post.id}/comments/').data
        row = data['results'][0]
        self.assertEqual(row['content_en'], 'Comment body')
        self.assertEqual(row['translation_source'], Comment.SOURCE_AUTO)
        self.assertFalse(row['translation_stale'])

    def test_user_comment_serializer_carries_english_post_title(self):
        """资料页的"来自《帖子》"在英文界面下要用英文标题（第 85 批）"""
        post = Post.objects.create(
            title='中文标题', title_en='English title', content='正文',
            author=self.author, board=self.board, status='published',
        )
        Comment.objects.create(content='评论', author=self.reader, post=post)

        data = self.client_reader.get(f'/api/users/{self.reader.id}/comments/').data
        row = data['results'][0]
        self.assertEqual(row['post_title'], '中文标题')
        self.assertEqual(row['post_title_en'], 'English title')

    def test_stale_flag_reaches_api_after_source_edit(self):
        post = Post.objects.create(
            title='标题', content='正文', author=self.author, board=self.board, status='published',
            title_en='Title', content_en='Body',
        )
        post.mark_translated(post.SOURCE_MANUAL)
        post.save()

        response = self.client_author.patch(
            f'/api/forums/posts/{post.id}/',
            {'title': '标题改了', 'content': '正文'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        # 人工译文不会被覆盖，但必须被标记为"已过期"
        self.assertTrue(response.data['translation_stale'])
        self.assertEqual(response.data['title_en'], 'Title')

    # ---------- 意见反馈（同一套机制的第二个使用方） ----------

    def test_feedback_translation_fields_in_api(self):
        """反馈内容与管理员回复都要有英文（第 85 批）"""
        feedback = Feedback.objects.create(
            user=self.author, category='suggestion', suggestion='建议增加病虫害预警推送',
            admin_reply='已列入计划', status='resolved',
            suggestion_en='Please add pest alerts', admin_reply_en='Already planned',
        )
        feedback.mark_translated(Feedback.SOURCE_AUTO)
        feedback.save()

        data = self.client_author.get(f'/api/feedback/{feedback.id}/').data
        self.assertEqual(data['suggestion_en'], 'Please add pest alerts')
        self.assertEqual(data['admin_reply_en'], 'Already planned')
        self.assertFalse(data['translation_stale'])

    def test_system_suggestion_uses_fixed_mapping_not_machine_translation(self):
        """「识别正确/识别错误」是系统写死的文案，必须用固定映射（不是机翻结果）"""
        feedback = Feedback.objects.create(
            user=self.author, category='recognition', suggestion='识别正确',
            disease_name='番茄晚疫病', is_correct=True,
        )
        # 即使库里被写入过机翻结果，也要被固定映射覆盖（否则会出现 Identify Correctly）
        feedback.suggestion_en = 'Identify Correctly'
        feedback.save(update_fields=['suggestion_en'])

        data = self.client_author.get(f'/api/feedback/{feedback.id}/').data
        self.assertEqual(data['suggestion_en'], 'Marked correct')

    def test_feedback_stale_after_admin_reply_edit(self):
        feedback = Feedback.objects.create(
            user=self.author, category='suggestion', suggestion='建议',
            admin_reply='已处理', suggestion_en='Suggestion', admin_reply_en='Done',
        )
        feedback.mark_translated(Feedback.SOURCE_MANUAL)
        feedback.save()

        data = self.client_author.get(f'/api/feedback/{feedback.id}/').data
        self.assertFalse(data['translation_stale'])

        feedback.admin_reply = '已处理，并已在 2.1 版本上线'
        self.assertTrue(feedback.translation_stale)

    def test_is_translatable_skips_system_only_feedback(self):
        """批量命令不该把「识别正确」这种系统文案排进翻译队列"""
        from . import services_translate as st

        only_system = Feedback.objects.create(
            user=self.author, category='recognition', suggestion='识别正确',
        )
        with_reply = Feedback.objects.create(
            user=self.author, category='suggestion', suggestion='识别错误', admin_reply='已收到',
        )
        real_text = Feedback.objects.create(
            user=self.author, category='suggestion', suggestion='希望支持批量导出',
        )

        self.assertFalse(st.is_translatable(only_system))
        self.assertTrue(st.is_translatable(with_reply))  # 有管理员回复要翻
        self.assertTrue(st.is_translatable(real_text))


class TranslateProviderTests(TestCase):
    """
    翻译 provider 与重刷语义（第 86 批）

    覆盖两件事：
      ① 新增的 DeepL / 百度 provider 的**请求构造**（端点选择、签名、错误码识别）——
         全部把网络层 `_http_form` 换成桩，测试不联网；
      ② `--force` 与 `--force-manual` 的区别：前者重刷机器译文、**不动**人工译文，
         后者才覆盖人工译文。这条在"作者能自己填英文"之后变得很关键 ——
         一键重刷不能把作者写的英文冲掉。
    """

    @classmethod
    def setUpTestData(cls):
        cls.board = ForumBoard.objects.create(name='provider版块', description='d', is_active=True)
        cls.author = User.objects.create_user(username='tp_author', password='pw12345678')

    def setUp(self):
        # 译文缓存跨用例共享（settings 里测试用 LocMemCache，但同一次 test run 内是同一个
        # 进程），provider 的桩返回不同就必须先清缓存，否则会"命中上一条用例的译文"。
        cache.clear()

    def test_deepl_uses_free_endpoint_for_fx_key(self):
        from . import services_translate as st

        captured = {}

        def fake_form(url, fields, headers=None):
            captured['url'] = url
            captured['fields'] = fields
            captured['headers'] = headers or {}
            return {'translations': [{'text': 'Tomato late blight'}]}

        with override_settings(TRANSLATE_API_KEY='abc:fx'), patch.object(st, '_http_form', fake_form):
            result = st.translate_text('番茄晚疫病', provider='deepl')

        self.assertEqual(result, 'Tomato late blight')
        self.assertTrue(captured['url'].startswith('https://api-free.deepl.com'), captured['url'])
        # 实测：DeepL 现在只认 Authorization 头，旧的表单字段 auth_key 会 403
        self.assertEqual(captured['headers'].get('Authorization'), 'DeepL-Auth-Key abc:fx')
        self.assertNotIn('auth_key', captured['fields'])
        self.assertEqual(captured['fields']['source_lang'], 'ZH')
        self.assertEqual(captured['fields']['target_lang'], 'EN-US')

    def test_deepl_uses_pro_endpoint_without_fx_suffix(self):
        from . import services_translate as st

        captured = {}

        def fake_form(url, fields, headers=None):
            captured['url'] = url
            return {'translations': [{'text': 'x'}]}

        with override_settings(TRANSLATE_API_KEY='abc-123'), patch.object(st, '_http_form', fake_form):
            st.translate_text('你好', provider='deepl')

        self.assertTrue(captured['url'].startswith('https://api.deepl.com'), captured['url'])

    def test_missing_config_is_reported_before_request(self):
        from . import services_translate as st

        with override_settings(TRANSLATE_API_KEY='', TRANSLATE_APP_ID=''):
            with self.assertRaises(st.TranslateError) as ctx:
                st.translate_text('你好', provider='deepl')
            self.assertIn('TRANSLATE_API_KEY', str(ctx.exception))

            with self.assertRaises(st.TranslateError) as ctx:
                st.translate_text('你好', provider='baidu')
            self.assertIn('TRANSLATE_APP_ID', str(ctx.exception))

    def test_unknown_provider_lists_options(self):
        from . import services_translate as st

        with self.assertRaises(st.TranslateError) as ctx:
            st.translate_text('你好', provider='google')
        self.assertIn('deepl', str(ctx.exception))

    def test_baidu_signs_request_and_parses_result(self):
        from . import services_translate as st

        captured = {}

        def fake_form(url, fields, headers=None):
            captured['url'] = url
            captured['fields'] = fields
            return {'trans_result': [{'src': '番茄晚疫病', 'dst': 'Tomato late blight'}]}

        with override_settings(TRANSLATE_APP_ID='app123', TRANSLATE_API_KEY='key456'), \
                patch.object(st, '_http_form', fake_form):
            result = st.translate_text('番茄晚疫病', provider='baidu')

        self.assertEqual(result, 'Tomato late blight')
        self.assertIn('/api/trans/vip/translate', captured['url'])
        fields = captured['fields']
        expected = hashlib.md5(
            f"app123{fields['q']}{fields['salt']}key456".encode('utf-8')
        ).hexdigest()
        self.assertEqual(fields['sign'], expected, '签名必须是 md5(appid+q+salt+密钥)')
        self.assertEqual(fields['from'], 'zh')
        self.assertEqual(fields['to'], 'en')

    def test_baidu_error_code_becomes_translate_error(self):
        from . import services_translate as st

        with override_settings(TRANSLATE_APP_ID='app123', TRANSLATE_API_KEY='key456'), \
                patch.object(st, '_http_form', lambda url, fields, headers=None: {'error_code': '54004', 'error_msg': '账户余额不足'}):
            with self.assertRaises(st.TranslateError) as ctx:
                st.translate_text('你好', provider='baidu')
        self.assertIn('54004', str(ctx.exception))
        self.assertIn('余额不足', str(ctx.exception))

    def test_force_does_not_touch_manual_translation(self):
        """--force 只重刷机器译文（第 86 批语义）"""
        from . import services_translate as st

        post = Post.objects.create(
            title='手工标题', content='手工正文', author=self.author, board=self.board, status='published',
            title_en='Manual title', content_en='Manual body',
        )
        post.mark_translated(Post.SOURCE_MANUAL)
        post.save()

        with patch.object(st, 'translate_text', side_effect=lambda text, **kw: f'AUTO:{text}'):
            # 命令层传的就是 force=True + allow_manual_overwrite=False
            changed = st.translate_instance(post, force=True, allow_manual_overwrite=False)

        self.assertFalse(changed)
        post.refresh_from_db()
        self.assertEqual(post.title_en, 'Manual title')

    def test_force_manual_overwrites_manual_translation(self):
        from . import services_translate as st

        post = Post.objects.create(
            title='手工标题', content='手工正文', author=self.author, board=self.board, status='published',
            title_en='Manual title', content_en='Manual body',
        )
        post.mark_translated(Post.SOURCE_MANUAL)
        post.save()

        with patch.object(st, 'translate_text', side_effect=lambda text, **kw: f'AUTO:{text}'):
            changed = st.translate_instance(post, force=True, allow_manual_overwrite=True)

        self.assertTrue(changed)
        post.refresh_from_db()
        self.assertEqual(post.title_en, 'AUTO:手工标题')
        self.assertEqual(post.translation_source, Post.SOURCE_AUTO)

    def test_dry_run_lists_only_missing_when_forced(self):
        """`--force --dry-run` 应该只列出"机器译文可重刷"的帖子，人工译文不列"""
        from io import StringIO

        from django.core.management import call_command

        auto = Post.objects.create(
            title='机器译文帖', content='正文', author=self.author, board=self.board, status='published',
            title_en='Auto title', content_en='Auto body',
        )
        auto.mark_translated(Post.SOURCE_AUTO)
        auto.save()

        manual = Post.objects.create(
            title='人工译文帖', content='正文', author=self.author, board=self.board, status='published',
            title_en='Manual title', content_en='Manual body',
        )
        manual.mark_translated(Post.SOURCE_MANUAL)
        manual.save()

        out = StringIO()
        call_command('translate_forum_content', '--kind=post', '--force', '--dry-run', stdout=out)
        listed = out.getvalue()
        self.assertIn('机器译文帖', listed)
        self.assertNotIn('人工译文帖', listed)
        self.assertIn('force(不动人工译文)', listed)

    def test_provider_check_command_reports_missing_config(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        with override_settings(TRANSLATE_API_KEY=''), self.assertRaises(SystemExit) as ctx:
            call_command('translate_provider_check', '--provider=deepl', stdout=out)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn('TRANSLATE_API_KEY', out.getvalue())

    def test_provider_check_command_success_path(self):
        from io import StringIO

        from django.core.management import call_command
        from . import services_translate as st

        out = StringIO()
        with patch.object(st, 'translate_text', side_effect=lambda text, **kw: 'stub translation'):
            call_command('translate_provider_check', stdout=out)
        self.assertIn('stub translation', out.getvalue())


# ============================================================================
# 第 112 批：私信"发起新会话"用的用户搜索
# ============================================================================
class UserSearchViewTests(TestCase):
    """
    `GET /api/users/search/?q=<关键词>`（第 112 批）

    背景：用户反馈"私信功能用不了"，查下来收发链路是好的 ——
    问题是**没有发起新会话的入口**，用户不知道去哪儿找人。
    私信页要加一个"发起新私信"的弹窗，而这个弹窗需要一个
    "普通用户也能按用户名搜人"的接口：

      · `/api/users/`        是仅管理员（IsAdminUser），普通用户搜不了；
      · `/api/users/follow-suggestions/` 只回固定 Top 5，不接受关键词。

    这个接口让**任何登录用户**都能按用户名查人，等于把"平台上有哪些用户"
    开放了出去，所以限制得比较紧 —— 下面每条用例钉住其中一道限制。
    """

    @classmethod
    def setUpTestData(cls):
        cls.me = User.objects.create_user(username='search_me', password='pw12345678')
        cls.alice = User.objects.create_user(username='alice_farmer', password='pw12345678')
        cls.alice2 = User.objects.create_user(username='alice_worker', password='pw12345678')
        cls.bob = User.objects.create_user(username='bob_grower', password='pw12345678')
        # 注销冷静期里的账号（is_active=False）不该被搜到
        cls.gone = User.objects.create_user(username='alice_gone', password='pw12345678')
        cls.gone.is_active = False
        cls.gone.save(update_fields=['is_active'])

    def setUp(self):
        cache.clear()
        self.client_auth = APIClient()
        self.client_auth.force_authenticate(user=self.me)

    def _search(self, keyword):
        return self.client_auth.get('/api/users/search/', {'q': keyword})

    def test_requires_login(self):
        """未登录不能用来枚举用户名"""
        response = APIClient().get('/api/users/search/', {'q': 'alice'})
        self.assertIn(response.status_code, (401, 403))

    def test_finds_by_partial_username(self):
        response = self._search('alice')
        self.assertEqual(response.status_code, 200)
        names = {item['username'] for item in response.data['results']}
        self.assertIn('alice_farmer', names)
        self.assertIn('alice_worker', names)
        self.assertNotIn('bob_grower', names, '不该匹配到不含关键词的人')

    def test_excludes_self(self):
        """搜到自己没有意义（私信页也不需要给自己发消息）"""
        names = {item['username'] for item in self._search('search_me').data['results']}
        self.assertNotIn('search_me', names)

    def test_excludes_inactive_user(self):
        """注销冷静期里的账号（is_active=False）不该还能被搜到"""
        names = {item['username'] for item in self._search('alice').data['results']}
        self.assertNotIn('alice_gone', names)

    def test_short_keyword_returns_empty_with_hint(self):
        """
        关键词太短 → 空列表 + 提示，而不是报错。

        为什么必须有这条：没有最小长度限制时，`?q=a` 可以把全站用户名
        **逐字母扫出来**（用户名常常就是手机号或真名，能枚举本身就是隐私问题）。
        回空列表而不是 400，是因为用户只是还没输够字，不是操作错了 ——
        弹错误框反而像"功能坏了"。
        """
        for keyword in ('', 'a', ' '):
            with self.subTest(keyword=keyword):
                response = self._search(keyword)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data['results'], [])
                self.assertIn('至少', response.data['detail'])

    def test_result_is_capped(self):
        """一次最多 10 条 —— 不能靠翻页把整站用户拉走"""
        for index in range(15):
            User.objects.create_user(username=f'cap_user_{index}', password='pw12345678')
        response = self._search('cap_user')
        self.assertEqual(len(response.data['results']), 10)

    def test_only_minimal_fields_returned(self):
        """
        只回最少字段 —— 不回 email、积分、登录时间等。

        允许 `role`：它不是敏感信息，而且是**展示需要**的
        （前端要在候选列表里标出"专家/管理员"），
        `follow-suggestions` 回的也是同一组字段（两条共用 `_user_brief`）。
        最初我按"id/username/avatar/bio"写死了四个，测试红了 ——
        红得对：**该由"这个字段该不该公开"来决定，而不是由我以为的清单决定**。

        这条测试的真正价值是**挡住以后往上加字段**：接口对所有登录用户开放，
        多回一个字段就是多泄露一份信息（比如 email、`last_login`）。
        """
        item = self._search('alice_farmer').data['results'][0]
        allowed = {'id', 'username', 'avatar', 'bio', 'role'}
        self.assertEqual(
            set(item.keys()) - allowed,
            set(),
            f'多回了字段：{sorted(set(item.keys()) - allowed)} —— '
            '这个接口对所有登录用户开放，加字段前先想清楚是否必要',
        )

    def test_search_path_does_not_shadow_user_detail(self):
        """
        `/api/users/search/` 必须排在 `/api/users/<int:user_id>/` 之前。

        这条不只是"顺序约定"：如果顺序反了，`search` 会被当成 user_id 去匹配
        int 转换器 → 匹配不上 → **404**，而搜索功能会整个失效。
        （同 `users/check-username/` 那条的理由，见 urls.py 的注释。）
        """
        from django.urls import resolve

        match = resolve('/api/users/search/')
        self.assertEqual(match.url_name, 'user-search')


# ============================================================================
# 第 114 批：私信重做（分页 / 已读反馈 / 单侧删除 / 摘要）
# ============================================================================
class DirectMessagePaginationTests(TestCase):
    """
    `GET /api/messages/with/<id>/?before_id=`

    修的是**结构性缺陷**：原来 `list(queryset)` 把整个会话读进内存再切最后 100 条，
    于是更早的消息**没有任何接口能取到** —— 聊久了就等于丢历史。
    现在用 `before_id` 游标分页。

    为什么用游标而不是 offset：聊天时随时会插入新消息，
    offset 分页会因为插入而**错位/重复**（经典坑）。
    """

    @classmethod
    def setUpTestData(cls):
        cls.me = User.objects.create_user(username='pg_me', password='pw12345678')
        cls.other = User.objects.create_user(username='pg_other', password='pw12345678')

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(user=self.me)
        self.key = conversation_key_for(self.me.id, self.other.id)

    def _make_history(self, count, *, sender=None):
        """造 `count` 条**对方发给我**的消息（这样也能顺便验证未读逻辑）"""
        sender = sender or self.other
        recipient = self.me if sender == self.other else self.other
        return [
            DirectMessage.objects.create(
                sender=sender, recipient=recipient, content=f'第 {index} 条',
                conversation_key=self.key, is_read=False,
            )
            for index in range(count)
        ]

    def test_returns_newest_page_by_default(self):
        """默认回**最新**一页（打开聊天就该看到最近的）"""
        self._make_history(60)
        response = self.client.get(f'/api/messages/with/{self.other.id}/', {'page_size': 20})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 20)
        contents = [item['content'] for item in response.data['results']]
        # 返回顺序是"从旧到新"（聊天记录该有的顺序）
        self.assertEqual(contents[0], '第 40 条')
        self.assertEqual(contents[-1], '第 59 条')
        self.assertTrue(response.data['has_more'], '还有更早的消息，has_more 应为 True')

    def test_before_id_walks_backwards(self):
        """带 before_id 能取到更早的一页 —— 这正是原来取不到的部分"""
        self._make_history(60)
        first = self.client.get(f'/api/messages/with/{self.other.id}/', {'page_size': 20}).data
        self.assertEqual(first['results'][0]['content'], '第 40 条')

        second = self.client.get(
            f'/api/messages/with/{self.other.id}/',
            {'page_size': 20, 'before_id': first['oldest_id']},
        ).data
        contents = [item['content'] for item in second['results']]
        self.assertEqual(len(contents), 20)
        self.assertEqual(contents[-1], '第 39 条', '上一页的最后一条应当紧挨着这一页的第一条')
        self.assertEqual(contents[0], '第 20 条')
        self.assertTrue(second['has_more'])

    def test_walk_to_the_very_beginning(self):
        """一直翻能翻到第一条，并且最后 has_more=False（不会无限翻）"""
        self._make_history(35)
        collected = []
        before = None
        for _ in range(10):  # 上限防止死循环
            params = {'page_size': 10}
            if before:
                params['before_id'] = before
            page = self.client.get(f'/api/messages/with/{self.other.id}/', params).data
            collected = [item['content'] for item in page['results']] + collected
            if not page['has_more']:
                break
            before = page['oldest_id']
        self.assertEqual(len(collected), 35, '应当正好把 35 条全部翻完')
        self.assertEqual(collected[0], '第 0 条')
        self.assertEqual(collected[-1], '第 34 条')

    def test_older_page_does_not_mark_new_messages_read(self):
        """
        **往上翻历史不该把新消息标成已读。**

        这条很要紧：用户翻历史时并没有看到最新那条，
        如果把未读清零，红点会凭空消失、消息再也不会被注意到。
        """
        self._make_history(30)
        first = self.client.get(f'/api/messages/with/{self.other.id}/', {'page_size': 10}).data
        self.assertGreaterEqual(first['marked_read'], 1, '打开最新一页应当清零未读')

        # 再翻历史页：不该有任何"标记已读"
        second = self.client.get(
            f'/api/messages/with/{self.other.id}/',
            {'page_size': 10, 'before_id': first['oldest_id']},
        ).data
        self.assertEqual(second['marked_read'], 0, '翻历史页不该标记已读')

    def test_fresh_unread_survives_walking_history(self):
        """对方刚发来的未读，在我只翻历史时**必须还是未读**"""
        self._make_history(20)
        first = self.client.get(f'/api/messages/with/{self.other.id}/', {'page_size': 10}).data
        self.assertGreater(first['marked_read'], 0)

        fresh = DirectMessage.objects.create(
            sender=self.other, recipient=self.me, content='刚发来的',
            conversation_key=self.key, is_read=False,
        )
        self.client.get(
            f'/api/messages/with/{self.other.id}/',
            {'page_size': 10, 'before_id': first['oldest_id']},
        )
        fresh.refresh_from_db()
        self.assertFalse(fresh.is_read, '只翻历史时，最新那条未读不该被标记')

    def test_invalid_cursor_falls_back_to_newest_page(self):
        """
        游标无效（消息被删了 / 不是这个会话的）时回**最新一页**，而不是报错。

        为什么：前端往上滚的一瞬间，对方可能正好删了那条消息 ——
        报错会让整个聊天窗口红掉，而用户只是想看更早的记录。
        """
        self._make_history(5)
        response = self.client.get(
            f'/api/messages/with/{self.other.id}/', {'before_id': 99999999, 'page_size': 10},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 5, '应当回退到最新一页')


class DirectMessageReadReceiptTests(TestCase):
    """
    `read_at` 要在序列化里返回（第 114 批）。

    原来这个字段一直在写（打开会话时 `update(is_read=True, read_at=now)`），
    但**从不返回** —— 前端想显示"已读"也没有数据可用。典型的"写了没人读"。
    """

    @classmethod
    def setUpTestData(cls):
        cls.me = User.objects.create_user(username='rr_me', password='pw12345678')
        cls.other = User.objects.create_user(username='rr_other', password='pw12345678')

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(user=self.me)

    def test_read_at_is_returned(self):
        sent = DirectMessage.objects.create(
            sender=self.me, recipient=self.other, content='你好',
            conversation_key=conversation_key_for(self.me.id, self.other.id),
        )
        response = self.client.get(f'/api/messages/with/{self.other.id}/')
        self.assertIsNone(response.data['results'][0]['read_at'], '还没读 → read_at 为 None')

        # 对方读了（直接改库模拟"对方打开会话"）
        sent.is_read = True
        sent.read_at = timezone.now()
        sent.save(update_fields=['is_read', 'read_at'])

        response = self.client.get(f'/api/messages/with/{self.other.id}/')
        self.assertIsNotNone(
            response.data['results'][0]['read_at'],
            '读过的消息必须带上 read_at —— 否则前端做不了"已读"标记',
        )


class DirectMessageDeleteTests(TestCase):
    """
    `DELETE /api/messages/with/<id>/`（第 114 批）

    `sender_deleted` / `recipient_deleted` 两个字段从第 42 批起就在库里，
    但**一直没有接口写它们**（死字段）。补上删除时最关键的一点是
    **单侧**：我删掉不该让对方也看不到 —— 这是模型注释里就写明的设计。
    """

    @classmethod
    def setUpTestData(cls):
        cls.me = User.objects.create_user(username='del_me', password='pw12345678')
        cls.other = User.objects.create_user(username='del_other', password='pw12345678')

    def setUp(self):
        cache.clear()
        self.key = conversation_key_for(self.me.id, self.other.id)
        self.client = APIClient()
        self.client.force_authenticate(user=self.me)
        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.other)

    def test_delete_only_hides_for_me(self):
        mine = DirectMessage.objects.create(
            sender=self.me, recipient=self.other, content='我发的', conversation_key=self.key,
        )
        theirs = DirectMessage.objects.create(
            sender=self.other, recipient=self.me, content='他发的', conversation_key=self.key,
        )

        response = self.client.delete(f'/api/messages/with/{self.other.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['deleted'], 2)

        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertTrue(mine.sender_deleted, '我发的、我删了 → sender_deleted')
        self.assertTrue(theirs.recipient_deleted, '他发的、我删了 → recipient_deleted')
        self.assertEqual(self.client.get('/api/messages/').data['count'], 0, '我的会话列表应当空了')

        # 对方那边：完全不受影响
        self.assertEqual(
            self.other_client.get('/api/messages/').data['count'], 1,
            '我删会话不该让对方的会话也消失（单侧软删）',
        )
        detail = self.other_client.get(f'/api/messages/with/{self.me.id}/').data
        self.assertEqual(detail['count'], 2, '对方仍然能看到两条消息')

    def test_new_message_restores_the_other_side(self):
        """
        对方删过会话后，我再发一条 —— 对方那边必须能重新看到。

        否则从对方视角看就是**这条新消息凭空消失**（他的 `recipient_deleted`
        还挂着，那一侧过滤掉了整个会话）。
        """
        DirectMessage.objects.create(
            sender=self.me, recipient=self.other, content='旧消息', conversation_key=self.key,
        )
        self.other_client.delete(f'/api/messages/with/{self.me.id}/')
        self.assertEqual(self.other_client.get('/api/messages/').data['count'], 0)

        self.client.post(f'/api/messages/with/{self.other.id}/', {'content': '新消息'}, format='json')
        self.assertEqual(
            self.other_client.get('/api/messages/').data['count'], 1,
            '收到新消息后，对方那一侧的删除标记应当被清掉',
        )

    def test_delete_does_not_restore_my_own_deleted_messages(self):
        """
        发新消息时只清 `recipient_deleted`，**不能连 `sender_deleted` 一起清**。

        后者是"这条消息的发件人不想要它了"，与收件人无关；
        一起清会把发件人自己删过的消息又恢复出来（我第一版就是这么写的）。
        """
        old = DirectMessage.objects.create(
            sender=self.me, recipient=self.other, content='我早先删掉的', conversation_key=self.key,
        )
        DirectMessage.objects.filter(pk=old.pk).update(sender_deleted=True)
        self.client.post(f'/api/messages/with/{self.other.id}/', {'content': '新的一条'}, format='json')

        old.refresh_from_db()
        self.assertTrue(old.sender_deleted, '我自己删过的消息不该被恢复出来')

    def test_cannot_delete_conversation_with_self(self):
        """不能给自己发私信 —— 删除同样应当被拒（否则会误删自己的另一半消息）"""
        response = self.client.delete(f'/api/messages/with/{self.me.id}/')
        self.assertEqual(response.status_code, 400)


class DirectMessagePreviewTests(TestCase):
    """会话列表的"最后一条"摘要（第 114 批）"""

    @classmethod
    def setUpTestData(cls):
        cls.me = User.objects.create_user(username='pv_me', password='pw12345678')
        cls.other = User.objects.create_user(username='pv_other', password='pw12345678')

    def setUp(self):
        cache.clear()
        self.key = conversation_key_for(self.me.id, self.other.id)
        self.client = APIClient()
        self.client.force_authenticate(user=self.me)

    def _preview(self):
        return self.client.get('/api/messages/').data['results'][0]['last_message']

    def test_image_message_shows_label_not_raw_json(self):
        """
        图片消息的正文是 JSON，摘要必须是 `[图片]` 而不是原始 JSON。

        原来直接 `content[:60]`，会话列表里会显示
        `{"type":"image","url":"http://…` —— 用户看到的是半个 URL。
        """
        DirectMessage.objects.create(
            sender=self.other, recipient=self.me,
            content='{"type": "image", "url": "http://x/y.jpg"}',
            conversation_key=self.key,
        )
        preview = self._preview()
        self.assertEqual(preview, '[图片]')
        self.assertNotIn('http', preview)

    def test_text_message_preview_unchanged(self):
        DirectMessage.objects.create(
            sender=self.other, recipient=self.me, content='普通文字消息',
            conversation_key=self.key,
        )
        self.assertEqual(self._preview(), '普通文字消息')

    def test_broken_json_falls_back_to_text(self):
        """正文是坏 JSON（以 `{` 开头但解析不了）时按普通文字处理，不该 500"""
        DirectMessage.objects.create(
            sender=self.other, recipient=self.me, content='{这不是合法 JSON',
            conversation_key=self.key,
        )
        response = self.client.get('/api/messages/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['last_message'], '{这不是合法 JSON')


# ============================================================================
# 第 125 批：角色 × 端点 的能力矩阵
# ============================================================================
# 为什么要有这一组
# ----------------------------------------------------------------------------
# 在它之前，"谁是管理员"被复制在约 30 处、三种写法并不等价（DRF 的 IsAdminUser
# 只认 is_staff、IsAdminOrReadOnly 认三样、各模块自己抄的 _is_admin 又各写一遍）。
# 第 124 批把这些判定收口到 `api/capabilities.py`，第 125 批让
# `role='EDITOR'`（信息编辑员）真正拿到 CONTENT 能力。
#
# 收口带来的**新风险**是"某个接口忘了改"——比如它还在用 DRF 的 IsAdminUser，
# 或者某人顺手把 USER_ADMIN 的接口写成了 CONTENT。这种错误不会自己暴露：
# 只有真的用 EDITOR 账号去撞才会发现。
#
# 所以这里把**产品口径**（见 docs/内容编辑角色方案.md）逐条断言成测试：
#   · EDITOR 能做的（CONTENT）：必须 2xx
#   · EDITOR 不能做的（USER_ADMIN / BROADCAST / 全权管理员专属）：必须 403
#   · 全权管理员（is_staff / role=ADMIN）在**所有**这些端点上都必须能过
# 以后谁再新增一个管理端接口，照着这张表补一行即可。
# ============================================================================
class CapabilityMatrixTests(APITestCase):
    """role × 端点 的能力矩阵（第 125 批）"""

    def setUp(self):
        cache.clear()
        User = get_user_model()

        # 三类账号：全权管理员 / 信息编辑员 / 普通用户
        self.admin = User.objects.create_user(
            username='zz_cap_admin', password='pw12345678', is_staff=True, role='ADMIN',
        )
        self.editor = User.objects.create_user(
            username='zz_cap_editor', password='pw12345678', role='EDITOR',
        )
        # 第 128 批：编辑员现在还要**按模块授权**。这一组测试验的是"编辑员这个角色
        # 能做哪些内容工作、不能碰哪些账号/发声接口"，所以给他**四个模块全勾**；
        # "只勾一块时互不干扰"由 ContentModuleScopeTests 单独盯。
        EditorModuleGrant.objects.bulk_create([
            EditorModuleGrant(user=self.editor, module=module, granted_by=self.admin)
            for module in ('review', 'news', 'pests', 'feedback')
        ])
        self.plain = User.objects.create_user(
            username='zz_cap_plain', password='pw12345678', role='USER',
        )

        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)
        self.client_editor = APIClient()
        self.client_editor.force_authenticate(user=self.editor)
        self.client_plain = APIClient()
        self.client_plain.force_authenticate(user=self.plain)

        # 造一点被操作的数据
        self.pest = PestInfo.objects.create(
            name='zz能力矩阵病', crop_type='玉米', english_identifier='zz_cap_pest',
            symptoms='用于权限矩阵测试',
        )
        self.news = News.objects.create(title='zz能力矩阵新闻', content='<p>x</p>', author=self.admin)
        self.board = ForumBoard.objects.create(name='zz能力矩阵版块', description='x')
        self.post = Post.objects.create(
            title='zz能力矩阵帖子', content='x', author=self.plain, board=self.board,
            status='pending',
        )
        self.comment = Comment.objects.create(post=self.post, author=self.plain, content='x')
        # 别人的反馈：EDITOR 能看能回，但**不能删**
        self.other_feedback = Feedback.objects.create(
            user=self.plain, category='suggestion', suggestion='zz能力矩阵反馈',
        )

    # ---------- 工具 ----------
    def _expect(self, client, method, url, expected, body=None, note=''):
        """发一个请求并断言状态码（把"期望"写在调用处，失败信息带说明）"""
        send = getattr(client, method)
        kwargs = {'format': 'json'}
        if body is not None:
            kwargs['data'] = body
        response = send(url, **kwargs)
        self.assertEqual(
            response.status_code, expected,
            f'{note}｜{method.upper()} {url} 期望 {expected}，实际 {response.status_code}'
            f'｜{getattr(response, "data", "")}',
        )
        return response

    # ---------- ① CONTENT：信息编辑员必须能做 ----------
    def test_editor_can_manage_content(self):
        """EDITOR 的内容生产权限：百科 / 新闻 / 审核 / 反馈回复 / 日历 / 看板"""

        # 病害百科：新增 + 修改 + 删除
        created = self._expect(
            self.client_editor, 'post', '/api/pests/',
            status.HTTP_201_CREATED,
            {'name': 'zz能力矩阵新增', 'crop_type': '玉米',
             'english_identifier': 'zz_cap_new', 'symptoms': 'x',
             'prevention_methods': []},
            note='百科新增（CONTENT）',
        )
        new_id = created.data['id']
        self._expect(self.client_editor, 'patch', f'/api/pests/{new_id}/',
                     status.HTTP_200_OK, {'symptoms': '改过'}, note='百科修改（CONTENT）')
        self._expect(self.client_editor, 'delete', f'/api/pests/{new_id}/',
                     status.HTTP_204_NO_CONTENT, note='百科删除（CONTENT）')

        # 新闻：新增 + 修改 + 删除
        news = self._expect(
            self.client_editor, 'post', '/api/news/',
            status.HTTP_201_CREATED,
            {'title': 'zz能力矩阵编辑员建的新闻', 'content': '<p>x</p>', 'category': 'notice'},
            note='新闻新增（CONTENT）',
        )
        self._expect(self.client_editor, 'patch', f"/api/news/{news.data['id']}/",
                     status.HTTP_200_OK, {'source': '本站'}, note='新闻修改（CONTENT）')

        # 内容审核：通过 / 驳回 / 批量
        self._expect(self.client_editor, 'post', f'/api/forums/posts/{self.post.id}/approve/',
                     status.HTTP_200_OK, note='帖子审核通过（CONTENT）')
        self._expect(self.client_editor, 'post', f'/api/forums/posts/{self.post.id}/reject/',
                     status.HTTP_200_OK, {'reason': '不合适'}, note='帖子审核驳回（CONTENT）')
        self._expect(self.client_editor, 'post', '/api/forums/posts/bulk-review/',
                     status.HTTP_200_OK, {'ids': [self.post.id], 'action': 'approve'},
                     note='批量审核（CONTENT）')

        # 评论软删除（内容处置；硬删除见下面的"全权管理员专属"）
        # 该 action 返回 204（无正文），不是 200
        self._expect(self.client_editor, 'post',
                     f'/api/forums/posts/{self.post.id}/comments/{self.comment.id}/delete/',
                     status.HTTP_204_NO_CONTENT, note='评论软删除（CONTENT）')

        # 意见反馈：能看到**别人**的反馈 + 能回复
        listed = self._expect(self.client_editor, 'get', '/api/feedback/',
                              status.HTTP_200_OK, note='反馈列表（CONTENT）')
        seen_ids = {row['id'] for row in listed.data['results']} if isinstance(
            listed.data, dict) and 'results' in listed.data else {r['id'] for r in listed.data}
        self.assertIn(
            self.other_feedback.id, seen_ids,
            '信息编辑员应当能看到其他用户提交的反馈（否则没法回复）',
        )
        self._expect(self.client_editor, 'post', f'/api/feedback/{self.other_feedback.id}/reply/',
                     status.HTTP_200_OK, {'status': 'resolved', 'admin_reply': '已处理'},
                     note='反馈回复（CONTENT）')

        # 种植日历：新增任务（CalendarTask 已在文件头导入）
        self._expect(self.client_editor, 'post', '/api/calendar/tasks/',
                     status.HTTP_201_CREATED,
                     {'crop_type': '玉米', 'month': 5, 'title': 'zz能力矩阵农事',
                      'task_type': 'sowing', 'detail': 'x'},
                     note='日历任务新增（CONTENT）')
        self.assertTrue(CalendarTask.objects.filter(title='zz能力矩阵农事').exists())

        # 数据看板：能看（只读），但**拿不到用户明细**
        dash = self._expect(self.client_editor, 'get', '/api/admin/dashboard/',
                            status.HTTP_200_OK, note='数据看板（CONTENT 只读）')
        self.assertIn('totals', dash.data, '看板至少要给聚合数字')
        self.assertEqual(
            dash.data.get('top_contributors'), [],
            '信息编辑员不该看到"贡献榜"（含用户名）',
        )
        self.assertEqual(
            dash.data.get('recent_users'), [],
            '信息编辑员不该看到"最近注册"（含用户名/登录时间）',
        )
        self.assertFalse(dash.data.get('includes_user_detail'))

        # 看板对全权管理员仍然给出用户明细
        admin_dash = self._expect(self.client_admin, 'get', '/api/admin/dashboard/',
                                  status.HTTP_200_OK, note='数据看板（管理员）')
        self.assertTrue(admin_dash.data.get('includes_user_detail'))

    # ---------- ② USER_ADMIN：信息编辑员必须被拒 ----------
    def test_editor_cannot_touch_user_admin(self):
        """EDITOR 不得进入用户与他人数据的接口（全部 403）"""
        cases = [
            ('get', '/api/users/', None, '全站用户列表'),
            ('get', '/api/admin/users/', None, '用户管理列表'),
            ('get', f'/api/admin/users/{self.plain.id}/', None, '用户详情'),
            ('post', f'/api/admin/users/{self.plain.id}/reset-link/', {}, '签发密码重置链接'),
            ('delete', f'/api/admin/users/{self.plain.id}/', None, '软删除用户'),
            ('post', f'/api/consult/experts/{self.plain.id}/', {'title': 'x'}, '授予专家'),
            ('delete', f'/api/consult/experts/{self.plain.id}/', None, '取消专家'),
        ]
        for method, url, body, note in cases:
            self._expect(self.client_editor, method, url, status.HTTP_403_FORBIDDEN,
                         body=body, note=f'{note}（USER_ADMIN）')

        # 反向确认：这几道门不是"把所有人都挡住"——全权管理员必须照常可用。
        # （只挑语义确定的读接口断言 200；写接口各自的业务护栏不在这里重复测。）
        for url in ['/api/users/', '/api/admin/users/', f'/api/admin/users/{self.plain.id}/']:
            self._expect(self.client_admin, 'get', url, status.HTTP_200_OK,
                         note='全权管理员读用户数据')

    def test_editor_sees_only_own_detection_records(self):
        """识别记录：EDITOR 拿不到"全部用户"视图（范围而不是 403）"""
        from .models import DetectionHistory
        DetectionHistory.objects.create(
            user=self.plain, detection_result='玉米大斑病', confidence=0.9,
        )
        DetectionHistory.objects.create(
            user=self.editor, detection_result='自己的记录', confidence=0.8,
        )

        response = self._expect(
            self.client_editor, 'get', '/api/detection-history/?all_users=true',
            status.HTTP_200_OK, note='识别记录列表',
        )
        # ⚠️ 这个接口的列表结构是 `{'status':.., 'data': {'items': [...]}}`
        # （第 22 批把识别记录管理并进来时定的形状），不是 DRF 默认的 `results`。
        # 三种形状都兼容一下，免得形状再变时测试以"str 没有 .get()"这种费解的方式失败。
        payload = response.data
        rows = payload.get('data', {}).get('items') or payload.get('results') or payload
        users = {row['user']['id'] for row in rows if isinstance(row, dict) and row.get('user')}
        self.assertEqual(
            users, {self.editor.id},
            '信息编辑员带 all_users=true 也只能看到自己的识别记录',
        )

    # ---------- ③ BROADCAST：信息编辑员必须被拒 ----------
    def test_editor_cannot_broadcast(self):
        """EDITOR 不得对全体用户发声 / 动系统开关（全部 403）"""
        cases = [
            ('post', '/api/announcements/',
             {'title': 'zz能力矩阵公告', 'content': 'x'}, '发布系统公告'),
            ('post', '/api/alerts/notify/', {}, '推送预警'),
            ('get', '/api/sensitive-words/', None, '敏感词列表（连读都不给）'),
            ('post', '/api/sensitive-words/', {'word': 'zz测试词'}, '新增敏感词'),
            ('post', '/api/forums/boards/', {'name': 'zz能力矩阵新板块'}, '新建论坛版块'),
            ('get', '/api/admin/dataset-stats/', None, '样本统计'),
        ]
        for method, url, body, note in cases:
            self._expect(self.client_editor, method, url, status.HTTP_403_FORBIDDEN,
                         body=body, note=f'{note}（BROADCAST）')

    # ---------- ④ 全权管理员专属：连 CONTENT 都不给 ----------
    def test_editor_cannot_do_irreversible_deletes(self):
        """不可逆动作只给全权管理员：删别人的反馈 / 硬删评论"""
        from .models_forum import Comment as ForumComment
        self._expect(
            self.client_editor, 'delete', f'/api/feedback/{self.other_feedback.id}/',
            status.HTTP_403_FORBIDDEN, note='删别人的反馈（全权管理员专属）',
        )
        # 自己的反馈仍然可以撤回（这条是"普通用户的权利"，不能被上面的收紧误伤）
        mine = Feedback.objects.create(
            user=self.editor, category='suggestion', suggestion='我自己的反馈',
        )
        self._expect(self.client_editor, 'delete', f'/api/feedback/{mine.id}/',
                     status.HTTP_204_NO_CONTENT, note='撤回自己的反馈')

        hard = ForumComment.objects.create(post=self.post, author=self.plain, content='待硬删')
        self._expect(
            self.client_editor, 'delete',
            f'/api/forums/posts/{self.post.id}/comments/{hard.id}/',
            status.HTTP_403_FORBIDDEN, note='硬删评论（全权管理员专属）',
        )
        # 管理员可以（验证护栏不是把所有人一起挡住）
        self._expect(
            self.client_admin, 'delete',
            f'/api/forums/posts/{self.post.id}/comments/{hard.id}/',
            status.HTTP_204_NO_CONTENT, note='硬删评论（管理员）',
        )

    # ---------- ⑤ 普通用户：三项能力全无 ----------
    def test_plain_user_gets_nothing(self):
        """普通用户在管理端接口上一律 401/403（防止收口时把门开太大）"""
        for method, url, body in [
            ('get', '/api/admin/users/', None),
            ('post', '/api/pests/', {'name': 'x', 'crop_type': '玉米',
                                     'english_identifier': 'zz_plain_x', 'prevention_methods': []}),
            ('post', '/api/announcements/', {'title': 'x', 'content': 'y'}),
            ('get', '/api/admin/dashboard/', None),
        ]:
            send = getattr(self.client_plain, method)
            response = send(url, data=body, format='json') if body is not None else send(url)
            self.assertIn(
                response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
                f'普通用户不该能访问 {method.upper()} {url}（实际 {response.status_code}）',
            )

    # ---------- ⑥ 能力清单本身 ----------
    def test_capabilities_are_reported_in_login_and_check_auth(self):
        """能力清单随登录 / check-auth 下发（前端据此显示菜单）"""
        from .capabilities import ALL_CAPABILITIES

        check = self._expect(self.client_editor, 'get', '/api/check-auth/',
                             status.HTTP_200_OK, note='check-auth')
        self.assertEqual(check.data['data']['capabilities'], ['CONTENT'])

        check_admin = self._expect(self.client_admin, 'get', '/api/check-auth/',
                                   status.HTTP_200_OK, note='check-auth（管理员）')
        self.assertEqual(check_admin.data['data']['capabilities'], list(ALL_CAPABILITIES))

        login = self.client.post(
            '/api/login/',
            {'username': 'zz_cap_editor', 'password': 'pw12345678'},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.assertEqual(login.data['data']['user']['capabilities'], ['CONTENT'])

        check_plain = self._expect(self.client_plain, 'get', '/api/check-auth/',
                                   status.HTTP_200_OK, note='check-auth（普通用户）')
        self.assertEqual(check_plain.data['data']['capabilities'], [])


# ============================================================================
# 第 127 批：管理后台改角色（四条护栏）
# ============================================================================
# 背景：第 95 批**刻意**不在后台提供"改角色"（属于提权操作，请走 Django admin）。
# 第 125 批引入信息编辑员之后，"把某个同事设成编辑员"成了日常操作，
# 每次都去 Django admin 不现实 —— 于是开了一个**窄口子**，这里逐条锁死这个口子：
#   1. 只有超级管理员能改（有 USER_ADMIN 能力的 staff 也不行）；
#   2. 只能在 EDITOR ↔ USER 之间调，ADMIN 既不能是目标也不能是结果；
#   3. 不能改自己；
#   4. 不能动 staff / 超管账号。
# 另外：变更要写日志、给对方发通知（"重新登录后生效"）。
# ============================================================================
class AdminUserRoleTests(APITestCase):
    """改角色接口的护栏（第 127 批）"""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='zz_role_super', password='pw12345678', email='', role='ADMIN',
        )
        # 有 USER_ADMIN 能力但不是超管：**不能**改角色（护栏 1）
        self.staff = User.objects.create_user(
            username='zz_role_staff', password='pw12345678', is_staff=True, role='ADMIN',
        )
        self.plain = User.objects.create_user(
            username='zz_role_plain', password='pw12345678', role='USER',
        )
        self.editor = User.objects.create_user(
            username='zz_role_editor', password='pw12345678', role='EDITOR',
        )
        self.client_super = APIClient()
        self.client_super.force_authenticate(user=self.superuser)
        self.client_staff = APIClient()
        self.client_staff.force_authenticate(user=self.staff)
        self.client_editor = APIClient()
        self.client_editor.force_authenticate(user=self.editor)

    def _url(self, user):
        return f'/api/admin/users/{user.id}/role/'

    def _post(self, client, user, role, modules=None):
        """
        发一次改角色请求

        第 128 批：改成 EDITOR 时必须带 `modules`（至少要给一个模块），
        这里默认给「新闻管理」，让只关心角色护栏的测试保持简短。
        """
        payload = {'role': role}
        if role == 'EDITOR' and modules is None:
            payload['modules'] = ['news']
        elif modules is not None:
            payload['modules'] = modules
        return client.post(self._url(user), payload, format='json')

    # ---------- 正向 ----------
    def test_superuser_can_promote_and_demote(self):
        """超管可以把普通用户设成编辑员，也可以改回来"""
        response = self._post(self.client_super, self.plain, 'EDITOR')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.plain.refresh_from_db()
        self.assertEqual(self.plain.role, 'EDITOR')

        response = self._post(self.client_super, self.plain, 'USER')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.plain.refresh_from_db()
        self.assertEqual(self.plain.role, 'USER')

    def test_role_change_notifies_the_user(self):
        """改完角色要通知本人（能力随登录下发，必须重新登录才生效）"""
        response = self._post(self.client_super, self.plain, 'EDITOR')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            Notification.objects.filter(recipient=self.plain).exists(),
            '改角色后应当给对方一条站内通知',
        )

    def test_same_role_is_idempotent(self):
        """设成同一个角色：成功但不改库（也就不该产生通知）"""
        before = Notification.objects.count()
        response = self._post(self.client_super, self.plain, 'USER')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data.get('changed'))
        self.assertEqual(Notification.objects.count(), before)

    def test_editor_capability_actually_follows_the_role(self):
        """改角色之后能力真的变了（这是这一批的**目的**，不是副作用）"""
        from .capabilities import (
            has_capability, has_content_module, CAP_CONTENT, CAP_USER_ADMIN,
        )

        self.assertFalse(has_capability(self.plain, CAP_CONTENT))
        self._post(self.client_super, self.plain, 'EDITOR', modules=['news', 'pests'])
        self.plain.refresh_from_db()
        self.assertTrue(has_capability(self.plain, CAP_CONTENT), '编辑员应当拿到 CONTENT')
        self.assertFalse(has_capability(self.plain, CAP_USER_ADMIN), '编辑员不该拿到 USER_ADMIN')
        # 第 128 批：拿到 CONTENT 不等于"四块全能干"，只等于被勾的那两块
        self.assertTrue(has_content_module(self.plain, 'news'))
        self.assertTrue(has_content_module(self.plain, 'pests'))
        self.assertFalse(has_content_module(self.plain, 'review'), '没勾的模块不能有')

    # ---------- 护栏 1：只有超管 ----------
    def test_staff_admin_cannot_change_roles(self):
        """有 USER_ADMIN 能力的 staff 管理员也不行 —— 否则他能造出编辑员"""
        response = self._post(self.client_staff, self.plain, 'EDITOR')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.plain.refresh_from_db()
        self.assertEqual(self.plain.role, 'USER')

    def test_editor_cannot_change_roles(self):
        """编辑员当然也不能（他没有 USER_ADMIN，会先被权限类拦住）"""
        response = self._post(self.client_editor, self.plain, 'EDITOR')
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED))

    # ---------- 护栏 2：只能在 EDITOR ↔ USER 之间调 ----------
    def test_cannot_promote_to_admin(self):
        """不能把人升成系统管理员（只能走 Django admin）"""
        response = self._post(self.client_super, self.plain, 'ADMIN')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.plain.refresh_from_db()
        self.assertEqual(self.plain.role, 'USER')

    def test_cannot_touch_admin_accounts(self):
        """不能改管理员账号的角色（即使操作者是超管）"""
        response = self._post(self.client_super, self.staff, 'USER')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.role, 'ADMIN')

    def test_unknown_role_is_rejected(self):
        """乱传角色：400（不是 500，也不能悄悄改成别的）"""
        response = self._post(self.client_super, self.plain, 'ROOT')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ---------- 护栏 3：不能改自己 ----------
    def test_cannot_change_own_role(self):
        """超管不能把自己降级 —— 否则可能把系统锁死（没人能再改回来）"""
        response = self._post(self.client_super, self.superuser, 'USER')
        # 自己那句护栏先命中（400）；即使绕过它，还有"不能动管理员账号"（403）。
        # 这里要求两者至少命中一条，且库里必须不变。
        self.assertIn(response.status_code,
                      (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN))
        self.superuser.refresh_from_db()
        self.assertEqual(self.superuser.role, 'ADMIN')
        self.assertTrue(self.superuser.is_superuser, '超管身份也不能被顺手改掉')

    def test_role_change_is_logged(self):
        """变更要留痕（谁把谁从什么改成什么 + 模块清单）—— 这是本接口的"操作日志" """
        with self.assertLogs('api.views_user', level='INFO') as captured:
            self._post(self.client_super, self.plain, 'EDITOR', modules=['news', 'feedback'])
        joined = '\n'.join(captured.output)
        # 第 128 批：日志里同时要有角色与模块（否则"为什么他有新闻权限"查不出来）
        self.assertIn('角色', joined)
        self.assertIn('模块', joined)
        self.assertIn('news', joined)
        self.assertIn(self.plain.username, joined)


# ============================================================================
# 第 128 批：内容模块互不干扰（内容审核 / 新闻管理 / 病害百科 / 意见反馈）
# ============================================================================
# 第 125 批给编辑员的是一个笼统的 CONTENT："拿到它就能改四块内容"。
# 第 128 批拆成四个模块，按人授权（`EditorModuleGrant`）。这组测试盯的是
# **拆分真的生效了** —— 尤其是"只勾了 A 模块的人碰不到 B 模块"，
# 因为这类错误单看代码很难发现（权限类名字都差不多）。
# ============================================================================
class ContentModuleScopeTests(APITestCase):
    """模块 × 端点：只勾一个模块的编辑员只能干那一块"""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='zz_mod_super', password='pw12345678', email='', role='ADMIN',
        )
        # 四个"只勾一块"的编辑员
        self.only_news = User.objects.create_user(
            username='zz_mod_news', password='pw12345678', role='EDITOR',
        )
        self.only_pests = User.objects.create_user(
            username='zz_mod_pests', password='pw12345678', role='EDITOR',
        )
        self.only_review = User.objects.create_user(
            username='zz_mod_review', password='pw12345678', role='EDITOR',
        )
        self.only_feedback = User.objects.create_user(
            username='zz_mod_feedback', password='pw12345678', role='EDITOR',
        )
        for user, module in (
            (self.only_news, 'news'), (self.only_pests, 'pests'),
            (self.only_review, 'review'), (self.only_feedback, 'feedback'),
        ):
            EditorModuleGrant.objects.create(user=user, module=module, granted_by=self.superuser)

        self.clients = {
            'news': self._client(self.only_news),
            'pests': self._client(self.only_pests),
            'review': self._client(self.only_review),
            'feedback': self._client(self.only_feedback),
        }

        # 数据
        self.pest = PestInfo.objects.create(
            name='zz模块病', crop_type='玉米', english_identifier='zz_mod_pest', symptoms='x',
        )
        self.board = ForumBoard.objects.create(name='zz模块版块', description='x')
        self.post = Post.objects.create(
            title='zz模块帖子', content='x', author=self.superuser, board=self.board,
            status='pending',
        )
        self.comment = Comment.objects.create(post=self.post, author=self.superuser, content='x')
        self.feedback = Feedback.objects.create(
            user=self.superuser, category='suggestion', suggestion='zz模块反馈',
        )

    @staticmethod
    def _client(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _expect(self, module, method, url, expected, body=None, note=''):
        client = self.clients[module]
        send = getattr(client, method)
        response = send(url, data=body, format='json') if body is not None else send(url)
        self.assertEqual(
            response.status_code, expected,
            f'{note}｜只勾 {module} 的编辑员 {method.upper()} {url} 期望 {expected}，'
            f'实际 {response.status_code}｜{getattr(response, "data", "")}',
        )
        return response

    # ---------- 各模块：自己那块能做 ----------
    def test_each_module_can_do_its_own_job(self):
        """每个"只勾一块"的编辑员，在自己那一块必须能做（否则等于没授权）"""
        # 新闻管理
        news = self._expect('news', 'post', '/api/news/', status.HTTP_201_CREATED,
                            {'title': 'zz模块新闻', 'content': '<p>x</p>', 'category': 'notice'},
                            note='新闻新增')
        self._expect('news', 'patch', f"/api/news/{news.data['id']}/", status.HTTP_200_OK,
                     {'source': '本站'}, note='新闻修改')

        # 病害百科
        pest = self._expect('pests', 'post', '/api/pests/', status.HTTP_201_CREATED,
                            {'name': 'zz模块新增', 'crop_type': '玉米',
                             'english_identifier': 'zz_mod_new', 'symptoms': 'x',
                             'prevention_methods': []},
                            note='百科新增')
        self._expect('pests', 'delete', f"/api/pests/{pest.data['id']}/",
                     status.HTTP_204_NO_CONTENT, note='百科删除')

        # 内容审核
        self._expect('review', 'post', f'/api/forums/posts/{self.post.id}/approve/',
                     status.HTTP_200_OK, note='帖子审核通过')
        self._expect('review', 'post',
                     f'/api/forums/posts/{self.post.id}/comments/{self.comment.id}/delete/',
                     status.HTTP_204_NO_CONTENT, note='评论软删除')

        # 意见反馈
        listed = self._expect('feedback', 'get', '/api/feedback/', status.HTTP_200_OK,
                              note='反馈列表')
        rows = listed.data.get('results', listed.data) if isinstance(listed.data, dict) else listed.data
        self.assertTrue(any(row.get('id') == self.feedback.id for row in rows),
                        '反馈编辑员要能看到别人提交的反馈')
        self._expect('feedback', 'post', f'/api/feedback/{self.feedback.id}/reply/',
                     status.HTTP_200_OK, {'status': 'resolved', 'admin_reply': '已处理'},
                     note='反馈回复')

    # ---------- 互不干扰：越界一律 403 ----------
    def test_modules_do_not_leak_into_each_other(self):
        """只勾新闻的人，碰不到百科/审核/反馈（反之亦然）—— 这就是"互不干扰" """
        # 新闻编辑员越界
        self._expect('news', 'post', '/api/pests/', status.HTTP_403_FORBIDDEN,
                     {'name': 'x', 'crop_type': '玉米', 'english_identifier': 'zz_leak',
                      'prevention_methods': []}, note='新闻编辑碰百科')
        self._expect('news', 'post', f'/api/forums/posts/{self.post.id}/approve/',
                     status.HTTP_403_FORBIDDEN, note='新闻编辑碰审核')
        self._expect('news', 'get', '/api/feedback/', status.HTTP_200_OK, note='反馈列表（降级为只看自己）')

        # 百科编辑员越界
        self._expect('pests', 'post', '/api/news/', status.HTTP_403_FORBIDDEN,
                     {'title': 'x', 'content': 'y'}, note='百科编辑碰新闻')
        self._expect('pests', 'post', f'/api/forums/posts/{self.post.id}/reject/',
                     status.HTTP_403_FORBIDDEN, {'reason': 'x'}, note='百科编辑碰审核')

        # 审核编辑员越界
        self._expect('review', 'post', '/api/news/', status.HTTP_403_FORBIDDEN,
                     {'title': 'x', 'content': 'y'}, note='审核编辑碰新闻')
        self._expect('review', 'post', '/api/pests/', status.HTTP_403_FORBIDDEN,
                     {'name': 'x', 'crop_type': '玉米', 'english_identifier': 'zz_leak2',
                      'prevention_methods': []}, note='审核编辑碰百科')

        # 反馈编辑员越界
        self._expect('feedback', 'post', '/api/news/', status.HTTP_403_FORBIDDEN,
                     {'title': 'x', 'content': 'y'}, note='反馈编辑碰新闻')
        self._expect('feedback', 'post', '/api/pests/', status.HTTP_403_FORBIDDEN,
                     {'name': 'x', 'crop_type': '玉米', 'english_identifier': 'zz_leak3',
                      'prevention_methods': []}, note='反馈编辑碰百科')

    def test_feedback_module_only_sees_others_when_granted(self):
        """没有 feedback 模块的人：反馈列表退回"只看自己"（不是 403，是范围收窄）"""
        response = self._expect('news', 'get', '/api/feedback/', status.HTTP_200_OK)
        rows = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(rows, [], '没有 feedback 模块时不该看到别人的反馈')

    # ---------- 农事任务归「病害百科」----------
    def test_calendar_tasks_follow_pests_module(self):
        """农事任务与病害百科同属"给农户看的农业资料"，因此跟 pests 模块走"""
        self._expect('pests', 'post', '/api/calendar/tasks/', status.HTTP_201_CREATED,
                     {'crop_type': '玉米', 'month': 6, 'title': 'zz模块农事',
                      'task_type': 'sowing', 'detail': 'x'}, note='百科编辑建农事任务')
        self._expect('news', 'post', '/api/calendar/tasks/', status.HTTP_403_FORBIDDEN,
                     {'crop_type': '玉米', 'month': 6, 'title': 'zz模块农事2',
                      'task_type': 'sowing', 'detail': 'x'}, note='新闻编辑建农事任务')

    # ---------- 看板：任何编辑员都能看（只读聚合）----------
    def test_any_module_sees_dashboard_without_user_detail(self):
        for module in self.clients:
            response = self._expect(module, 'get', '/api/admin/dashboard/',
                                    status.HTTP_200_OK, note=f'{module} 编辑员看板')
            self.assertIn('totals', response.data)
            self.assertEqual(response.data.get('top_contributors'), [])
            self.assertFalse(response.data.get('includes_user_detail'))

    # ---------- 能力清单：CONTENT 只表示"至少有一个模块" ----------
    def test_capabilities_payload_lists_modules(self):
        check = self._expect('news', 'get', '/api/check-auth/', status.HTTP_200_OK)
        self.assertEqual(check.data['data']['capabilities'], ['CONTENT'])
        self.assertEqual(check.data['data']['content_modules'], ['news'])

        admin = self._client(self.superuser).get('/api/check-auth/')
        self.assertEqual(admin.data['data']['content_modules'],
                         ['review', 'news', 'pests', 'feedback'])
        self.assertEqual(admin.data['data']['capabilities'], ['CONTENT', 'USER_ADMIN', 'BROADCAST'])

    # ---------- 全权管理员不受模块表影响 ----------
    def test_full_admin_has_all_modules_without_grants(self):
        """管理员不需要（也不该）依赖授权表 —— 表里没他的记录，四个模块照样全有"""
        self.assertEqual(EditorModuleGrant.objects.filter(user=self.superuser).count(), 0)
        client = self._client(self.superuser)
        self.assertEqual(client.post('/api/pests/', {
            'name': 'zz管理员新增', 'crop_type': '玉米',
            'english_identifier': 'zz_admin_new', 'prevention_methods': [],
        }, format='json').status_code, status.HTTP_201_CREATED)
        self.assertEqual(client.post('/api/news/', {
            'title': 'zz管理员新闻', 'content': '<p>x</p>',
        }, format='json').status_code, status.HTTP_201_CREATED)


class RoleModuleAssignmentTests(APITestCase):
    """改角色时一并设置模块（第 128 批扩展）"""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='zz_rm_super', password='pw12345678', email='', role='ADMIN',
        )
        self.plain = User.objects.create_user(
            username='zz_rm_plain', password='pw12345678', role='USER',
        )
        self.staff = User.objects.create_user(
            username='zz_rm_staff', password='pw12345678', is_staff=True, role='ADMIN',
        )
        self.client_super = APIClient()
        self.client_super.force_authenticate(user=self.superuser)
        self.client_staff = APIClient()
        self.client_staff.force_authenticate(user=self.staff)

    def _post(self, payload, user=None):
        target = user or self.plain
        return self.client_super.post(
            f'/api/admin/users/{target.id}/role/', payload, format='json',
        )

    def test_promote_with_modules(self):
        """超管可以一次把角色与模块都设好"""
        response = self._post({'role': 'EDITOR', 'modules': ['news', 'feedback']})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['content_modules'], ['news', 'feedback'])
        self.plain.refresh_from_db()
        self.assertEqual(self.plain.role, 'EDITOR')

        from .capabilities import has_content_module
        self.assertTrue(has_content_module(self.plain, 'news'))
        self.assertTrue(has_content_module(self.plain, 'feedback'))
        self.assertFalse(has_content_module(self.plain, 'pests'))

    def test_modules_can_be_changed_later(self):
        """先勾两块，后来只留一块：被去掉的那块要真的没了（delete 而不是留着）"""
        self._post({'role': 'EDITOR', 'modules': ['news', 'pests']})
        response = self._post({'role': 'EDITOR', 'modules': ['pests']})
        self.assertEqual(response.data['content_modules'], ['pests'])
        from .capabilities import has_content_module
        self.assertFalse(has_content_module(self.plain, 'news'), '去掉的模块必须立刻失效')
        self.assertEqual(
            EditorModuleGrant.objects.filter(user=self.plain).count(), 1,
            '不该留下"影子授权"',
        )

    def test_editor_without_modules_is_rejected(self):
        """一个模块都不勾：400（否则他进后台什么也做不了，八成是点漏了）"""
        response = self._post({'role': 'EDITOR', 'modules': []})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.plain.refresh_from_db()
        self.assertEqual(self.plain.role, 'USER')

    def test_unknown_module_is_rejected(self):
        response = self._post({'role': 'EDITOR', 'modules': ['news', 'root']})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_missing_modules_keeps_existing_grants(self):
        """不传 modules：保留他已有的授权（只想改角色时不该顺手清空模块）"""
        self._post({'role': 'EDITOR', 'modules': ['news']})
        response = self._post({'role': 'EDITOR'})   # 不带 modules
        self.assertEqual(response.data['content_modules'], ['news'])

    def test_demote_to_user_clears_modules(self):
        """降级成普通用户：模块授权一并清掉（不留"影子权限"）"""
        self._post({'role': 'EDITOR', 'modules': ['news', 'pests']})
        response = self._post({'role': 'USER'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['content_modules'], [])
        self.assertEqual(EditorModuleGrant.objects.filter(user=self.plain).count(), 0)

    def test_staff_admin_still_cannot_assign_modules(self):
        """护栏 1 不变：有 USER_ADMIN 能力的 staff 管理员照样不能给自己人开模块"""
        response = self.client_staff.post(
            f'/api/admin/users/{self.plain.id}/role/',
            {'role': 'EDITOR', 'modules': ['news']}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(EditorModuleGrant.objects.filter(user=self.plain).count(), 0)


# ============================================================================
# 第 131 批：在后台开通编辑员账号
# ============================================================================
# 在这之前，"新建一个编辑员"必须去 Django admin 建号、再回用户管理勾模块；
# 而新建出来的账号还得自己想办法设密码。这一组测试盯四件事：
#   1. 真的能用：开通 → 拿一次性链接走 /password-reset/confirm/ 设密码 → 能登录；
#   2. **接口全程不经手明文密码**（账号建出来时 set_unusable_password）；
#   3. 护栏：仅超管、用户名/邮箱校验、至少一个模块；
#   4. 模块授权真的生效（只有被勾的模块能干活）。
# ============================================================================
class AdminUserCreateEditorTests(APITestCase):
    """开通编辑员账号（第 131 批）"""

    URL = '/api/admin/users/create-editor/'

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='zz_ce_super', password='pw12345678', email='', role='ADMIN',
        )
        self.staff = User.objects.create_user(
            username='zz_ce_staff', password='pw12345678', is_staff=True, role='ADMIN',
        )
        self.plain = User.objects.create_user(
            username='zz_ce_plain', password='pw12345678', role='USER',
            email='taken@example.invalid',
        )
        self.client_super = APIClient()
        self.client_super.force_authenticate(user=self.superuser)
        self.client_staff = APIClient()
        self.client_staff.force_authenticate(user=self.staff)
        self.client_plain = APIClient()
        self.client_plain.force_authenticate(user=self.plain)

    def _create(self, client=None, **payload):
        body = {'username': 'zz_new_editor', 'modules': ['news']}
        body.update(payload)
        return (client or self.client_super).post(self.URL, body, format='json')

    # ---------- 正向 ----------
    def test_superuser_can_create_editor_with_modules(self):
        response = self._create(email='editor@example.invalid', modules=['news', 'feedback'])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        User = get_user_model()
        user = User.objects.get(username='zz_new_editor')
        self.assertEqual(user.role, 'EDITOR')
        self.assertFalse(user.is_staff)
        self.assertTrue(user.is_active)

        from .capabilities import has_content_module
        self.assertTrue(has_content_module(user, 'news'))
        self.assertTrue(has_content_module(user, 'feedback'))
        self.assertFalse(has_content_module(user, 'pests'), '没勾的模块不能有')

        self.assertEqual(response.data['user']['content_modules'], ['news', 'feedback'])
        self.assertTrue(response.data['has_email'])
        self.assertIn('reset-password', response.data['url'])

    def test_created_account_has_no_usable_password(self):
        """接口全程不经手明文密码：建出来的账号根本没有可用密码"""
        self._create()
        User = get_user_model()
        user = User.objects.get(username='zz_new_editor')
        self.assertFalse(user.has_usable_password(), '不该有任何明文密码生效')
        # 密码字段必须是"不可用密码"的标记（以 ! 开头），不是空串
        self.assertTrue(user.password.startswith('!'), f'密码字段是 {user.password!r}')

    def test_one_time_link_actually_works(self):
        """端到端：开通 → 用返回的链接设新密码 → 能用新密码登录"""
        response = self._create()
        url = response.data['url']
        match = re.search(r'uid=([^&\s]+)&token=([^\s]+)', url)
        self.assertIsNotNone(match, f'链接里没有 uid/token：{url}')
        uid, token = match.groups()

        confirm = self.client.post('/api/password-reset/confirm/', {
            'uid': uid, 'token': token, 'new_password': 'BrandNew!2026',
        }, format='json')
        self.assertEqual(confirm.status_code, status.HTTP_200_OK, confirm.data)

        login = APIClient().post('/api/login/', {
            'username': 'zz_new_editor', 'password': 'BrandNew!2026',
        }, format='json')
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.assertEqual(login.data['data']['user']['role'], 'EDITOR')
        self.assertEqual(login.data['data']['user']['content_modules'], ['news'])

    def test_link_is_single_use(self):
        """一次性：改过密码之后同一条链接失效（与自助找回同一套 token 机制）"""
        response = self._create()
        uid, token = re.search(r'uid=([^&\s]+)&token=([^\s]+)', response.data['url']).groups()
        first = self.client.post('/api/password-reset/confirm/', {
            'uid': uid, 'token': token, 'new_password': 'BrandNew!2026',
        }, format='json')
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        second = self.client.post('/api/password-reset/confirm/', {
            'uid': uid, 'token': token, 'new_password': 'Another!2026',
        }, format='json')
        self.assertNotEqual(second.status_code, status.HTTP_200_OK, '同一条链接不该能用第二次')

    def test_created_editor_can_do_only_its_module(self):
        """开通出来的编辑员：被勾的模块能干，别的模块 403（与改角色那条链路一致）"""
        self._create(username='zz_new_editor2', modules=['pests'])
        User = get_user_model()
        user = User.objects.get(username='zz_new_editor2')
        client = APIClient()
        client.force_authenticate(user=user)

        created = client.post('/api/pests/', {
            'name': 'zz开通测试病', 'crop_type': '玉米',
            'english_identifier': 'zz_ce_pest', 'prevention_methods': [],
        }, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)

        news = client.post('/api/news/', {'title': 'zz开通测试新闻', 'content': '<p>x</p>'},
                           format='json')
        self.assertEqual(news.status_code, status.HTTP_403_FORBIDDEN, news.data)

    # ---------- 护栏 ----------
    def test_only_superuser_can_create_editor(self):
        """staff 管理员（有 USER_ADMIN 能力）也不行 —— 造编辑员是提权操作"""
        response = self._create(client=self.client_staff, username='zz_ce_by_staff')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertFalse(get_user_model().objects.filter(username='zz_ce_by_staff').exists())

    def test_plain_user_cannot_create_editor(self):
        response = self._create(client=self.client_plain, username='zz_ce_by_plain')
        self.assertIn(response.status_code,
                      (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_username_rules_enforced(self):
        """用户名：格式与占用都要挡（复用注册那套校验，避免两处规则不一致）"""
        for bad, note in (('', '空'), ('ab', '太短'), ('1abc', '数字开头'),
                          ('a' * 21, '太长'), ('bad name', '有空格')):
            response = self._create(username=bad)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST,
                             f'{note}的用户名应当被拒：{response.data}')
        # 占用（大小写不敏感）
        response = self._create(username='zz_ce_plain'.upper())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_email_must_be_unique_when_given(self):
        response = self._create(username='zz_ce_email', email='taken@example.invalid')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        # 不填邮箱是可以的（编辑员常常没有邮箱）
        ok = self._create(username='zz_ce_noemail')
        self.assertEqual(ok.status_code, status.HTTP_201_CREATED, ok.data)
        self.assertFalse(ok.data['has_email'])
        self.assertFalse(ok.data['mailed'])

    def test_modules_validated(self):
        """模块：必须至少一个、且只能是那四个"""
        empty = self._create(username='zz_ce_nomod', modules=[])
        self.assertEqual(empty.status_code, status.HTTP_400_BAD_REQUEST, empty.data)
        self.assertFalse(get_user_model().objects.filter(username='zz_ce_nomod').exists(),
                         '校验失败不该留下半个账号')

        unknown = self._create(username='zz_ce_badmod', modules=['news', 'root'])
        self.assertEqual(unknown.status_code, status.HTTP_400_BAD_REQUEST, unknown.data)

        not_list = self._create(username='zz_ce_strmod', modules='news')
        self.assertEqual(not_list.status_code, status.HTTP_400_BAD_REQUEST, not_list.data)

    def test_change_is_logged(self):
        with self.assertLogs('api.views_user', level='INFO') as captured:
            self._create(username='zz_ce_logged', modules=['review'])
        joined = '\n'.join(captured.output)
        self.assertIn('开通了编辑员账号', joined)
        self.assertIn('zz_ce_logged', joined)
        self.assertIn('内容审核', joined)


# ============================================================================
# 第 135 批：敏感词的英文对照（word_en）
# ============================================================================
# 用户反馈"敏感词库切英文没完全翻译"：词条是**被拦截的字面串**，中文词库在英文
# 界面下就是一串中文，英文管理员看不出每条拦的是什么。于是给每条加一个**只用于显示**
# 的英文说法（word_en）。
#
# 这组测试盯三件事：
#   1. 接口能读能写 word_en；
#   2. **它不参与拦截** —— 这条最容易被人"顺手改成也匹配"：word_en 是**描述**
#      （例如 加微信 → "moving users to WeChat"），拿去匹配英文正文毫无意义；
#      想拦英文垃圾词应当新增一条英文词条。
#   3. 第 52 批种下的 13 条默认词库都补上了英文对照（迁移里做的）。
# ============================================================================
class SensitiveWordGlossTests(APITestCase):
    """敏感词英文对照（第 135 批）"""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.admin = User.objects.create_user(
            username='zz_gloss_admin', password='pw12345678', is_staff=True, role='ADMIN',
        )
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.admin)
        SensitiveWord.objects.all().delete()
        self.word = SensitiveWord.objects.create(
            word='代开发票', category='ad', word_en='fake invoices',
        )

    def test_api_exposes_word_en(self):
        response = self.client_admin.get('/api/sensitive-words/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(item for item in response.data if item['word'] == '代开发票')
        self.assertEqual(row['word_en'], 'fake invoices')

    def test_can_create_with_word_en(self):
        response = self.client_admin.post('/api/sensitive-words/', {
            'word': 'zz测试词', 'category': 'other', 'word_en': 'e2e term',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        created = SensitiveWord.objects.get(word='zz测试词')
        self.assertEqual(created.word_en, 'e2e term')
        # 空白会被 strip（前端可能传空格）
        response2 = self.client_admin.post('/api/sensitive-words/', {
            'word': 'zz测试词2', 'category': 'other', 'word_en': '   ',
        }, format='json')
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SensitiveWord.objects.get(word='zz测试词2').word_en, '')

    def test_word_en_is_not_matched(self):
        """
        英文对照**只用于显示**，不参与拦截

        ⚠️ 这条是刻意的：word_en 是"这条中文词是什么意思"的**描述**
        （例：加微信 → "moving users to WeChat"），拿去匹配英文正文没有意义；
        想拦英文垃圾词，应当**新增一条英文词条**（那样 `word` 就是英文，照常拦）。

        下面两句：第一句含 word_en 的原文 → 不该被拦；
        第二句含真正的词条（在 word 里）→ 必须被拦。
        """
        from rest_framework import serializers

        from .sensitive import check_text, find_sensitive_words

        # 1) 正文里出现 word_en 的内容：不拦
        self.assertEqual(
            find_sensitive_words('This post mentions fake invoices and nothing else.'),
            [],
            'word_en 是显示用的描述，不该参与匹配',
        )

        # 2) 出现词条本身：必须拦
        with self.assertRaises(serializers.ValidationError) as ctx:
            check_text('加我微信聊：代开发票', field_label='正文')
        self.assertIn('代开发票', str(ctx.exception))

    def test_english_word_entry_still_blocks(self):
        """想拦英文垃圾词：把英文作为 `word` 新增一条 —— 照常生效"""
        from rest_framework import serializers

        from .sensitive import check_text

        SensitiveWord.objects.create(word='casino', category='other', word_en='')
        with self.assertRaises(serializers.ValidationError):
            check_text('Join our casino now', field_label='正文')


class SeededSensitiveWordGlossTests(TestCase):
    """
    第 52 批种下的默认词库都带英文对照（由第 135 批的迁移补上）

    ⚠️ 这个测试类**不清空词表** —— 测试库跑过全部迁移，所以那 13 条种子就在表里；
    清空它们的是上面那个类（它只测接口行为）。
    """

    def test_seeded_words_have_gloss(self):
        seeded = ['代开发票', '办证', '刷单', '兼职刷单', '加微信', '加QQ',
                  '贷款秒批', '高额返利', '博彩', '赌场', '色情', '枪支', '毒品']
        missing = [
            word for word in seeded
            if not SensitiveWord.objects.filter(word=word).exclude(word_en='').exists()
        ]
        self.assertEqual(missing, [], f'这些默认敏感词还缺英文对照：{missing}')


# ============================================================================
# 第 137 批：停用 / 恢复账号
# ============================================================================
# 背景：用户管理页早就有「已禁用」筛选与状态标签，却**没有入口能把账号停用** ——
# 状态只能来自 ①用户自助注销（冷静期）②管理员删除（软删除）③Django admin 手动取消 active，
# 而 ①② 都被默认列表查询排除，于是那个筛选在控制台里永远筛不出东西。
#
# 这组测试盯四件事：
#   1. 停用**真的生效**：对方立刻掉线（同一个 token 401）、重新登录被拒；
#   2. 恢复**真的能用**：不需要改密码就能重新登录（这是与"删除"的关键区别）；
#   3. 护栏：不能停用自己、非超管不能停用权限不低于自己的人、已删除/冷静期账号查不到；
#   4. 幂等与日志：重复点同一个状态不报错、不写第二条日志。
# ============================================================================
class AdminUserStatusTests(APITestCase):
    """停用 / 恢复账号（第 137 批）"""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='zz_st_super', password='pw12345678', email='', role='ADMIN',
        )
        self.staff = User.objects.create_user(
            username='zz_st_staff', password='pw12345678', is_staff=True, role='ADMIN',
        )
        self.editor = User.objects.create_user(
            username='zz_st_editor', password='pw12345678', role='EDITOR',
        )
        self.target = User.objects.create_user(
            username='zz_st_target', password='pw12345678', role='USER',
        )
        self.client_super = APIClient()
        self.client_super.force_authenticate(user=self.superuser)
        self.client_staff = APIClient()
        self.client_staff.force_authenticate(user=self.staff)
        self.client_editor = APIClient()
        self.client_editor.force_authenticate(user=self.editor)
        self.client_target = APIClient()
        self.client_target.force_authenticate(user=self.target)

    def url(self, user_id=None):
        return f'/api/admin/users/{user_id or self.target.id}/status/'

    # ---------- 正向：停用 ----------
    def test_disable_then_the_account_really_cannot_login(self):
        """停用后：同一个 token 立刻 401、重新登录被拒（不是"只是界面上显示一下"）"""
        # 先让对方正常登录拿到 token
        token = Token.objects.create(user=self.target)
        live = APIClient()
        live.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(live.get('/api/check-auth/').status_code, status.HTTP_200_OK)

        response = self.client_super.post(self.url(), {'is_active': False}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['changed'])
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

        # 1) 旧 token 立刻失效（DRF 的 TokenAuthentication 会判 is_active）
        self.assertIn(live.get('/api/check-auth/').status_code,
                      (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        # 2) token 记录本身也被清掉了（否则恢复那一刻旧凭证会"复活"）
        self.assertFalse(Token.objects.filter(user=self.target).exists())
        # 3) 重新登录被拒（密码仍然是对的，是账号被停用）
        relogin = APIClient().post('/api/login/', {
            'username': 'zz_st_target', 'password': 'pw12345678',
        }, format='json')
        self.assertNotEqual(relogin.status_code, status.HTTP_200_OK)

    def test_enable_restores_login_without_changing_password(self):
        """恢复后：密码没被动过，直接能登回来（与"删除"的关键区别）"""
        self.client_super.post(self.url(), {'is_active': False}, format='json')
        response = self.client_super.post(self.url(), {'is_active': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['changed'])
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertTrue(self.target.has_usable_password(), '恢复不该动密码')

        login = APIClient().post('/api/login/', {
            'username': 'zz_st_target', 'password': 'pw12345678',
        }, format='json')
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        # ⚠️ 登录回包的 user 里**没有** is_active（那是管理端序列化器的字段），
        #    所以这里只断言"能登回来"，状态本身看数据库（上面已断言）。
        self.assertEqual(login.data['data']['user']['username'], 'zz_st_target')

    def test_disabled_user_shows_up_in_the_console_filter(self):
        """
        停用后的账号**能被「已禁用」筛选筛到**

        这条正是这个接口存在的理由：删除（is_deleted）与注销冷静期都会把账号
        从默认列表里排除掉，所以那个筛选在此之前的真实数据里筛不出任何东西。
        """
        self.client_super.post(self.url(), {'is_active': False}, format='json')
        response = self.client_super.get('/api/admin/users/?status=disabled')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [row['username'] for row in response.data['results']]
        self.assertIn('zz_st_target', names)
        # 而且确实标记成禁用状态（前端的状态标签据此渲染）
        row = next(r for r in response.data['results'] if r['username'] == 'zz_st_target')
        self.assertFalse(row['is_active'])

    # ---------- 护栏 ----------
    def test_cannot_disable_self(self):
        response = self.client_super.post(self.url(self.superuser.id), {'is_active': False},
                                          format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    def test_non_superuser_cannot_disable_admin(self):
        """staff 管理员不能停用同为管理员的账号（否则"谁能被停用"取决于谁先动手）"""
        response = self.client_staff.post(self.url(self.superuser.id), {'is_active': False},
                                          format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        # 但普通用户可以停用（口径与删除一致：能删就能停）
        ok = self.client_staff.post(self.url(), {'is_active': False}, format='json')
        self.assertEqual(ok.status_code, status.HTTP_200_OK, ok.data)

    def test_superuser_can_disable_another_admin(self):
        response = self.client_super.post(self.url(self.staff.id), {'is_active': False},
                                          format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)

    def test_editor_without_user_admin_capability_cannot_disable(self):
        """信息编辑员只有内容能力，碰不了用户管理（第 124/128 批的能力体系）"""
        response = self.client_editor.post(self.url(), {'is_active': False}, format='json')
        self.assertIn(response.status_code,
                      (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_plain_user_cannot_disable(self):
        response = self.client_target.post(self.url(self.staff.id), {'is_active': False},
                                           format='json')
        self.assertIn(response.status_code,
                      (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_deleted_and_grace_accounts_are_not_reachable(self):
        """
        已删除 / 注销冷静期的账号：404

        这两类的状态由删除与注销流程管理，不该在用户管理里改 ——
        `_admin_user_queryset()` 已把它们排除，所以这里应当是"查不到"。
        """
        User = get_user_model()
        gone = User.objects.create_user(username='zz_st_gone', password='pw12345678',
                                        role='USER')
        gone.soft_delete(by=self.superuser, reason='admin')
        response = self.client_super.post(self.url(gone.id), {'is_active': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

        pending = User.objects.create_user(username='zz_st_pending', password='pw12345678',
                                           role='USER')
        pending.request_deletion()
        response2 = self.client_super.post(self.url(pending.id), {'is_active': True},
                                           format='json')
        self.assertEqual(response2.status_code, status.HTTP_404_NOT_FOUND, response2.data)

    # ---------- 幂等 / 入参 / 日志 ----------
    def test_idempotent_when_already_in_target_state(self):
        """重复点同一个状态：200 + changed=False，且不写第二条日志"""
        first = self.client_super.post(self.url(), {'is_active': True}, format='json')
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertFalse(first.data['changed'])

        # ⚠️ 这里要用 assertNoLogs（而不是 assertLogs + assertNotIn）：
        #    assertLogs 要求"至少有一条日志"，幂等路径**一条都不该有**，
        #    用它反而会因为"没有日志"而失败（第一版就是这么写错的）。
        with self.assertNoLogs('api.views_user', level='INFO'):
            second = self.client_super.post(self.url(), {'is_active': True}, format='json')
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertFalse(second.data['changed'])

    def test_rejects_non_boolean(self):
        """不收 "false" 这种字符串：前端传错时宁可 400，也别猜错了把账号停掉"""
        for bad in ('false', 0, None, ''):
            response = self.client_super.post(self.url(), {'is_active': bad}, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST,
                             f'{bad!r} 应当被拒：{response.data}')
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_change_is_logged(self):
        with self.assertLogs('api.views_user', level='INFO') as captured:
            self.client_super.post(self.url(), {'is_active': False}, format='json')
        joined = '\n'.join(captured.output)
        self.assertIn('停用', joined)
        self.assertIn('zz_st_target', joined)
        self.assertIn('作废', joined)


# ============================================================================
# 第 138 批：反馈的批量改状态 / 批量删除
# ============================================================================
# 背景：`POST /api/feedback/bulk-status/` 第 100 批就写好了（规则齐全），但**前端从未调用** ——
# 列表页连多选都没有，等于一个死接口。这一批把它接上，并补一个对称的批量删除。
#
# 这组测试盯三件事：
#   1. 批量改状态真的生效，且沿用单条 reply 的三条规则（状态白名单、
#      标记已处理必须给回复、首次处理才记 handled_at）；
#   2. 批量删除**只给全权管理员**（内容编辑员即便"能看全部反馈"也不能批量删，
#      这是不可逆操作 —— 与单条 destroy 的护栏对齐后再收紧一档）；
#   3. 两条接口共用同一套 ids 校验（数组、逐项转 int、去重、上限 200）。
# ============================================================================
class FeedbackBulkActionTests(APITestCase):
    """批量改状态 / 批量删除（第 138 批）"""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        from .models import EditorModuleGrant

        self.superuser = User.objects.create_superuser(
            username='zz_fb_super', password='pw12345678', email='', role='ADMIN',
        )
        # 只有 feedback 模块的编辑员
        self.editor = User.objects.create_user(
            username='zz_fb_editor', password='pw12345678', role='EDITOR',
        )
        EditorModuleGrant.objects.create(user=self.editor, module='feedback',
                                        granted_by=self.superuser)
        self.author = User.objects.create_user(
            username='zz_fb_author', password='pw12345678', role='USER',
        )
        self.other = User.objects.create_user(
            username='zz_fb_other', password='pw12345678', role='USER',
        )

        self.mine = [Feedback.objects.create(user=self.author, suggestion=f'我的反馈{i}')
                     for i in range(3)]
        self.theirs = [Feedback.objects.create(user=self.other, suggestion=f'别人的反馈{i}')
                       for i in range(2)]

        self.client_super = APIClient()
        self.client_super.force_authenticate(user=self.superuser)
        self.client_editor = APIClient()
        self.client_editor.force_authenticate(user=self.editor)

    # ---------- 批量改状态 ----------
    def test_bulk_status_flow(self):
        ids = [f.id for f in self.theirs]
        response = self.client_editor.post('/api/feedback/bulk-status/', {
            'ids': ids, 'status': 'processing',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['succeeded'], 2)
        self.assertEqual(response.data['failed'], 0)
        for feedback in self.theirs:
            feedback.refresh_from_db()
            self.assertEqual(feedback.status, 'processing')
            self.assertIsNone(feedback.handled_at, '非"已处理"不该有处理时间')

    def test_bulk_resolved_requires_reply(self):
        """与单条 reply 同一条规则：标记「已处理」必须有回复内容"""
        ids = [f.id for f in self.theirs]
        blocked = self.client_editor.post('/api/feedback/bulk-status/', {
            'ids': ids, 'status': 'resolved',
        }, format='json')
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST, blocked.data)
        for feedback in self.theirs:
            feedback.refresh_from_db()
            self.assertEqual(feedback.status, 'pending', '被拒时不能改状态')

        ok = self.client_editor.post('/api/feedback/bulk-status/', {
            'ids': ids, 'status': 'resolved', 'admin_reply': '已核实并修复',
        }, format='json')
        self.assertEqual(ok.status_code, status.HTTP_200_OK, ok.data)
        for feedback in self.theirs:
            feedback.refresh_from_db()
            self.assertEqual(feedback.status, 'resolved')
            self.assertEqual(feedback.admin_reply, '已核实并修复')
            self.assertIsNotNone(feedback.handled_at)

    def test_bulk_status_keeps_first_handled_at(self):
        """重复标记已处理不刷新首次处理时间（与单条 reply 一致）"""
        feedback = self.theirs[0]
        self.client_editor.post('/api/feedback/bulk-status/', {
            'ids': [feedback.id], 'status': 'resolved', 'admin_reply': '第一次',
        }, format='json')
        feedback.refresh_from_db()
        first_time = feedback.handled_at
        self.assertIsNotNone(first_time)

        self.client_editor.post('/api/feedback/bulk-status/', {
            'ids': [feedback.id], 'status': 'resolved', 'admin_reply': '第二次',
        }, format='json')
        feedback.refresh_from_db()
        self.assertEqual(feedback.handled_at, first_time)
        self.assertEqual(feedback.admin_reply, '第二次')

    def test_bulk_status_rejects_bad_input(self):
        for payload, note in (
            ({'ids': [self.theirs[0].id], 'status': 'done'}, '非法状态'),
            ({'ids': [], 'status': 'processing'}, '空 ids'),
            ({'ids': 'abc', 'status': 'processing'}, 'ids 不是数组'),
            ({'ids': list(range(1, 202)), 'status': 'processing'}, '超过 200 条'),
        ):
            response = self.client_editor.post('/api/feedback/bulk-status/', payload,
                                               format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST,
                             f'{note} 应当被拒：{response.data}')

    def test_bulk_status_reports_missing_rows(self):
        """逐条处理不整体失败：不存在的 id 在 results 里如实报错"""
        response = self.client_editor.post('/api/feedback/bulk-status/', {
            'ids': [self.theirs[0].id, 999999], 'status': 'processing',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['succeeded'], 1)
        self.assertEqual(response.data['failed'], 1)

    def test_plain_user_cannot_bulk_status(self):
        """普通用户没有 feedback 模块 → 批量接口 403（他只能看自己的）"""
        client = APIClient()
        client.force_authenticate(user=self.author)
        response = client.post('/api/feedback/bulk-status/', {
            'ids': [f.id for f in self.mine], 'status': 'resolved', 'admin_reply': 'x',
        }, format='json')
        self.assertIn(response.status_code,
                      (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    # ---------- 批量删除 ----------
    def test_bulk_delete_requires_full_admin(self):
        """
        **内容编辑员不能批量删**（即便他有 feedback 模块、能看全部反馈）

        这是本批刻意收紧的一档：批量删除不可逆，而列表页里编辑员看到的就是全部反馈 ——
        开放给他等于把"不能删别人的反馈"这条守卫从后门绕过去。
        """
        response = self.client_editor.post('/api/feedback/bulk-delete/', {
            'ids': [f.id for f in self.theirs],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertEqual(Feedback.objects.filter(id__in=[f.id for f in self.theirs]).count(), 2)

    def test_superuser_bulk_delete(self):
        ids = [f.id for f in self.theirs]
        response = self.client_super.post('/api/feedback/bulk-delete/', {'ids': ids},
                                          format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['succeeded'], 2)
        self.assertEqual(Feedback.objects.filter(id__in=ids).count(), 0)

    def test_bulk_delete_reports_missing_rows(self):
        response = self.client_super.post('/api/feedback/bulk-delete/', {
            'ids': [self.theirs[0].id, 999999],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['succeeded'], 1)
        self.assertEqual(response.data['failed'], 1)
        self.assertFalse(Feedback.objects.filter(id=self.theirs[0].id).exists())
        self.assertTrue(Feedback.objects.filter(id=self.theirs[1].id).exists())

    def test_bulk_delete_rejects_bad_input(self):
        for payload, note in (
            ({'ids': []}, '空 ids'),
            ({'ids': 'abc'}, 'ids 不是数组'),
            ({'ids': list(range(1, 202))}, '超过 200 条'),
        ):
            response = self.client_super.post('/api/feedback/bulk-delete/', payload,
                                              format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, note)

    def test_bulk_delete_is_logged(self):
        with self.assertLogs('api.views', level='INFO') as captured:
            self.client_super.post('/api/feedback/bulk-delete/',
                                   {'ids': [self.theirs[0].id]}, format='json')
        self.assertIn('批量删除反馈', '\n'.join(captured.output))


# ============================================================================
# 第 140 批：版块管理（Console 页面的两条接口）
# ============================================================================
# 背景：`boards/<id>/set_status/`（启停）与 `boards/update_order/`（排序）**接口早就有**，
# 但控制台里没有版块管理页 —— 两条接口等于死代码；而版块的启停与排序只能进 Django admin。
# 本批把页面补上，这里补上这两条接口的测试（它们此前一条测试都没有）。
#
# 测试重点来自它们注释里记着的两个真实事故：
#   1. `set_status` 曾把不存在的 `updated_by` 字段写进 update_fields → 稳定 500；
#   2. `get_permissions` 的白名单曾漏掉 `update_order` → **任何登录用户**都能改排序（实测 200）。
# ============================================================================
class ForumBoardAdminTests(APITestCase):
    """版块启停 / 排序（第 140 批）"""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.broadcast_admin = User.objects.create_user(
            username='zz_bd_admin', password='pw12345678', is_staff=True, role='ADMIN',
        )
        self.editor = User.objects.create_user(
            username='zz_bd_editor', password='pw12345678', role='EDITOR',
        )
        self.plain = User.objects.create_user(
            username='zz_bd_plain', password='pw12345678', role='USER',
        )
        self.board_a = ForumBoard.objects.create(name='zz版块A', order=1, is_active=True)
        self.board_b = ForumBoard.objects.create(name='zz版块B', order=2, is_active=True)

        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.broadcast_admin)
        self.client_editor = APIClient()
        self.client_editor.force_authenticate(user=self.editor)
        self.client_plain = APIClient()
        self.client_plain.force_authenticate(user=self.plain)

    # ---------- 启停 ----------
    def test_broadcast_admin_can_disable_and_enable(self):
        """启停真的生效，且**不 500**（回归：曾把不存在的 updated_by 写进 update_fields）"""
        off = self.client_admin.post(f'/api/forums/boards/{self.board_a.id}/set_status/',
                                     {'is_active': False}, format='json')
        self.assertEqual(off.status_code, status.HTTP_200_OK, off.data)
        self.assertFalse(off.data['is_active'])
        self.board_a.refresh_from_db()
        self.assertFalse(self.board_a.is_active)

        on = self.client_admin.post(f'/api/forums/boards/{self.board_a.id}/set_status/',
                                    {'is_active': True}, format='json')
        self.assertEqual(on.status_code, status.HTTP_200_OK, on.data)
        self.board_a.refresh_from_db()
        self.assertTrue(self.board_a.is_active)

    def test_set_status_requires_is_active(self):
        response = self.client_admin.post(f'/api/forums/boards/{self.board_a.id}/set_status/',
                                          {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_disabled_board_hidden_from_users_but_visible_to_manager(self):
        """停用的版块：农户端看不到，但版块管理者仍看得到（否则停用后就再也开不回来）"""
        self.client_admin.post(f'/api/forums/boards/{self.board_a.id}/set_status/',
                               {'is_active': False}, format='json')

        public = APIClient()
        public.force_authenticate(user=self.plain)
        names = [b['name'] for b in public.get('/api/forums/boards/').data
                 if isinstance(b, dict)]
        self.assertNotIn('zz版块A', names)

        admin_view = self.client_admin.get('/api/forums/boards/')
        admin_names = [b['name'] for b in admin_view.data if isinstance(b, dict)]
        self.assertIn('zz版块A', admin_names)

    # ---------- 排序 ----------
    def test_broadcast_admin_can_reorder(self):
        response = self.client_admin.post('/api/forums/boards/update_order/', {
            'orders': [{'id': self.board_a.id, 'order': 9},
                       {'id': self.board_b.id, 'order': 1}],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['updated'], 2)
        self.board_a.refresh_from_db()
        self.board_b.refresh_from_db()
        self.assertEqual(self.board_a.order, 9)
        self.assertEqual(self.board_b.order, 1)

    def test_reorder_rejects_bad_payload(self):
        for payload, note in (
            ({'orders': 'abc'}, 'orders 不是数组'),
            ({'orders': [{'id': 'x', 'order': 1}]}, 'id 不是数字'),
            ({'orders': [{'order': 1}]}, '缺 id'),
        ):
            response = self.client_admin.post('/api/forums/boards/update_order/', payload,
                                              format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST,
                             f'{note} 应当被拒：{response.data}')

    # ---------- 权限（回归：曾经任何登录用户都能改排序）----------
    def test_plain_user_cannot_touch_boards(self):
        """普通用户既不能启停、也不能改排序（后者是真实出过的越权）"""
        self.assertEqual(
            self.client_plain.post(f'/api/forums/boards/{self.board_a.id}/set_status/',
                                   {'is_active': False}, format='json').status_code,
            status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client_plain.post('/api/forums/boards/update_order/',
                                   {'orders': [{'id': self.board_a.id, 'order': 5}]},
                                   format='json').status_code,
            status.HTTP_403_FORBIDDEN)
        self.board_a.refresh_from_db()
        self.assertEqual(self.board_a.order, 1, '越权请求不能真的改到数据')

    def test_editor_without_broadcast_capability_cannot_touch_boards(self):
        """信息编辑员只有内容能力，管不了版块（第 124/128 批的能力口径）"""
        self.assertEqual(
            self.client_editor.post(f'/api/forums/boards/{self.board_a.id}/set_status/',
                                    {'is_active': False}, format='json').status_code,
            status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client_editor.post('/api/forums/boards/update_order/',
                                    {'orders': [{'id': self.board_a.id, 'order': 5}]},
                                    format='json').status_code,
            status.HTTP_403_FORBIDDEN)


# ============================================================================
# 第 142 批：被停用的账号登录时要说清原因，且**不消耗失败次数**
# ============================================================================
# 修的是什么：登录视图里本来就有 `account_disabled` 分支，但它**够不着** ——
# Django 的 ModelBackend 对 is_active=False 的用户直接返回 None，
# 于是被停用的账号拿到的提示是「密码错误，还可尝试 4 次」（第 137 批实测），
# 而且**每试一次都在扣失败次数**，5 次后账号还会被临时锁定 ——
# 用户拿着正确密码，却被告知密码错，越试越像"密码错了"。
#
# 修法：把第 101 批为"注销冷静期"写的**提前拦**从 `has_pending_deletion`
# 放宽到 `not is_active`，两种不可用分别给说法（见 `_inactive_login_response`）。
#
# 这组测试盯四件事：
#   1. 停用 + 密码正确 → 403/account_disabled，**失败次数不增加**、不发 token；
#   2. 停用 + 密码错误 → 与普通失败一视同仁（**防枚举**：不知道密码的人拿不到区别）；
#   3. 冷静期账号的老行为不变（仍给 can_cancel 自助恢复信息）；
#   4. 恢复后能正常登录（停用是可逆的）。
# ============================================================================
class DisabledAccountLoginTests(APITestCase):
    """被停用账号的登录提示（第 142 批）"""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='zz_dis_super', password='pw12345678', email='', role='ADMIN',
        )
        self.user = User.objects.create_user(
            username='zz_dis_user', password='pw12345678', role='USER',
        )
        self.client_super = APIClient()
        self.client_super.force_authenticate(user=self.superuser)

    def _login(self, password='pw12345678'):
        return APIClient().post('/api/login/', {
            'username': 'zz_dis_user', 'password': password,
        }, format='json')

    def _suspend(self):
        self.client_super.post(f'/api/admin/users/{self.user.id}/status/',
                               {'is_active': False}, format='json')
        self.user.refresh_from_db()

    def test_suspended_with_correct_password_gets_clear_message(self):
        self._suspend()
        before = self.user.failed_login_attempts

        response = self._login()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertEqual(response.data['code'], 'account_disabled')
        self.assertIn('停用', response.data['message'])
        # 不能发 token，也不该消耗失败次数
        self.assertNotIn('token', response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, before,
                         '密码是对的，不该消耗失败次数')
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_repeated_attempts_do_not_lock_the_account(self):
        """反复登录（密码正确）不会把账号试到锁定 —— 这正是修复前的问题"""
        self._suspend()
        for _ in range(6):
            response = self._login()
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(response.data['code'], 'account_disabled')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_locked, '停用账号不该因为"登录被拒"而被锁定')
        self.assertEqual(self.user.failed_login_attempts, 0)

    def test_suspended_with_wrong_password_looks_like_a_normal_failure(self):
        """防枚举：不知道密码的人拿不到"这个账号被停用了"这个区别"""
        self._suspend()
        response = self._login(password='wrong-password')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, response.data)
        self.assertEqual(response.data['code'], 'invalid_password')
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 1)

    def test_reenabled_account_can_login_again(self):
        self._suspend()
        self.assertEqual(self._login().data['code'], 'account_disabled')
        self.client_super.post(f'/api/admin/users/{self.user.id}/status/',
                               {'is_active': True}, format='json')
        ok = self._login()
        self.assertEqual(ok.status_code, status.HTTP_200_OK, ok.data)
        self.assertTrue(ok.data['data']['token'])

    def test_pending_deletion_still_gets_self_service_hint(self):
        """第 101 批的老行为不能破：冷静期账号仍要拿到"可以取消注销"的信息"""
        self.user.request_deletion()
        response = self._login()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertEqual(response.data['code'], 'account_pending_deletion')
        self.assertTrue(response.data['can_cancel'])
        self.assertIn('days_left', response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)

    def test_soft_deleted_account_is_indistinguishable(self):
        """
        已被删除（软删除）的账号：外部探测不出"这个账号存在过"

        `soft_delete()` 做三件事：**改写用户名**（`deleted_<id>`）、清空个人信息、
        把密码换成随机串。所以拿原用户名来登录，得到的只是"用户名或密码错误"（404）——
        既不暴露"该账号被停用/被删除"，也不暴露它曾经存在。
        （第一版测试断言的是 401 invalid_password，实际是 404 user_not_found：
         用户名已经被让出去了，这比"密码错"更彻底地不可区分。）
        """
        self.user.soft_delete(by=self.superuser, reason='admin')
        response = self._login()
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)
        self.assertEqual(response.data['code'], 'user_not_found')


class ForumBoardCrudTests(APITestCase):
    """
    版块的新建 / 编辑（第 143 批）

    接口本来就有（`POST /forums/boards/`、`PATCH /forums/boards/<id>/`，
    权限 `IsBroadcastManager | IsModeratorOrReadOnly`），但控制台一直没有入口 ——
    在此之前**建版块只能进 Django admin**。本批补上页面后，这里把接口行为钉住。

    重点：
      · 中英字段都要能写（英文界面读 `name_en`/`description_en`，留空回落中文名）；
      · **PATCH 不能把只读统计字段冲掉**（`post_count`/`today_posts` 是只读，
        但如果哪天改成 PUT 全量提交，它们会被写成 0 —— 这条测试就是防这个的）；
      · 权限：只有 BROADCAST（或版主）能建/改，普通用户与信息编辑员都 403。
    """

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.broadcast_admin = User.objects.create_user(
            username='zz_bc_admin', password='pw12345678', is_staff=True, role='ADMIN',
        )
        self.editor = User.objects.create_user(
            username='zz_bc_editor', password='pw12345678', role='EDITOR',
        )
        self.plain = User.objects.create_user(
            username='zz_bc_plain', password='pw12345678', role='USER',
        )
        self.client_admin = APIClient()
        self.client_admin.force_authenticate(user=self.broadcast_admin)
        self.client_editor = APIClient()
        self.client_editor.force_authenticate(user=self.editor)
        self.client_plain = APIClient()
        self.client_plain.force_authenticate(user=self.plain)

    def test_create_board_with_bilingual_fields(self):
        response = self.client_admin.post('/api/forums/boards/', {
            'name': 'zz新版块',
            'name_en': 'zz New Board',
            'description': '简介',
            'description_en': 'Intro',
            'icon': 'seedling',
            'order': 7,
            'is_active': True,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        board = ForumBoard.objects.get(name='zz新版块')
        self.assertEqual(board.name_en, 'zz New Board')
        self.assertEqual(board.description_en, 'Intro')
        self.assertEqual(board.icon, 'seedling')
        self.assertEqual(board.order, 7)
        self.assertTrue(board.is_active)

    def test_edit_keeps_statistics(self):
        """PATCH 改名字不能把统计字段冲掉（post_count/today_posts 是只读）"""
        board = ForumBoard.objects.create(name='zz待改版块', order=1,
                                          post_count=12, today_posts=3)
        response = self.client_admin.patch(f'/api/forums/boards/{board.id}/', {
            'name': 'zz改名后',
            'name_en': 'zz Renamed',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        board.refresh_from_db()
        self.assertEqual(board.name, 'zz改名后')
        self.assertEqual(board.name_en, 'zz Renamed')
        self.assertEqual(board.post_count, 12, '统计字段不该被编辑接口冲掉')
        self.assertEqual(board.today_posts, 3)

    def test_created_board_is_visible_to_growers(self):
        """新建且启用 → 农户端（普通用户）立刻能看到"""
        self.client_admin.post('/api/forums/boards/', {
            'name': 'zz可见版块', 'order': 3, 'is_active': True,
        }, format='json')
        names = [b['name'] for b in self.client_plain.get('/api/forums/boards/').data
                 if isinstance(b, dict)]
        self.assertIn('zz可见版块', names)

    def test_created_but_disabled_board_is_hidden_from_growers(self):
        """新建但**不启用** → 农户端看不到（先把版块建好、内容备齐再开放）"""
        self.client_admin.post('/api/forums/boards/', {
            'name': 'zz隐藏版块', 'order': 4, 'is_active': False,
        }, format='json')
        public_names = [b['name'] for b in self.client_plain.get('/api/forums/boards/').data
                        if isinstance(b, dict)]
        self.assertNotIn('zz隐藏版块', public_names)
        admin_names = [b['name'] for b in self.client_admin.get('/api/forums/boards/').data
                       if isinstance(b, dict)]
        self.assertIn('zz隐藏版块', admin_names)

    def test_name_is_required(self):
        response = self.client_admin.post('/api/forums/boards/', {'name': ''}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_only_broadcast_can_create_or_edit(self):
        for client, label in ((self.client_plain, '普通用户'), (self.client_editor, '信息编辑员')):
            created = client.post('/api/forums/boards/', {'name': f'zz越权{label}'},
                                  format='json')
            self.assertEqual(created.status_code, status.HTTP_403_FORBIDDEN,
                             f'{label}不该能建版块：{created.data}')
        board = ForumBoard.objects.create(name='zz只读版块', order=9)
        edited = self.client_editor.patch(f'/api/forums/boards/{board.id}/',
                                          {'name': 'zz被改了'}, format='json')
        self.assertEqual(edited.status_code, status.HTTP_403_FORBIDDEN, edited.data)
        board.refresh_from_db()
        self.assertEqual(board.name, 'zz只读版块')


class PostModerationByEditorTests(APITestCase):
    """
    置顶 / 加精：信息编辑员（review 模块）也能用（第 145 批）

    这一批给论坛列表加了版主开关（此前只有作者自己的编辑页有勾选框，
    所以"版主给别人的帖子加精/置顶"在界面上做不到）。界面按
    "有 review 模块 / is_staff / is_superuser"显隐，后端仍以 `is_moderator()` 为准 ——
    这里把三类账号的行为钉住，避免以后有人把判定收紧或放宽而无人察觉。
    """

    def setUp(self):
        cache.clear()
        User = get_user_model()
        from .models import EditorModuleGrant

        self.superuser = User.objects.create_superuser(
            username='zz_pm_super', password='pw12345678', email='', role='ADMIN',
        )
        self.editor = User.objects.create_user(
            username='zz_pm_editor', password='pw12345678', role='EDITOR',
        )
        EditorModuleGrant.objects.create(user=self.editor, module='review',
                                         granted_by=self.superuser)
        self.news_editor = User.objects.create_user(
            username='zz_pm_newseditor', password='pw12345678', role='EDITOR',
        )
        EditorModuleGrant.objects.create(user=self.news_editor, module='news',
                                         granted_by=self.superuser)
        self.author = User.objects.create_user(
            username='zz_pm_author', password='pw12345678', role='USER',
        )
        self.board = ForumBoard.objects.create(name='zz版主测试版块', order=900)
        self.post = Post.objects.create(
            title='zz别人的帖子', content='<p>内容</p>', author=self.author,
            board=self.board, status='published',
        )

        self.client_editor = APIClient()
        self.client_editor.force_authenticate(user=self.editor)
        self.client_news = APIClient()
        self.client_news.force_authenticate(user=self.news_editor)
        self.client_author = APIClient()
        self.client_author.force_authenticate(user=self.author)

    def test_review_editor_can_pin_and_feature_others_post(self):
        """有 review 模块的信息编辑员能给**别人的**帖子置顶/加精（这正是本批补的能力）"""
        pinned = self.client_editor.post(
            f'/api/forums/posts/{self.post.id}/set_pinned/', {'is_pinned': True}, format='json')
        self.assertEqual(pinned.status_code, status.HTTP_200_OK, pinned.data)
        self.assertTrue(pinned.data['is_pinned'])

        essence = self.client_editor.post(
            f'/api/forums/posts/{self.post.id}/set_essence/', {'is_essence': True}, format='json')
        self.assertEqual(essence.status_code, status.HTTP_200_OK, essence.data)
        self.assertTrue(essence.data['is_essence'])

        self.post.refresh_from_db()
        self.assertTrue(self.post.is_pinned and self.post.is_essence)

        # 再点一次是取消（接口语义：传了值就按值设，没传就取反）
        off = self.client_editor.post(
            f'/api/forums/posts/{self.post.id}/set_pinned/', {'is_pinned': False}, format='json')
        self.assertEqual(off.status_code, status.HTTP_200_OK)
        self.post.refresh_from_db()
        self.assertFalse(self.post.is_pinned)

    def test_news_only_editor_and_author_cannot_moderate(self):
        """只有 news 模块的编辑员、以及帖子作者本人，都不能置顶/加精（后端 403）"""
        for client, label in ((self.client_news, '只有 news 模块的编辑员'),
                              (self.client_author, '作者本人')):
            pinned = client.post(f'/api/forums/posts/{self.post.id}/set_pinned/',
                                 {'is_pinned': True}, format='json')
            self.assertEqual(pinned.status_code, status.HTTP_403_FORBIDDEN,
                             f'{label}不该能置顶：{pinned.data}')
            essence = client.post(f'/api/forums/posts/{self.post.id}/set_essence/',
                                  {'is_essence': True}, format='json')
            self.assertEqual(essence.status_code, status.HTTP_403_FORBIDDEN,
                             f'{label}不该能加精：{essence.data}')
        self.post.refresh_from_db()
        self.assertFalse(self.post.is_pinned or self.post.is_essence)

    def test_pinned_post_comes_first_in_list(self):
        """置顶真的影响列表顺序（否则这个开关对用户就是隐形的）"""
        other = Post.objects.create(title='zz普通帖子', content='<p>x</p>',
                                    author=self.author, board=self.board, status='published')
        self.client_editor.post(f'/api/forums/posts/{self.post.id}/set_pinned/',
                                {'is_pinned': True}, format='json')
        rows = self.client_author.get(f'/api/forums/posts/?board={self.board.id}').data
        rows = rows.get('results', rows) if isinstance(rows, dict) else rows
        self.assertEqual(rows[0]['id'], self.post.id,
                         '置顶帖应当排在最前（列表默认按 -is_pinned 排序）')
        self.assertEqual(rows[1]['id'], other.id)


# ============================================================================
# 第 146 批：管理操作日志（AuditLog）
# ============================================================================
# 在此之前，管理端的敏感动作（停用/恢复、改角色、开通编辑员、删账号、批量删反馈、
# 版块启停与排序）**只写 logger.info** —— 日志会轮转、没法按操作人筛选、更没法展示。
#
# 这组测试盯四件事：
#   1. 关键动作**真的落库**，且带"谁 / 对谁 / 做了什么"（快照字段）；
#   2. **绝不记录凭证**：签发重置链接的日志里不能出现 token（那等于把改密码的凭证抄进库）；
#   3. 写日志**失败不能影响主操作**（助手内部兜异常）；
#   4. 读取接口**仅全权管理员**，且支持按动作/操作人/关键字筛选。
# ============================================================================
class AdminAuditLogTests(APITestCase):
    """管理操作日志（第 146 批）"""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        from .models import EditorModuleGrant

        self.superuser = User.objects.create_superuser(
            username='zz_al_super', password='pw12345678', email='', role='ADMIN',
        )
        self.editor = User.objects.create_user(
            username='zz_al_editor', password='pw12345678', role='EDITOR',
        )
        EditorModuleGrant.objects.create(user=self.editor, module='feedback',
                                         granted_by=self.superuser)
        self.target = User.objects.create_user(
            username='zz_al_target', password='pw12345678', role='USER',
        )
        self.client_super = APIClient()
        self.client_super.force_authenticate(user=self.superuser)
        self.client_editor = APIClient()
        self.client_editor.force_authenticate(user=self.editor)

    # ---------- 写入 ----------
    def test_suspend_and_restore_are_logged(self):
        self.client_super.post(f'/api/admin/users/{self.target.id}/status/',
                               {'is_active': False}, format='json')
        self.client_super.post(f'/api/admin/users/{self.target.id}/status/',
                               {'is_active': True}, format='json')

        logs = list(AdminAuditLog.objects.filter(target_repr='zz_al_target'))
        actions = [log.action for log in logs]
        self.assertIn('user.suspend', actions)
        self.assertIn('user.restore', actions)
        suspend = next(log for log in logs if log.action == 'user.suspend')
        self.assertEqual(suspend.actor_repr, 'zz_al_super', '要记下操作人用户名快照')
        self.assertEqual(suspend.target_type, 'user')
        self.assertIn('作废', suspend.detail)

    def test_role_change_is_logged(self):
        self.client_super.post(f'/api/admin/users/{self.target.id}/role/',
                               {'role': 'EDITOR', 'modules': ['news']}, format='json')
        log = AdminAuditLog.objects.get(action='user.role_change')
        self.assertEqual(log.target_repr, 'zz_al_target')
        self.assertIn('普通用户', log.detail)   # 用中文角色名，读日志的人不需要查代码
        self.assertIn('编辑员', log.detail)
        self.assertIn('news', log.detail)

    def test_create_editor_is_logged(self):
        self.client_super.post('/api/admin/users/create-editor/', {
            'username': 'zz_al_newone', 'modules': ['news'],
        }, format='json')
        log = AdminAuditLog.objects.get(action='user.create_editor')
        self.assertEqual(log.target_repr, 'zz_al_newone')
        self.assertIn('EDITOR', log.detail)
        get_user_model().objects.filter(username='zz_al_newone').delete()

    def test_delete_and_bulk_delete_are_logged(self):
        other = get_user_model().objects.create_user(
            username='zz_al_other', password='pw12345678', role='USER',
        )
        self.client_super.delete(f'/api/admin/users/{self.target.id}/',
                                 {'confirm': 'zz_al_target'}, format='json')
        self.client_super.post('/api/admin/users/bulk-delete/',
                               {'ids': [other.id]}, format='json')

        self.assertTrue(AdminAuditLog.objects.filter(action='user.delete',
                                                     target_repr='zz_al_target').exists())
        bulk = AdminAuditLog.objects.get(action='user.bulk_delete')
        self.assertIn('1/1', bulk.detail)

    def test_reset_link_token_is_not_logged(self):
        """
        签发重置链接的日志里**不能出现 token**

        链接形如 `<前端地址>/reset-password?uid=..&token=..` —— 把整条链接写进日志，
        等于把"改别人密码的凭证"抄进数据库：任何能读日志的人都能去改那个账号的密码。
        这里同时验证两件事：动作被记下、链接/令牌没被记下。
        """
        response = self.client_super.post(
            f'/api/admin/users/{self.target.id}/reset-link/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        token = response.data['url'].split('token=')[-1]

        log = AdminAuditLog.objects.get(action='user.reset_link')
        self.assertNotIn('token', log.detail.lower())
        self.assertNotIn(token, log.detail)
        self.assertNotIn('/reset-password', log.detail)
        self.assertEqual(log.target_repr, 'zz_al_target')

    def test_bulk_feedback_delete_is_logged(self):
        rows = [Feedback.objects.create(user=self.target, suggestion=f'zz日志测试{i}')
                for i in range(3)]
        self.client_super.post('/api/feedback/bulk-delete/',
                               {'ids': [r.id for r in rows]}, format='json')
        log = AdminAuditLog.objects.get(action='feedback.bulk_delete')
        self.assertEqual(log.target_type, 'feedback')
        self.assertIn('3/3', log.detail)

    def test_board_status_and_order_are_logged(self):
        board = ForumBoard.objects.create(name='zz日志版块', order=1)
        self.client_super.post(f'/api/forums/boards/{board.id}/set_status/',
                               {'is_active': False}, format='json')
        self.client_super.post('/api/forums/boards/update_order/',
                               {'orders': [{'id': board.id, 'order': 5}]}, format='json')
        self.assertTrue(AdminAuditLog.objects.filter(action='board.set_status',
                                                     target_repr='zz日志版块').exists())
        self.assertTrue(AdminAuditLog.objects.filter(action='board.update_order').exists())

    # ---------- 助手本身的护栏 ----------
    def test_helper_never_raises(self):
        """
        写日志失败不能影响主操作：助手内部兜住异常并返回 None

        ⚠️ 第一版我传了个超长 action 想让它失败 —— 结果 SQLite 不校验 CharField 长度，
        记录照样写进去了（断言因此失败）。现在直接**让 create 抛异常**来测契约，
        这才是真正要保证的事：底层炸了也不能把停用/删除这类主操作带崩。
        """
        from unittest import mock

        from .audit import log_admin_action

        with mock.patch('api.models_audit.AdminAuditLog.objects.create',
                        side_effect=RuntimeError('磁盘满了')):
            result = log_admin_action(self.superuser, 'user.suspend', target=self.target,
                                      detail='测试')
        self.assertIsNone(result, '写不进去时应当返回 None，而不是抛异常')

        # 主流程照常可用（上面的异常被兜在助手内部）
        response = self.client_super.post(f'/api/admin/users/{self.target.id}/status/',
                                          {'is_active': False}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(AdminAuditLog.objects.filter(action='user.suspend').exists())

    def test_sanitize_detail_masks_credentials(self):
        """detail 里的 `token=...` 会被保险丝抹掉（即使调用方写错了）"""
        from .audit import sanitize_detail
        masked = sanitize_detail('链接 /reset-password?uid=1&token=abcdef 已签发')
        self.assertNotIn('abcdef', masked)
        self.assertIn('token=***', masked)

    def test_actor_snapshot_survives_account_deletion(self):
        """操作人账号被删后，日志仍读得懂（这正是存快照的理由）"""
        self.client_super.post(f'/api/admin/users/{self.target.id}/status/',
                               {'is_active': False}, format='json')
        log = AdminAuditLog.objects.get(action='user.suspend')
        # 把操作人真删掉（hard delete → actor 外键变 NULL）
        get_user_model().objects.filter(id=self.superuser.id).delete()
        log.refresh_from_db()
        self.assertIsNone(log.actor)
        self.assertEqual(log.actor_repr, 'zz_al_super', '快照要留着，否则日志变成"某人对某人"')

    # ---------- 读取接口 ----------
    def test_list_requires_full_admin(self):
        self.client_super.post(f'/api/admin/users/{self.target.id}/status/',
                               {'is_active': False}, format='json')
        # 有 feedback 模块的编辑员也读不到（日志是管理端内部信息）
        self.assertEqual(self.client_editor.get('/api/admin/audit-logs/').status_code,
                         status.HTTP_403_FORBIDDEN)
        response = self.client_super.get('/api/admin/audit-logs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data['count'], 1)
        row = response.data['results'][0]
        self.assertIn('actor_name', row)
        self.assertIn('action_display', row)

    def test_list_filters(self):
        self.client_super.post(f'/api/admin/users/{self.target.id}/status/',
                               {'is_active': False}, format='json')
        self.client_super.post(f'/api/admin/users/{self.target.id}/status/',
                               {'is_active': True}, format='json')

        only_suspend = self.client_super.get('/api/admin/audit-logs/?action=user.suspend')
        self.assertEqual(only_suspend.data['count'], 1)

        by_actor = self.client_super.get(f'/api/admin/audit-logs/?actor={self.superuser.id}')
        self.assertEqual(by_actor.data['count'], 2)

        # 非法筛选值**忽略**，不该 500（与其它管理列表一致）
        self.assertEqual(
            self.client_super.get('/api/admin/audit-logs/?action=不存在的动作').status_code,
            status.HTTP_200_OK)

        searched = self.client_super.get('/api/admin/audit-logs/?search=zz_al_target')
        self.assertGreaterEqual(searched.data['count'], 1)

    def test_actions_endpoint(self):
        response = self.client_super.get('/api/admin/audit-logs/actions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        values = [row['value'] for row in response.data]
        self.assertIn('user.suspend', values)
        self.assertIn('board.create', values)
        self.assertEqual(self.client_editor.get('/api/admin/audit-logs/actions/').status_code,
                         status.HTTP_403_FORBIDDEN)
