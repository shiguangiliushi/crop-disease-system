"""
专家咨询接口（第 49 批）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/consult/questions/` | GET | 提问列表（`?status=open|answered|closed`、`?crop=`、`?mine=true`） |
| `/api/consult/questions/` | POST | 提问（敏感词校验；通知全体专家） |
| `/api/consult/questions/<id>/` | GET | 详情（含回答；浏览数 +1） |
| `/api/consult/questions/<id>/close/` | POST | 关闭问题（提问者本人或管理员） |
| `/api/consult/questions/<id>/answers/` | POST | 作答（**仅专家或管理员**，这是"咨询"与"论坛"的关键区别） |
| `/api/consult/answers/<id>/accept/` | POST | 采纳回答（**仅提问者本人**；一个回答被采纳则其余取消） |
| `/api/consult/experts/` | GET | 专家列表 |
| `/api/consult/experts/<user_id>/` | POST/DELETE | 授予/取消专家（仅管理员） |
"""
import logging

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import permissions, status
# 第 124 批：统一的能力/全权管理员判定（本文件原来自己抄了一份管理员判定）
from .capabilities import CAP_USER_ADMIN, has_capability, is_full_admin
from rest_framework.response import Response
from rest_framework.views import APIView

from .models_expert import ConsultAnswer, ConsultQuestion, ExpertProfile
from .sensitive import check_text
from .services_content_i18n import pest_en_maps  # 第 78 批：作物名的中英对照

logger = logging.getLogger(__name__)
User = get_user_model()


def _can_admin_users(user):
    """
    能否授予 / 取消专家身份（`USER_ADMIN` 能力：账号与身份管理）

    第 124 批：判定统一收口到 `capabilities.py`。**信息编辑员（EDITOR）不可** ——
    专家身份是"谁能代表平台答疑"的授权，与内容维护不是一回事。
    """
    return has_capability(user, CAP_USER_ADMIN)


def notify_experts(question):
    """把一张咨询工单通知给在岗专家（第 196 批从 `QuestionListView._notify_experts` 提出）。

    为什么要提出来：助手"转人工"也要发同样的通知。原先它是视图里的方法，
    助手要复用就只能 import 视图类再手动构造 —— 那种耦合迟早出问题。
    失败只记日志：**通知发不出去不该让提问失败**（提问本身已经落库了）。
    """
    try:
        from .views_notify import notify
        experts = User.objects.filter(
            Q(expert_profile__is_active=True) | Q(is_staff=True),
            is_active=True,
        ).exclude(id=question.asker_id).distinct()
        for expert in experts:
            notify(
                expert,
                type='system',
                title=f'新的专家咨询：{question.title[:30]}',
                title_en=f'New expert question: {question.title[:30]}',
                message=f'{question.asker.username} 提问（{question.crop_type or "未指定作物"}），期待你的解答',
                url='/consult',
                actor=question.asker,
            )
    except Exception:
        logger.exception('通知专家失败 question=%s', question.id)


def is_expert(user):
    """
    在岗专家（管理员默认也算，方便管理员直接答疑）

    ⚠️ 这里**直接查库**而不是 `user.expert_profile.is_active`：
    反向一对一关系会被缓存在 User 实例上，同一个实例（例如 DRF 测试里
    `force_authenticate` 复用的对象、或长生命周期进程里复用的对象）在**取消专家身份后**
    仍会读到旧的 `is_active=True`，导致"已撤销还能作答"。
    一次 count 查询换来权限判断永远以数据库为准，值得。

    ⚠️ 第 124 批说明：这里的"管理员默认也算专家"用的是 `is_full_admin()`
    （不是能力判定）—— 它表达的是**身份**（谁能答疑），不是"内容维护权限"。
    因此信息编辑员（EDITOR）**不会**因此获得答疑身份，要保持原有行为。
    """
    if not user or not user.is_authenticated:
        return False
    if is_full_admin(user):
        return True
    return ExpertProfile.objects.filter(user=user, is_active=True).exists()


def _crop_en_map():
    """
    作物中文名 → 英文名（第 78 批）

    咨询里的 `crop_type` 是用户从百科作物里选的，取值与 `PestInfo.crop_type` 同源，
    所以直接复用百科的对照表，不用给咨询表再加一个 `crop_type_en` 字段（也就不需要迁移）。
    """
    return pest_en_maps()[1]


def _user_brief(user):
    profile = getattr(user, 'expert_profile', None)
    # 回包字段（不是权限判定）：管理员兜底成"专家"身份用于展示，语义同 is_expert()
    is_admin = is_full_admin(user)
    return {
        'id': user.id,
        'username': user.username,
        'is_expert': bool(profile and profile.is_active) or is_admin,
        'expert_title': profile.title if profile else ('管理员' if is_admin else ''),
        # 第 78 批：管理员兜底头衔也要有英文（专家自己填写的头衔属于内容数据，保持原样）
        'expert_title_en': 'Administrator' if (is_admin and not (profile and profile.title)) else '',
        'avatar': user.avatar.url if getattr(user, 'avatar', None) else None,
    }


def _serialize_question(question, request=None, with_answers=False):
    data = {
        'id': question.id,
        'crop_type': question.crop_type,
        # 第 78 批：作物名走百科的中英对照，英文界面下"番茄"要显示成 Tomato
        'crop_type_en': _crop_en_map().get(question.crop_type, ''),
        'title': question.title,
        'content': question.content,
        'image': question.image.url if question.image else None,
        'status': question.status,
        'status_display': question.get_status_display(),
        'answer_count': question.answer_count,
        'view_count': question.view_count,
        'accepted_answer_id': question.accepted_answer_id,
        'created_at': question.created_at,
        'last_answer_at': question.last_answer_at,
        'asker': _user_brief(question.asker) if question.asker_id else None,
        'is_mine': bool(request and getattr(request.user, 'id', None) == question.asker_id),
    }
    if with_answers:
        data['answers'] = [_serialize_answer(item, request) for item in question.answers.all()]
    return data


def _serialize_answer(answer, request=None):
    return {
        'id': answer.id,
        'content': answer.content,
        'is_accepted': answer.is_accepted,
        'created_at': answer.created_at,
        'author': _user_brief(answer.author) if answer.author_id else None,
        'author_title': answer.author_title,
        # 第 78 批：管理员兜底头衔的英文（专家自己填写的头衔属于内容数据，保持原样）
        'author_title_en': 'Administrator' if answer.author_title == '管理员' else '',
        'is_mine': bool(request and getattr(request.user, 'id', None) == answer.author_id),
    }


class QuestionListView(APIView):
    """提问列表 / 发起提问"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = ConsultQuestion.objects.select_related('asker', 'asker__expert_profile')

        status_param = (request.query_params.get('status') or '').strip()
        if status_param in ('open', 'answered', 'closed'):
            queryset = queryset.filter(status=status_param)

        crop = (request.query_params.get('crop') or '').strip()
        if crop and crop != 'all':
            queryset = queryset.filter(crop_type=crop)

        if request.query_params.get('mine') == 'true':
            queryset = queryset.filter(asker=request.user)

        keyword = (request.query_params.get('search') or '').strip()
        if keyword:
            queryset = queryset.filter(Q(title__icontains=keyword) | Q(content__icontains=keyword))

        total = queryset.count()
        counts = {
            'open': ConsultQuestion.objects.filter(status='open').count(),
            'answered': ConsultQuestion.objects.filter(status='answered').count(),
            'closed': ConsultQuestion.objects.filter(status='closed').count(),
        }

        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = min(50, max(1, int(request.query_params.get('page_size', 10))))
        except (TypeError, ValueError):
            page_size = 10

        start = (page - 1) * page_size
        rows = queryset[start:start + page_size]

        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'status_counts': counts,
            'results': [_serialize_question(row, request) for row in rows],
        })

    def post(self, request):
        title = (request.data.get('title') or '').strip()
        content = (request.data.get('content') or '').strip()
        crop_type = (request.data.get('crop_type') or '').strip()

        if not title:
            return Response({'detail': '请填写问题标题'}, status=status.HTTP_400_BAD_REQUEST)
        if len(title) > 200:
            return Response({'detail': '问题标题最多 200 字'}, status=status.HTTP_400_BAD_REQUEST)
        if len(content) < 5:
            return Response({'detail': '问题描述太短了，至少写 5 个字'}, status=status.HTTP_400_BAD_REQUEST)

        # 与帖子/评论/私信同一套敏感词校验
        try:
            check_text(title, content, field_label='问题')
        except Exception as exc:
            detail = getattr(exc, 'detail', None)
            message = detail.get('detail') if isinstance(detail, dict) else '问题包含不允许的词汇'
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)

        question = ConsultQuestion.objects.create(
            asker=request.user, crop_type=crop_type, title=title, content=content,
        )

        # 通知在岗专家（有活干才有人来答）
        self._notify_experts(question)
        logger.info('新增咨询提问 id=%s by=%s', question.id, request.user.id)
        return Response(_serialize_question(question, request, with_answers=True),
                        status=status.HTTP_201_CREATED)

    def _notify_experts(self, question):
        """保留这个方法名（原有调用点与测试可能引用），实现收口到模块级 `notify_experts()`。

        第 196 批：助手"转人工"也要发同样的通知，所以把实现提成模块级函数 ——
        否则助手侧只能 import 视图类再手工调用，那种耦合迟早出问题。
        """
        notify_experts(question)


class QuestionDetailView(APIView):
    """提问详情（浏览数 +1）/ 关闭问题"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        question = (
            ConsultQuestion.objects
            .select_related('asker', 'asker__expert_profile')
            .filter(pk=pk).first()
        )
        if not question:
            return Response({'detail': '问题不存在'}, status=status.HTTP_404_NOT_FOUND)

        # 浏览量用 F() 原子自增，避免并发覆盖
        from django.db.models import F
        ConsultQuestion.objects.filter(pk=pk).update(view_count=F('view_count') + 1)
        question.refresh_from_db(fields=['view_count'])

        return Response(_serialize_question(question, request, with_answers=True))

    def post(self, request, pk):
        """关闭问题（提问者本人或管理员）"""
        question = ConsultQuestion.objects.filter(pk=pk).first()
        if not question:
            return Response({'detail': '问题不存在'}, status=status.HTTP_404_NOT_FOUND)
        if not (request.user.id == question.asker_id or is_full_admin(request.user)):
            return Response({'detail': '只有提问者本人或管理员可以关闭问题'},
                            status=status.HTTP_403_FORBIDDEN)

        question.status = 'closed'
        question.save(update_fields=['status', 'updated_at'])
        return Response(_serialize_question(question, request, with_answers=True))


class AnswerCreateView(APIView):
    """作答（仅专家或管理员）"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        question = ConsultQuestion.objects.select_related('asker').filter(pk=pk).first()
        if not question:
            return Response({'detail': '问题不存在'}, status=status.HTTP_404_NOT_FOUND)
        if not is_expert(request.user):
            return Response({'detail': '只有专家或管理员可以回答咨询问题'},
                            status=status.HTTP_403_FORBIDDEN)

        content = (request.data.get('content') or '').strip()
        if len(content) < 5:
            return Response({'detail': '回答内容太短了，至少写 5 个字'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            check_text(content, field_label='回答')
        except Exception as exc:
            detail = getattr(exc, 'detail', None)
            message = detail.get('detail') if isinstance(detail, dict) else '回答包含不允许的词汇'
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)

        profile = getattr(request.user, 'expert_profile', None)
        answer = ConsultAnswer.objects.create(
            question=question, author=request.user, content=content,
            author_title=(profile.title if profile and profile.is_active
                          else ('管理员' if is_full_admin(request.user) else '')),
        )
        question.refresh_answer_stats()

        # 通知提问者
        try:
            from .views_notify import notify
            notify(
                question.asker,
                type='reply',
                title=f'{request.user.username} 回答了你的问题：{question.title[:30]}',
                title_en=f'{request.user.username} answered your question: {question.title[:30]}',
                message=content[:60],
                url='/consult',
                actor=request.user,
            )
        except Exception:
            logger.exception('通知提问者失败 question=%s', question.id)

        logger.info('咨询回答 id=%s question=%s by=%s', answer.id, question.id, request.user.id)
        return Response(_serialize_answer(answer, request), status=status.HTTP_201_CREATED)


class AnswerAcceptView(APIView):
    """采纳回答（仅提问者本人）"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        answer = ConsultAnswer.objects.select_related('question', 'author').filter(pk=pk).first()
        if not answer:
            return Response({'detail': '回答不存在'}, status=status.HTTP_404_NOT_FOUND)

        question = answer.question
        if question.asker_id != request.user.id:
            return Response({'detail': '只有提问者本人可以采纳回答'},
                            status=status.HTTP_403_FORBIDDEN)

        # 一个回答被采纳，其余取消（保证"最佳答案"唯一）
        ConsultAnswer.objects.filter(question=question, is_accepted=True).update(is_accepted=False)
        answer.is_accepted = True
        answer.save(update_fields=['is_accepted', 'updated_at'])

        question.accepted_answer = answer
        question.status = 'answered'
        question.save(update_fields=['accepted_answer', 'status', 'updated_at'])

        try:
            from .views_notify import notify
            notify(
                answer.author,
                type='system',
                title=f'你的回答被采纳了：{question.title[:30]}',
                title_en=f'Your answer was accepted: {question.title[:30]}',
                message='提问者采纳了你的回答，感谢你的帮助！',
                url='/consult',
                actor=request.user,
            )
        except Exception:
            logger.exception('通知被采纳者失败 answer=%s', answer.id)

        logger.info('采纳回答 answer=%s question=%s', answer.id, question.id)
        return Response({
            'accepted_answer_id': answer.id,
            'question': _serialize_question(question, request, with_answers=True),
        })


class ExpertListView(APIView):
    """专家列表 / 授予或取消专家（仅管理员）"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profiles = ExpertProfile.objects.select_related('user').filter(is_active=True)
        data = []
        for profile in profiles:
            answered = ConsultAnswer.objects.filter(author=profile.user).count()
            accepted = ConsultAnswer.objects.filter(author=profile.user, is_accepted=True).count()
            data.append({
                'user': _user_brief(profile.user),
                'title': profile.title,
                'specialties': profile.specialty_list,
                'bio': profile.bio,
                'answered_count': answered,
                'accepted_count': accepted,
            })
        # 管理员也算可答疑的人，但列表只展示被正式授予的专家（口径清楚）
        return Response({'count': len(data), 'results': data})

    def post(self, request, user_id):
        if not _can_admin_users(request.user):
            return Response({'detail': '只有管理员可以授予专家身份'}, status=status.HTTP_403_FORBIDDEN)
        user = User.objects.filter(pk=user_id).first()
        if not user:
            return Response({'detail': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)

        profile, _created = ExpertProfile.objects.update_or_create(
            user=user,
            defaults={
                'title': (request.data.get('title') or '').strip(),
                'specialties': (request.data.get('specialties') or '').strip(),
                'bio': (request.data.get('bio') or '').strip(),
                'is_active': True,
                'granted_by': request.user,
            },
        )
        # 通知被授予人
        try:
            from .views_notify import notify
            notify(
                user, type='system', title='你已被设为平台专家',
                title_en='You have been granted expert status',
                message=f'职称：{profile.title or "专家"}；现在可以在「专家咨询」里回答农户提问了',
                url='/consult', actor=request.user,
            )
        except Exception:
            logger.exception('通知新专家失败 user=%s', user_id)
        return Response({'detail': '已授予专家身份', 'user': _user_brief(user)}, status=status.HTTP_200_OK)

    def delete(self, request, user_id):
        if not _can_admin_users(request.user):
            return Response({'detail': '只有管理员可以取消专家身份'}, status=status.HTTP_403_FORBIDDEN)
        profile = ExpertProfile.objects.filter(user_id=user_id).first()
        if not profile:
            return Response({'detail': '该用户不是专家'}, status=status.HTTP_404_NOT_FOUND)
        if not profile.is_active:
            # 幂等：重复点"取消"不该报错，但也不该重复发通知
            return Response({'detail': '该用户当前不是专家', 'changed': False})

        profile.is_active = False
        profile.save(update_fields=['is_active'])

        # 通知被取消人（与"授予"对称；此前只发授予通知，被取消的人毫无感知）
        try:
            from .views_notify import notify
            notify(
                profile.user,
                type='system',
                title='你的平台专家身份已被取消',
                title_en='Your expert status has been revoked',
                message='如有疑问请联系管理员。你之前已回答的咨询内容仍会保留。',
                url='/consult',
                actor=request.user,
            )
        except Exception:
            logger.exception('通知被取消专家失败 user=%s', user_id)

        logger.info('取消专家身份 user=%s by=%s', user_id, request.user.id)
        return Response({'detail': '已取消专家身份', 'changed': True})
