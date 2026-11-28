"""游客试用的测试（第 439 批）。

## 为什么单独一个文件

与 `tests_agent.py` 同一个理由：`tests.py` 已经两万行，而这一批的行为
（额度、闸门、统计口径、清理）需要能独立跑：

    python manage.py test api.tests_guest

## 这组用例盯的是什么

真跑"3 次识别"太慢，所以额度被压到 **1**（`override_settings`），盯的是**语义**：

1. 第 N+1 次必须是 **402 且没有落库**（不能"扣了额度还写了一条历史"）；
2. 扣减是**一条 UPDATE**（并发下只有一个能成功）；
3. 游客**写不了**白名单之外的任何东西；
4. 游客的记录**不进**管理端统计；
5. `prune_guests` 只删过期游客，**不碰真实用户**。
"""
from __future__ import annotations

from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from . import guest, views_guest
from .models import DetectionHistory
from .models_guest import GuestTrialQuota
from .models_token import DeviceToken

User = get_user_model()

#: 把额度压到 1，测"第 2 次"就够
SMALL_QUOTA = {'enabled': True, 'detect_per_day': 1, 'ask_per_day': 1}

#: 识别测试用的真实图片（仓库自带）；被清理掉时用例跳过而不是假绿
LEAF_IMAGE = Path(settings.BASE_DIR) / 'pests' / 'Apple___Apple_scab14.jpg'


def _fake_request(ip: str, user=None):
    """给 `guest.*` 用的最小 request 替身（它们只读 META 与 user）。"""
    class _Req:
        META = {'REMOTE_ADDR': ip}

    request = _Req()
    request.user = user
    return request


def _guest_client(ip: str):
    """开一个游客身份，返回 (已带 token 的 client, token)。"""
    client = APIClient()
    response = client.post('/api/guest/session/', REMOTE_ADDR=ip)
    assert response.status_code == 201, response.data
    token = response.data['data']['token']
    client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
    return client, token


class GuestSessionTests(TestCase):
    """开试用：匿名可开、重复调用不重复建号、身份不可登录。"""

    def setUp(self):
        cache.clear()

    def test_anonymous_can_open_trial(self):
        response = APIClient().post('/api/guest/session/', REMOTE_ADDR='10.1.0.1')
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data['data']
        self.assertTrue(data['user']['is_guest'], '返回的 user 必须带 is_guest')
        self.assertTrue(data['token'])
        self.assertEqual(data['quota']['detect_left'], 3)
        self.assertEqual(data['quota']['ask_left'], 5)

        user = User.objects.get(pk=data['user']['id'])
        self.assertTrue(user.is_guest)
        self.assertFalse(user.has_usable_password(),
                         '游客账号必须永远登录不上（不可用密码），否则就成了后门')
        self.assertEqual(user.role, 'USER')

    def test_second_call_reuses_identity(self):
        client, token = _guest_client('10.1.0.2')
        before = User.objects.filter(is_guest=True).count()
        again = client.post('/api/guest/session/', REMOTE_ADDR='10.1.0.2')
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(again.data['data']['token'], token)
        self.assertEqual(User.objects.filter(is_guest=True).count(), before,
                         '带着游客 token 再开一次，不该多建一个账号')

    @override_settings(GUEST_TRIAL={**SMALL_QUOTA, 'enabled': False})
    def test_disabled_returns_403(self):
        response = APIClient().post('/api/guest/session/', REMOTE_ADDR='10.1.0.3')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['code'], 'GUEST_TRIAL_DISABLED')


class GuestQuotaTests(TestCase):
    """额度的语义：原子扣减、用尽即 402、换身份不换额度。"""

    def setUp(self):
        cache.clear()

    @override_settings(GUEST_TRIAL=SMALL_QUOTA)
    def test_second_detect_is_402_and_writes_nothing(self):
        client, _ = _guest_client('10.2.0.1')
        # 先把唯一一次额度用掉（直接扣，避免真的跑一次推理）
        allowed, left = guest.consume('detect', _fake_request('10.2.0.1'))
        self.assertTrue(allowed)
        self.assertEqual(left, 0)

        image = SimpleUploadedFile('leaf.jpg', b'\xff\xd8\xff\xe0fake-jpeg',
                                   content_type='image/jpeg')
        response = client.post('/api/detect/', {'image': image}, format='multipart',
                               REMOTE_ADDR='10.2.0.1')
        self.assertEqual(response.status_code, 402, response.data)
        self.assertEqual(response.data['code'], 'GUEST_QUOTA_EXCEEDED')
        self.assertIn('注册', response.data['message'])
        self.assertTrue(response.data['reset_at'])
        self.assertEqual(DetectionHistory.objects.count(), 0,
                         '额度已满时不该产生任何识别记录')

    @override_settings(GUEST_TRIAL=SMALL_QUOTA)
    def test_consume_is_one_update(self):
        """并发下只有一次能成功 —— 这里用"连扣两次"表达同一条不变量。"""
        request = _fake_request('10.2.0.2')
        first, left1 = guest.consume('ask', request)
        second, left2 = guest.consume('ask', request)
        self.assertTrue(first)
        self.assertEqual(left1, 0)
        self.assertFalse(second, '额度只有 1 次，第二次必须失败')
        self.assertEqual(left2, 0)
        self.assertEqual(GuestTrialQuota.objects.get().asks, 1)

    @override_settings(GUEST_TRIAL=SMALL_QUOTA)
    def test_new_identity_does_not_reset_quota(self):
        """清掉本地存储再进一次 = 新 token，但额度还是按 IP 算。"""
        _guest_client('10.2.0.3')
        guest.consume('ask', _fake_request('10.2.0.3'))

        fresh = APIClient().post('/api/guest/session/', REMOTE_ADDR='10.2.0.3')
        self.assertEqual(fresh.status_code, 201)
        self.assertEqual(fresh.data['data']['quota']['ask_left'], 0,
                         '换了身份额度就重置 —— 那这条防线等于不存在')

    def test_normal_user_is_unlimited(self):
        user = User.objects.create_user(username='normal_quota', password='pw12345678')
        request = _fake_request('10.2.0.4', user=user)
        self.assertFalse(guest.is_guest(user))
        self.assertTrue(guest.snapshot(request)['unlimited'])
        # `charge()` 是视图用的入口：非游客直接放行，且**不建额度行**
        for _ in range(10):
            self.assertIsNone(views_guest.charge('detect', request))
        self.assertEqual(GuestTrialQuota.objects.count(), 0,
                         '登录用户不该产生额度行')

    @override_settings(GUEST_TRIAL=SMALL_QUOTA)
    def test_quota_endpoint_reports_left(self):
        client, _ = _guest_client('10.2.0.5')
        guest.consume('ask', _fake_request('10.2.0.5'))
        response = client.get('/api/guest/quota/', REMOTE_ADDR='10.2.0.5')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['data']['ask_left'], 0)
        self.assertEqual(response.data['data']['detect_left'], 1)
        self.assertFalse(response.data['data']['unlimited'])


class GuestGateTests(TestCase):
    """闸门：游客只能写白名单视图。"""

    def setUp(self):
        cache.clear()

    def test_guest_cannot_write_other_endpoints(self):
        client, _ = _guest_client('10.3.0.1')
        # 意见反馈：真实用户空 body 会是 400；游客必须在**认证层**就被挡成 403
        response = client.post('/api/feedback/', {}, format='json', REMOTE_ADDR='10.3.0.1')
        self.assertEqual(response.status_code, 403, response.data)
        self.assertIn('注册', str(response.data))

    def test_guest_cannot_post_forum(self):
        client, _ = _guest_client('10.3.0.2')
        response = client.post('/api/forums/posts/',
                               {'title': '标题标题标题', 'content': 'x' * 30},
                               format='json', REMOTE_ADDR='10.3.0.2')
        self.assertEqual(response.status_code, 403, response.data)

    def test_guest_can_read_public_pages(self):
        """读是放行的：否则连百科、预警都看不了。"""
        client, _ = _guest_client('10.3.0.3')
        for url in ('/api/pests/', '/api/alerts/'):
            response = client.get(url, REMOTE_ADDR='10.3.0.3')
            self.assertIn(response.status_code, (200, 404), f'{url} 不该被闸门挡住')

    def test_guest_token_cannot_touch_admin(self):
        client, _ = _guest_client('10.3.0.4')
        response = client.get('/api/admin/dashboard/', REMOTE_ADDR='10.3.0.4')
        self.assertIn(response.status_code, (401, 403))

    def test_guest_cannot_send_image_to_assistant(self):
        """看图问答对游客关闭：明确 400，且**不扣额度**。"""
        if not LEAF_IMAGE.exists():
            self.skipTest('测试图片不存在')
        client, _ = _guest_client('10.3.0.5')
        with LEAF_IMAGE.open('rb') as handle:
            upload = SimpleUploadedFile('leaf.jpg', handle.read(), content_type='image/jpeg')
            response = client.post('/api/assistant/ask/',
                                   {'question': '这是什么病？', 'image': upload},
                                   format='multipart', REMOTE_ADDR='10.3.0.5')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('试用', str(response.data), '应是"试用不支持看图"，不是图片格式报错')
        self.assertEqual(guest.used('ask', _fake_request('10.3.0.5')), 0,
                         '被拒绝的请求不该消耗额度')

    def test_guest_can_clear_own_history(self):
        """清空自己的历史在白名单里（他要能抹掉试用痕迹）。"""
        client, _ = _guest_client('10.3.0.6')
        response = client.delete('/api/detection-history/clear-all/',
                                 REMOTE_ADDR='10.3.0.6')
        self.assertIn(response.status_code, (200, 204), response.data)

    def test_disabled_also_blocks_existing_guest_token(self):
        """总开关关掉 = 存量游客也失效（只关入口的话，出事时止不住血）。"""
        client, _ = _guest_client('10.3.0.7')
        with override_settings(GUEST_TRIAL={**SMALL_QUOTA, 'enabled': False}):
            response = client.get('/api/guest/quota/', REMOTE_ADDR='10.3.0.7')
        self.assertEqual(response.status_code, 403, response.data)


class GuestStatsIsolationTests(TestCase):
    """游客的记录不能进管理端统计。"""

    def setUp(self):
        cache.clear()
        self.normal = User.objects.create_user(username='stats_normal', password='pw12345678')
        self.guest_user = User.objects.create(username='guest_stats', is_guest=True)

    def _history(self, user, result='苹果黑星病'):
        return DetectionHistory.objects.create(user=user, detection_result=result,
                                               confidence=0.9, image='detection_history/x.jpg')

    def test_real_users_excludes_guest(self):
        self._history(self.normal)
        self._history(self.guest_user)
        self.assertEqual(DetectionHistory.objects.count(), 2)
        self.assertEqual(DetectionHistory.objects.real_users().count(), 1,
                         '统计口径必须排除游客试用')

    def test_health_counts_ignore_guest(self):
        from .views_system_health import _counts
        self._history(self.normal)
        self._history(self.guest_user)
        self.assertEqual(_counts()['detections'], 1)


class PruneGuestsTests(TestCase):
    """清理：只删过期游客，真实用户一条不少。"""

    def setUp(self):
        cache.clear()

    def _guest_with_token(self, username, *, days_ago):
        user = User.objects.create(username=username, is_guest=True)
        token = DeviceToken.issue(user, 'web')
        DeviceToken.objects.filter(pk=token.pk).update(
            last_seen=timezone.now() - timedelta(days=days_ago))
        return user

    def test_prune_deletes_only_stale_guests(self):
        stale = self._guest_with_token('guest_old', days_ago=10)
        fresh = self._guest_with_token('guest_new', days_ago=0)
        normal = User.objects.create_user(username='keep_me', password='pw12345678')

        call_command('prune_guests', '--days', '3', '--yes', stdout=StringIO())

        self.assertFalse(User.objects.filter(pk=stale.pk).exists(),
                         '10 天没活动的游客应该被删')
        self.assertTrue(User.objects.filter(pk=fresh.pk).exists(),
                        '刚用过的游客不能删（面试官可能正开着页面）')
        self.assertTrue(User.objects.filter(pk=normal.pk).exists(),
                        '真实用户绝不能被误删')

    def test_prune_is_dry_run_by_default(self):
        user = self._guest_with_token('guest_dry', days_ago=10)
        call_command('prune_guests', '--days', '3', stdout=StringIO())
        self.assertTrue(User.objects.filter(pk=user.pk).exists(),
                        '不给 --yes 时不该删任何东西')

class GuestQuotaIpTrustTests(TestCase):
    """额度按 IP 计，所以"信哪个 IP"就是**安全边界**（第 439 批）。

    修复前 `audit._client_ip()` 取 `X-Forwarded-For` 的**最左**值，而 nginx 用的是
    `$proxy_add_x_forwarded_for`（真 IP 追加在**最右**）—— 最左那一段是客户端自己填的。
    结果：任何人在请求里加一个 `X-Forwarded-For: 1.2.3.4` 就能"换 IP"，
    而游客额度正是按 IP 哈希计的 ⇒ **一个 header 换无限免费识别**（CPU 推理，
    等于免费压测入口）。审计日志的 ip 同样会失真。

    这三条用例钉住新的优先级：X-Real-IP > X-Forwarded-For 最右 > REMOTE_ADDR。
    """

    def setUp(self):
        cache.clear()

    def _req(self, meta):
        from .audit import _client_ip

        class _R:
            META = meta

        return _client_ip(_R())

    def test_spoofed_leftmost_xff_is_ignored(self):
        ip = self._req({
            'HTTP_X_FORWARDED_FOR': '6.6.6.6, 10.9.0.1',   # 左边是伪造的
            'REMOTE_ADDR': '10.9.0.1',
        })
        self.assertEqual(ip, '10.9.0.1')

    def test_x_real_ip_wins_over_forwarded_for(self):
        ip = self._req({
            'HTTP_X_REAL_IP': '10.9.0.2',                   # nginx 覆盖写入
            'HTTP_X_FORWARDED_FOR': '6.6.6.6, 1.1.1.1',
            'REMOTE_ADDR': '127.0.0.1',
        })
        self.assertEqual(ip, '10.9.0.2')

    def test_quota_key_ignores_spoofed_leftmost(self):
        """同一真实 IP、不同伪造前缀 → **同一个额度行**（不能靠换 header 加额度）。"""

        def req(meta):
            class _R:
                META = meta

            return _R()

        a = req({'HTTP_X_FORWARDED_FOR': '1.1.1.1, 10.9.0.4', 'REMOTE_ADDR': '10.9.0.4'})
        b = req({'HTTP_X_FORWARDED_FOR': '2.2.2.2, 10.9.0.4', 'REMOTE_ADDR': '10.9.0.4'})
        self.assertEqual(guest.ip_hash(a), guest.ip_hash(b))

    def test_real_ip_change_still_gets_new_quota(self):
        """不同真实 IP 仍然是不同额度行（否则多台设备共享 3 次，体验不对）。"""

        def req(meta):
            class _R:
                META = meta

            return _R()

        a = req({'REMOTE_ADDR': '10.9.0.4'})
        b = req({'REMOTE_ADDR': '10.9.0.5'})
        self.assertNotEqual(guest.ip_hash(a), guest.ip_hash(b))

class GuestCanConvertToRealAccountTests(TestCase):
    """游客必须能"转正"——否则漏斗断在最后一步（第 439 批补）。

    实测坑：写闸门默认拒绝，而 `/api/register/`、`/api/login/` 一开始不在白名单；
    前端 `utils/axios.js` 只要本地有 token 就带 `Authorization`，而游客进过识别页后
    **token 是有的** —— 于是"用完 3 次 → 点注册"收到 403「试用账号只能使用识别与问答」，
    用户既注册不了也登录不了（只能清缓存）。现在四个身份入口都放行：

        register / login / password-reset / password-reset-confirm

    注意放行的是"能到达视图"，不是"能随便写"：这些视图本身就是 `AllowAny`。
    """

    def setUp(self):
        cache.clear()

    def test_guest_can_reach_register(self):
        client, _token = _guest_client('10.6.0.1')
        response = client.post(
            '/api/register/',
            {'username': 'guest_try_register', 'password': 'pw12345678'},
            format='json',
        )
        self.assertNotEqual(
            response.status_code, 403,
            f'游客被写闸门挡住了注册：{getattr(response, "data", None)}')

    def test_guest_can_reach_login(self):
        client, _token = _guest_client('10.6.0.2')
        response = client.post(
            '/api/login/',
            {'username': 'nobody_here', 'password': 'wrong-password'},
            format='json',
        )
        self.assertNotEqual(
            response.status_code, 403,
            f'游客被写闸门挡住了登录：{getattr(response, "data", None)}')

    def test_guest_can_reach_password_reset_request(self):
        client, _token = _guest_client('10.6.0.3')
        response = client.post(
            '/api/password-reset/', {'username_or_email': 'nobody'}, format='json',
        )
        self.assertNotEqual(response.status_code, 403)

    def test_gate_still_blocks_other_writes(self):
        """放行的是身份入口，**不是所有写操作** —— 闸门本身不能被弄坏。"""
        client, _token = _guest_client('10.6.0.4')
        response = client.post('/api/feedback/', {'content': 'hello'}, format='json')
        self.assertEqual(response.status_code, 403, response.data)