"""agent 层（LangGraph）的测试 —— 第 424 批。

## 为什么单独一个文件，不写进 `tests.py`

`tests.py` 已经 20000 行，且第 423 批还在改它。这一批的用例要能独立跑：

    python manage.py test api.tests_agent

## 测试**不打真模型**

模型被替换成 `ScriptedModel`（按脚本吐 `AIMessage`）。理由不是"快"，
而是**可判定**：真模型每次的 tool_calls 都可能不同，那样的用例只能断言
"没崩"，断言不了"写操作只执行了一次"。

## 三个必须被钉住的行为

1. 写操作在"确认"之前**一次都没执行**（否则二次确认形同虚设）；
2. 确认之后**只执行一次**（重复 resume 不能执行两次）；
3. 模型挂了要降级，不能把 `LLMError` 抛到视图层。
"""
from __future__ import annotations

from unittest import mock

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration
from langchain_core.outputs import ChatResult as LangChainChatResult
from rest_framework.test import APITestCase

from .assistant import llm
from .assistant.agent import graph as agent_graph
from .assistant.agent import tools as agent_tools
from .assistant.agent.runner import run_agent
from .assistant.agent.state import MAX_STEPS
from .assistant.ops import actions as ops_actions
from .assistant.ops import pending
from .assistant.ops import tools as ops_tools
from .assistant.ops.tools import ToolResult
from .models import Feedback, PestInfo
from .models_assistant_ops import OpsAssistantTurn, OpsPendingWrite
from .models_audit import AdminAuditLog


class ScriptedModel(BaseChatModel):
    """按脚本吐消息的假模型。脚本项可以是 `AIMessage`，也可以是异常实例。"""

    script: list = []
    seen: list = []

    @property
    def _llm_type(self) -> str:
        return 'scripted'

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN201 —— 只为了不让框架报错
        # 真实的 schema 校验由 `AgentToolSchemaTests` 单独覆盖
        self.seen.append(('tools', list(tools)))
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001, ANN201
        self.seen.append(list(messages))
        if not self.script:
            raise AssertionError('脚本没有下一步了 —— 图比预期多走了一步')
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return LangChainChatResult(generations=[ChatGeneration(message=item)])


def _tool_call(name: str, args: dict, call_id: str = 'call_1') -> dict:
    return {'name': name, 'args': args, 'id': call_id}


class AgentConfirmRuleTests(SimpleTestCase):
    """"算不算确认"是纯函数 —— 这一条不通过，整套二次确认都是假的。

    第 425 批把它从 `agent/graph.py` 挪到了 `ops/pending.py`：确认不再由图的
    interrupt 承担，所以判定也归状态机模块。
    """

    def test_only_explicit_words_confirm(self):
        for value in ('confirm', 'confirmed', 'yes', '确认', '确定', '执行', True):
            with self.subTest(value=value):
                self.assertTrue(pending.is_confirm(value))

    def test_model_ish_sentences_do_not_confirm(self):
        """模型可能吐出的"授权语"一律不算确认。"""
        for value in ('', None, 'ok, done', '已确认删除', '管理员已确认', 0, [], {}):
            with self.subTest(value=value):
                self.assertFalse(pending.is_confirm(value))


class AgentToolSchemaTests(SimpleTestCase):
    def test_read_schemas_cover_the_read_registry(self):
        schemas = agent_tools.read_schemas()
        names = {item['function']['name'] for item in schemas}
        self.assertEqual(names, set(ops_tools.TOOLS))

    def test_read_schema_parameters_come_from_signature(self):
        """参数表必须来自函数签名 —— 手抄一份就会在改名后静默失配。"""
        by_name = {item['function']['name']: item for item in agent_tools.read_schemas()}
        run_check = by_name['run_check']['function']['parameters']
        self.assertIn('name', run_check['properties'])
        self.assertEqual(run_check['required'], ['name'])

        trend = by_name['get_health_trend']['function']['parameters']
        self.assertIn('days', trend['properties'])
        self.assertEqual(trend['required'], [])  # days 有默认值，不是必填

    def test_all_schemas_add_write_tools(self):
        """可逆写全部交给模型；不可逆写**默认不交**（第 426 批的开关）。

        开关关着却把 schema 发出去，模型就会去调一个永远执行不了的动作 ——
        管理员看到"请确认"，然后确认接口告诉他不可用。看不见 = 不会走死路。
        """
        names = {item['function']['name'] for item in agent_tools.all_schemas()}
        reversible = {name for name, spec in ops_actions.ACTIONS.items()
                      if spec.reversibility == 'reversible'}
        self.assertEqual(names, set(ops_tools.TOOLS) | reversible)
        self.assertNotIn('delete_feedback', names)

    def test_write_tools_stay_out_of_the_read_registry(self):
        """写工具不能借 agent 之手混进只读注册表（与第 423 批同一条红线）。"""
        self.assertEqual(set(agent_tools.READ_TOOLS) & set(agent_tools.WRITE_TOOLS), set())


class AgentToolPairingTests(SimpleTestCase):
    """每个 `tool_call` 都必须有回复 —— 真机 HTTP 400 的根因。

    假模型不会因为"少一条 tool 回复"而报错，真实端点会（而且报在**下一轮**）。
    所以这条约束必须单独钉住，不能只靠 happy path 的用例。
    """

    def _ai(self, *call_ids):
        return AIMessage(content='', tool_calls=[
            _tool_call(f'tool_{i}', {}, call_id) for i, call_id in enumerate(call_ids)])

    def _tool(self, call_id):
        from langchain_core.messages import ToolMessage
        return ToolMessage(content='{}', tool_call_id=call_id, name='tool')

    def test_missing_replies_are_repaired(self):
        messages = [self._ai('c1', 'c2'), self._tool('c1')]
        repairs = agent_graph.repair_unanswered(messages)
        self.assertEqual([item.tool_call_id for item in repairs], ['c2'])

    def test_no_repair_when_all_answered(self):
        messages = [self._ai('c1', 'c2'), self._tool('c1'), self._tool('c2')]
        self.assertEqual(agent_graph.repair_unanswered(messages), [])

    def test_pending_write_leaves_no_dangling_call(self):
        """挂起的那一轮：assistant 消息里的调用还没有回复。

        这是最容易漏的一条 —— 挂起时不能回复（还没执行），但也不能就那样留在状态里，
        否则恢复后模型一被调用就 400。
        """
        messages = [self._ai('w1')]
        repairs = agent_graph.repair_unanswered(messages)
        self.assertEqual([item.tool_call_id for item in repairs], ['w1'])
        self.assertIn('没有执行', repairs[0].content)


class AgentReadLoopTests(SimpleTestCase):
    """只读循环：模型要工具 → 图执行 → 回到模型 → 出答案。"""

    def test_read_tool_then_answer(self):
        model = ScriptedModel(script=[
            AIMessage(content='', tool_calls=[_tool_call(
                'search_ops_docs', {'query': '备份'})]),
            AIMessage(content='备份在 backups/ 目录，按日期命名。'),
        ])
        result = run_agent(question='备份放哪', model=model)

        self.assertFalse(result['interrupted'])
        self.assertEqual(result['answer'], '备份在 backups/ 目录，按日期命名。')
        self.assertEqual(result['steps'], 2)
        self.assertEqual([item['name'] for item in result['events']], ['search_ops_docs'])

    def test_direct_answer_without_tools(self):
        model = ScriptedModel(script=[AIMessage(content='这是一句直接回答。')])
        result = run_agent(question='系统还好吗', model=model)

        self.assertEqual(result['answer'], '这是一句直接回答。')
        self.assertEqual(result['steps'], 1)
        self.assertEqual(result['events'], [])

    def test_step_limit_stops_the_loop(self):
        """模型要个没完时，图必须自己停 —— 不能靠模型配合。"""
        model = ScriptedModel(script=[
            AIMessage(content='', tool_calls=[_tool_call('search_ops_docs', {'query': f'q{i}'})])
            for i in range(MAX_STEPS + 3)
        ])
        result = run_agent(question='一直查', model=model)

        self.assertFalse(result['interrupted'])
        self.assertLessEqual(result['steps'], MAX_STEPS + 1)
        self.assertTrue(result['answer'], '停下来之后必须给出确定性答案，不能空着')

    def test_model_failure_degrades_instead_of_raising(self):
        model = ScriptedModel(script=[llm.LLMError('端点连不上')])
        result = run_agent(question='系统还好吗', model=model)

        self.assertEqual(result['degraded'], 'model_unavailable')
        self.assertTrue(result['answer'])


class AgentReversibleWriteTests(TestCase):
    """L2 可逆写：校验通过即执行 + 审计（与既有 ops 链路分级一致）。"""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username='zz_agent_write_admin', password='pw12345678', is_staff=True)
        self.author = User.objects.create_user(
            username='zz_agent_write_author', password='pw12345678')
        self.pest = PestInfo.objects.create(
            name='番茄早疫病', crop_type='番茄', english_identifier='agent_early_blight')
        self.sample = Feedback.objects.create(
            user=self.author, category='recognition', disease_name='番茄晚疫病',
            is_correct=False, corrected_pest=self.pest)

    def _model(self, feedback_id: int) -> ScriptedModel:
        return ScriptedModel(script=[
            AIMessage(content='', tool_calls=[_tool_call('verify_feedback_sample', {
                'feedback_id': feedback_id, 'verify_status': 'confirmed'})]),
        ])

    def test_reversible_write_executes_and_audits(self):
        question = f'把反馈 #{self.sample.id} 的样本标为已确认'
        result = run_agent(question=question, user=self.admin, model=self._model(self.sample.id))

        self.sample.refresh_from_db()
        self.assertEqual(self.sample.verify_status, 'confirmed')
        self.assertTrue(result['answer'])
        self.assertTrue(
            AdminAuditLog.objects.filter(action='feedback.verify_sample').exists(),
            '写操作必须留痕',
        )

    def test_id_must_come_from_the_administrators_words(self):
        """原话里没有编号 → 一次都不许写（防模型幻觉一个 id 改到无关记录）。"""
        result = run_agent(question='把那个样本标为已确认', user=self.admin,
                           model=self._model(self.sample.id))

        self.sample.refresh_from_db()
        self.assertEqual(self.sample.verify_status, 'pending')
        self.assertFalse(AdminAuditLog.objects.filter(action='feedback.verify_sample').exists())
        self.assertTrue(result['answer'])

    def test_two_writes_in_one_turn_are_both_rejected(self):
        model = ScriptedModel(script=[
            AIMessage(content='', tool_calls=[
                _tool_call('verify_feedback_sample',
                           {'feedback_id': self.sample.id, 'verify_status': 'confirmed'}, 'c1'),
                _tool_call('mark_feedback_handled',
                           {'feedback_id': self.sample.id, 'status': 'resolved'}, 'c2'),
            ]),
        ])
        run_agent(question=f'把 #{self.sample.id} 标为已确认并置为已处理',
                  user=self.admin, model=model)

        self.sample.refresh_from_db()
        self.assertEqual(self.sample.verify_status, 'pending')
        self.assertEqual(self.sample.status, 'pending')


class _IrreversibleSetup:
    """造一个"不可逆动作"。

    真正的不可逆动作还没上线（`ACTIONS` 里全是可逆的），所以这里用 mock 造：
    测的是**状态机与图的接线**——确认之前不执行、确认之后只执行一次、
    过期/越权/重放的 token 一律拒绝。
    """

    def _validated(self) -> ops_actions.Validated:
        spec = ops_actions.ActionSpec(
            name='delete_detection_records',
            label='删除识别记录',
            reversibility='irreversible',
            audit_action='feedback.status',
            description='删除指定识别记录（不可逆）',
        )
        return ops_actions.Validated(
            spec=spec,
            args={'feedback_id': 7},
            target='识别记录 #7',
            changes=['deleted'],
        )

    def _patches(self):
        """把"不可逆动作"接进两处：图的写工具表、`actions` 的校验与执行。"""
        validated = self._validated()
        executed: list = []

        def _execute(item, **kwargs):  # noqa: ANN001, ANN003
            executed.append(item)
            return ToolResult(name=item.name, ok=True, data={'deleted': True})

        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(mock.patch.object(
            agent_tools, 'WRITE_TOOLS', (validated.name,)))
        # 同一个 `actions.validate` 既被 `agent_tools.prepare_write` 用、
        # 也被 `pending.confirm` 用 —— 一个 patch 同时盖住"提议"与"确认"两次校验
        stack.enter_context(mock.patch.object(
            ops_actions, 'validate', return_value=(validated, '')))
        stack.enter_context(mock.patch.object(
            ops_actions, 'execute', side_effect=_execute))
        return stack, executed, validated

    def _model(self, validated) -> ScriptedModel:  # noqa: ANN001
        return ScriptedModel(script=[
            AIMessage(content='', tool_calls=[
                _tool_call(validated.name, dict(validated.args))]),
        ])


class AgentProposalTests(TestCase, _IrreversibleSetup):
    """不可逆写的第一段：**只生成待确认记录**，一次都不执行。"""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username='zz_agent_propose_admin', password='pw12345678', is_staff=True)

    def test_proposal_creates_row_and_executes_nothing(self):
        stack, executed, validated = self._patches()
        with stack:
            result = run_agent(question='删除识别记录 #7', user=self.admin,
                               model=self._model(validated))

        self.assertEqual(executed, [], '提议阶段一次都不许执行')
        self.assertEqual(OpsPendingWrite.objects.count(), 1)
        row = OpsPendingWrite.objects.get()
        self.assertEqual(row.status, 'pending')
        self.assertEqual(row.action, validated.name)
        self.assertEqual(row.target, '识别记录 #7')
        self.assertEqual(result['token'], row.token)
        self.assertEqual(result['degraded'], 'needs_confirmation')

    def test_proposal_answer_states_target_and_expiry(self):
        """复述必须说清"对谁、做什么、多久有效" —— 只说"确认吗"不算二次确认。"""
        stack, executed, validated = self._patches()
        with stack:
            result = run_agent(question='删除识别记录 #7', user=self.admin,
                               model=self._model(validated))

        answer = result['answer']
        self.assertIn('删除识别记录', answer)
        self.assertIn('识别记录 #7', answer)
        self.assertIn('不可逆', answer)
        self.assertIn(result['token'], answer)

    def test_logged_out_proposal_is_refused(self):
        """没有登录用户就不能落待确认（否则确认时无法核对"是不是他提议的"）。"""
        stack, executed, validated = self._patches()
        with stack:
            result = run_agent(question='删除识别记录 #7', user=None,
                               model=self._model(validated))

        self.assertEqual(OpsPendingWrite.objects.count(), 0)
        self.assertEqual(executed, [])
        self.assertEqual(result['degraded'], 'action_failed')

    def test_too_many_open_proposals_are_refused(self):
        stack, executed, validated = self._patches()
        with stack:
            for index in range(pending.MAX_OPEN):
                run_agent(question=f'删除识别记录 #7 第{index}次', user=self.admin,
                          model=self._model(validated))
            result = run_agent(question='删除识别记录 #7 再一次', user=self.admin,
                               model=self._model(validated))

        self.assertEqual(OpsPendingWrite.objects.count(), pending.MAX_OPEN)
        self.assertEqual(executed, [])
        self.assertEqual(result['degraded'], 'action_failed')


class OpsPendingWriteTests(TestCase, _IrreversibleSetup):
    """状态机本身：原子认领、过期、越权、重放、执行失败。"""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username='zz_pending_admin', password='pw12345678', is_staff=True)
        self.other = User.objects.create_user(
            username='zz_pending_other', password='pw12345678', is_staff=True)
        # ⚠️ 必须 addCleanup：这个 patch 改的是 `actions.validate` 这个**模块属性**，
        # 不还原的话它会泄漏到后面所有测试类（表现为"随便什么名字都能校验通过"）。
        self._stack, _, self.validated = self._patches()
        self.addCleanup(self._stack.close)

    def _propose(self, user=None) -> OpsPendingWrite:
        row, error = pending.propose(
            user=user or self.admin, validated=self.validated, question='删除识别记录 #7')
        self.assertIsNotNone(row, error)
        return row

    def test_consume_is_single_use(self):
        row = self._propose()
        first, reason = pending.consume(row.token, user=self.admin)
        self.assertIsNotNone(first, reason)
        self.assertEqual(first.status, 'confirmed')

        second, reason = pending.consume(row.token, user=self.admin)
        self.assertIsNone(second)
        self.assertEqual(reason, 'consumed')

    def test_expired_token_is_refused(self):
        row = self._propose()
        OpsPendingWrite.objects.filter(pk=row.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1))

        consumed, reason = pending.consume(row.token, user=self.admin)
        self.assertIsNone(consumed)
        self.assertEqual(reason, 'expired')
        row.refresh_from_db()
        self.assertEqual(row.status, 'expired')

    def test_other_admin_cannot_consume(self):
        row = self._propose()
        consumed, reason = pending.consume(row.token, user=self.other)
        self.assertIsNone(consumed)
        self.assertEqual(reason, 'not_found', '不区分"不存在"与"不是你的"，避免探测')
        row.refresh_from_db()
        self.assertEqual(row.status, 'pending')

    def test_cancel_then_confirm_is_refused(self):
        row = self._propose()
        ok, message = pending.cancel(row.token, user=self.admin)
        self.assertTrue(ok, message)

        stack, executed, _ = self._patches()
        with stack:
            result, reason, _ = pending.confirm(row.token, user=self.admin)
        self.assertEqual(executed, [], '取消之后绝不能再执行')
        self.assertFalse(result.ok)

    def test_confirm_executes_and_marks_confirmed(self):
        row = self._propose()
        stack, executed, _ = self._patches()
        with stack:
            result, reason, finished = pending.confirm(row.token, user=self.admin)

        self.assertTrue(result.ok)
        self.assertEqual(reason, '')
        self.assertEqual(len(executed), 1)
        row.refresh_from_db()
        self.assertEqual(row.status, 'confirmed')
        self.assertIsNotNone(row.consumed_at)

    def test_confirm_revalidates_before_executing(self):
        """提议与确认之间的几分钟里，目标可能被删、权限可能被收回。"""
        row = self._propose()
        stack, executed, _ = self._patches()
        self.addCleanup(stack.close)
        with mock.patch.object(ops_actions, 'validate', return_value=(None, '目标不存在')):
            result, reason, finished = pending.confirm(row.token, user=self.admin)

        self.assertFalse(result.ok)
        self.assertEqual(reason, 'invalid')
        self.assertEqual(executed, [])
        row.refresh_from_db()
        self.assertEqual(row.status, 'failed', '校验不过要落 failed，不能留一条假 pending')

    def test_execute_failure_marks_failed(self):
        row = self._propose()
        with mock.patch.object(ops_actions, 'validate', return_value=(self.validated, '')), \
                mock.patch.object(ops_actions, 'execute',
                                  side_effect=RuntimeError('数据库炸了')):
            result, reason, _ = pending.confirm(row.token, user=self.admin)

        self.assertFalse(result.ok)
        self.assertEqual(reason, 'exec_failed')
        row.refresh_from_db()
        self.assertEqual(row.status, 'failed')

    def test_propose_requires_a_validated_object(self):
        """`propose()` 收的是 `Validated` 而不是裸参数 —— 裸的没有"已校验"这层保证。"""
        row, error = pending.propose(user=self.admin, validated=None, question='x')
        self.assertIsNone(row)
        self.assertTrue(error)


class OpsPendingConfirmApiTests(APITestCase, _IrreversibleSetup):
    """确认接口：token 一次性、越权与状态码。"""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username='zz_confirm_api_admin', password='pw12345678', is_staff=True)
        self.editor = User.objects.create_user(
            username='zz_confirm_api_editor', password='pw12345678')
        # 同上：不还原就会污染其它测试类
        self._stack, _, self.validated = self._patches()
        self.addCleanup(self._stack.close)
        row, error = pending.propose(
            user=self.admin, validated=self.validated, question='删除识别记录 #7')
        self.assertIsNotNone(row, error)
        self.row = row

    def _post(self, **payload):
        return self.client.post(reverse('admin-assistant-ops-confirm'), payload, format='json')

    def test_non_admin_is_forbidden(self):
        self.client.force_authenticate(self.editor)
        response = self._post(token=self.row.token, decision='confirm')
        self.assertEqual(response.status_code, 403)

    def test_missing_token_is_bad_request(self):
        self.client.force_authenticate(self.admin)
        response = self._post(decision='confirm')
        self.assertEqual(response.status_code, 400)

    def test_ambiguous_decision_is_bad_request(self):
        self.client.force_authenticate(self.admin)
        response = self._post(token=self.row.token, decision='大概吧')
        self.assertEqual(response.status_code, 400)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, 'pending', '说不清就什么都不做')

    def test_confirm_executes_exactly_once(self):
        self.client.force_authenticate(self.admin)
        stack, executed, _ = self._patches()
        with stack:
            first = self._post(token=self.row.token, decision='confirm')
            second = self._post(token=self.row.token, decision='confirm')

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()['ok'])
        self.assertEqual(len(executed), 1, '重复提交不能执行第二次')
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()['ok'])

    def test_cancel_does_not_execute(self):
        self.client.force_authenticate(self.admin)
        stack, executed, _ = self._patches()
        with stack:
            response = self._post(token=self.row.token, decision='cancel')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(executed, [])
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, 'cancelled')

    def test_expired_token_reports_clearly(self):
        OpsPendingWrite.objects.filter(pk=self.row.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        self.client.force_authenticate(self.admin)
        stack, executed, _ = self._patches()
        with stack:
            response = self._post(token=self.row.token, decision='confirm')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['ok'])
        self.assertEqual(executed, [])
        self.assertIn('过期', response.json()['answer'])

class OpsAgentSwitchTests(APITestCase):
    """开关：/ask/ 走图编排还是走"意图分类 → 固定映射"（第 425 批）。

    ## 为什么要盯着"开关关着时 agent 一次都不许被调用"

    开关存在的意义是**可回退**。若关掉之后代码仍然碰了 agent，
    那么"没装 langgraph 的部署"和"agent 出故障时的回退"都会失效 —— 而这两件事
    恰恰是当初把 agent 放旁路的全部理由。
    """

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username='zz_switch_admin', password='pw12345678', is_staff=True)
        self.client.force_authenticate(self.admin)

    def _ask(self, question='系统最近怎么样'):
        return self.client.post(reverse('admin-assistant-ops-ask'),
                                {'question': question}, format='json')

    def test_flag_off_never_touches_the_agent(self):
        from api.assistant.agent import runner as agent_runner
        with mock.patch.object(agent_runner, 'run_agent',
                               side_effect=AssertionError('开关关着时不许调 agent')):
            response = self._ask()
        self.assertEqual(response.status_code, 200)

    @override_settings(OPS_AGENT_ENABLED=True)
    def test_flag_on_uses_the_graph_and_records_intent(self):
        from api.assistant.agent import runner as agent_runner
        canned = {
            'answer': '图编排给的答案', 'degraded': '', 'pending': None, 'token': '',
            'results': [ToolResult(name='get_system_health', ok=True, ms=12, data={}).as_dict()],
            'steps': 1, 'events': [],
        }
        with mock.patch.object(agent_runner, 'run_agent', return_value=canned):
            response = self._ask()

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body['answer'], '图编排给的答案')
        self.assertEqual(body['intent'], 'agent')
        self.assertEqual([item['name'] for item in body['tools']], ['get_system_health'])
        turn = OpsAssistantTurn.objects.order_by('-id').first()
        self.assertEqual(turn.intent, 'agent', '观测表要能区分图编排与固定映射')

    @override_settings(OPS_AGENT_ENABLED=True)
    def test_pending_token_reaches_the_client(self):
        from api.assistant.agent import runner as agent_runner
        canned = {
            'answer': '准备执行：删除识别记录', 'degraded': 'needs_confirmation',
            'pending': {'action': 'delete_detection_records', 'target': '识别记录 #7'},
            'token': 'abc123', 'results': [], 'steps': 1, 'events': [],
        }
        with mock.patch.object(agent_runner, 'run_agent', return_value=canned):
            body = self._ask('删除识别记录 #7').json()

        self.assertEqual(body['token'], 'abc123')
        self.assertEqual(body['pending']['target'], '识别记录 #7')
        self.assertTrue(body['degraded'])

    @override_settings(OPS_AGENT_ENABLED=True)
    def test_model_outage_still_returns_200(self):
        from api.assistant.agent import runner as agent_runner
        canned = {'answer': '模型暂时不可用', 'degraded': 'model_unavailable',
                  'pending': None, 'token': '', 'results': [], 'steps': 0, 'events': []}
        with mock.patch.object(agent_runner, 'run_agent', return_value=canned):
            response = self._ask()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['degraded'])
        self.assertEqual(body['degrade_reason'], 'model_unavailable')

class OpsIrreversibleActionTests(TestCase):
    """第一个真正的不可逆动作：delete_feedback（第 426 批）。

    这个类盯的是**四道独立的闸门**，任何一道失效都算事故：

    1. 开关关着时，模型**看不到**这个动作；
    2. 直接调 execute()（老的模型工具路径就是这样）→ 拒绝执行；
    3. 只有 `confirmed=True`（只有 `pending.confirm()` 会传）才真的删；
    4. 删除要落审计、要清图片文件。
    """

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username='zz_delete_admin', password='pw12345678', is_staff=True)
        self.author = User.objects.create_user(
            username='zz_delete_author', password='pw12345678')
        self.feedback = Feedback.objects.create(
            user=self.author, category='suggestion', suggestion='希望加导出按钮',
            disease_name='番茄晚疫病')
        self.question = f'把反馈 #{self.feedback.id} 删掉'

    def _validated(self):
        validated, error = ops_actions.validate(
            'delete_feedback', {'feedback_id': self.feedback.id}, question=self.question)
        self.assertIsNotNone(validated, error)
        return validated

    # ── ① 开关关着：看不见、也校验不过 ──────────────────────────────────
    @override_settings(OPS_IRREVERSIBLE_ENABLED=False)
    def test_switch_off_hides_the_action_from_the_model(self):
        names = {item['function']['name'] for item in agent_tools.all_schemas()}
        self.assertNotIn('delete_feedback', names)

        validated, error = ops_actions.validate(
            'delete_feedback', {'feedback_id': self.feedback.id}, question=self.question)
        self.assertIsNone(validated)
        self.assertIn('未开启', error)

    @override_settings(OPS_IRREVERSIBLE_ENABLED=False)
    def test_switch_off_keeps_the_reversible_actions_visible(self):
        names = {item['function']['name'] for item in agent_tools.all_schemas()}
        self.assertIn('verify_feedback_sample', names)

    # ── ② 没有确认 → 一次都不执行 ────────────────────────────────────────
    @override_settings(OPS_IRREVERSIBLE_ENABLED=True)
    def test_direct_execute_is_refused(self):
        """老的"模型选工具 → 直接执行"路径必须被挡住。

        _run_action() 会把模型选中的动作直接交给 execute()；没有这道闸门，
        一次提示注入就能删掉一条反馈，而整套二次确认完全没被走到。
        """
        validated = self._validated()
        result = ops_actions.execute(validated, user=self.admin)

        self.assertFalse(result.ok)
        self.assertIn('二次确认', result.error)
        self.assertTrue(Feedback.objects.filter(pk=self.feedback.id).exists())

    # ── ③ 确认之后：删除 + 审计 ─────────────────────────────────────────
    @override_settings(OPS_IRREVERSIBLE_ENABLED=True)
    def test_confirmed_execute_deletes_and_audits(self):
        validated = self._validated()
        self.assertIn(f'#{self.feedback.id}', validated.target, '复述必须能说清删哪一条')

        result = ops_actions.execute(validated, user=self.admin, confirmed=True)

        self.assertTrue(result.ok, result.error)
        self.assertFalse(Feedback.objects.filter(pk=self.feedback.id).exists())
        log = AdminAuditLog.objects.filter(action='feedback.delete').first()
        self.assertIsNotNone(log, '不可逆操作必须留痕')
        self.assertEqual(log.actor_id, self.admin.id)
        self.assertEqual(log.target_id, str(self.feedback.id))
        self.assertIn('确认后删除', log.detail)

    # ── ④ 图片文件一起清掉 ──────────────────────────────────────────────
    @override_settings(OPS_IRREVERSIBLE_ENABLED=True)
    def test_image_file_is_removed_too(self):
        from django.core.files.storage import default_storage
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.feedback.image = SimpleUploadedFile(
            'zz_delete_pic.png', b'\x89PNG\r\n\x1a\nfake', content_type='image/png')
        self.feedback.save(update_fields=['image'])
        name = self.feedback.image.name
        self.assertTrue(default_storage.exists(name))

        validated = self._validated()
        result = ops_actions.execute(validated, user=self.admin, confirmed=True)

        self.assertTrue(result.ok, result.error)
        self.assertFalse(default_storage.exists(name), '孤儿图片文件会让 media 越积越大')

    # ── ⑤ 端到端：提议 → 确认，反馈在确认之前一直还在 ────────────────────
    @override_settings(OPS_IRREVERSIBLE_ENABLED=True)
    def test_end_to_end_propose_then_confirm(self):
        model = ScriptedModel(script=[
            AIMessage(content='', tool_calls=[_tool_call(
                'delete_feedback', {'feedback_id': self.feedback.id})]),
        ])
        proposed = run_agent(question=self.question, user=self.admin, model=model)

        self.assertEqual(proposed['degraded'], 'needs_confirmation')
        self.assertTrue(Feedback.objects.filter(pk=self.feedback.id).exists(),
                        '提议阶段绝不能删')
        row = OpsPendingWrite.objects.get(token=proposed['token'])
        self.assertEqual(row.action, 'delete_feedback')
        self.assertIn(f'#{self.feedback.id}', proposed['answer'])

        result, reason, finished = pending.confirm(proposed['token'], user=self.admin)

        self.assertTrue(result.ok, (result.error, reason))
        self.assertFalse(Feedback.objects.filter(pk=self.feedback.id).exists())
        finished.refresh_from_db()
        self.assertEqual(finished.status, 'confirmed')

    @override_settings(OPS_IRREVERSIBLE_ENABLED=True)
    def test_confirm_is_refused_when_the_target_is_gone(self):
        """提议之后目标被别人删了：确认时必须拒绝，而不是"假装删成功"。"""
        validated = self._validated()
        row, error = pending.propose(
            user=self.admin, validated=validated, question=self.question)
        self.assertIsNotNone(row, error)

        Feedback.objects.filter(pk=self.feedback.id).delete()
        result, reason, finished = pending.confirm(row.token, user=self.admin)

        self.assertFalse(result.ok)
        self.assertEqual(reason, 'invalid')
        finished.refresh_from_db()
        self.assertEqual(finished.status, 'failed')
