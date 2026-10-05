<template>
  <!--
    可点击的用户头像（第 113 批）
    ==========================================================================
    用户要求："用户之间可以点击头像进行私信"。

    这个组件把"点头像 → 开私信"这条交互**收在一处**，而不是在 8 个页面里
    各写一遍 `@click` + 路由跳转 + 自己的 id 判断 —— 那种写法最容易出现
    "有的页面能点、有的页面点了没反应"，而这类静默不一致正是第 112 批
    用户报"私信功能用不了"的原因之一。

    两条路都留着（刻意）：
      · **点头像**  → 直接打开与这个人的私信（本次要求）
      · **点昵称**  → 去他的个人主页（`router-link` 那部分）
    两者不冲突，用户不必再"先进主页才能发私信"。

    ---------------------------------------------------------------------------
    自己的头像不跳转
    ---------------------------------------------------------------------------
    给自己发私信没有意义，后端也不提供这个能力（会话是双方参与算出来的）。
    点自己的头像**什么都不做**，并且不给 hover 提示 —— 免得用户以为能点。

    ---------------------------------------------------------------------------
    为什么不必先判断登录
    ---------------------------------------------------------------------------
    `/messages` 的路由 meta 里有 `requiresAuth: true`，未登录时路由守卫会把
    用户送到登录页并带上 `redirect`，登录后自动回到这个会话。
    在这里再判一次反而会让"点头像没反应"重新出现（未登录时静默失败）。
  -->
  <!--
    ⚠️ 为什么外面要套一个 `<span>`（第 113 批实测得出的）：
    Element Plus 的 `el-tooltip` 是 `inheritAttrs: false`，**它不会把父组件传下来的
    `class` 透传给子元素**。所以当根元素是 `el-tooltip` 时，
    调用方写的 `class="post-avatar"` 会**凭空消失**（实测 DOM 里根本找不到该类），
    而 `ForumBoardView` 的 `.post-avatar { background: … }` 正是靠它选中头像的 ——
    结果就是头像底色变回 Element Plus 的默认灰。

    套一层真实元素后：类名落在 span 上（稳定可见），内部用 `:deep(.el-avatar)`
    把观感打到圆上。`display: inline-flex` 是为了让它的盒模型与原头像一致
    （原来是 span 的 el-avatar，也是 inline-flex）。
  -->
  <span class="user-avatar-slot">
    <el-tooltip
      :content="clickable ? t('profile.messageUser', { name: username || '' }) : ''"
      :disabled="!clickable"
      placement="top"
      :show-after="350"
    >
      <el-avatar
        :size="size"
        :src="avatar || undefined"
        class="user-avatar-link"
        :class="{ 'is-clickable': clickable }"
        :data-user-id="userId || ''"
        @click.stop.prevent="openMessage"
      >
        {{ initial }}
      </el-avatar>
    </el-tooltip>
  </span>
</template>

<script>
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';

export default {
  name: 'UserAvatarLink',
  props: {
    /** 目标用户 id。缺失（数据不全）时退化成"不可点"的纯展示头像 */
    userId: { type: [Number, String], default: null },
    username: { type: String, default: '' },
    avatar: { type: String, default: '' },
    size: { type: [Number, String], default: 40 },
  },
  setup(props) {
    const { t } = useI18n();
    const router = useRouter();
    const authStore = useAuthStore();

    const initial = computed(() => (
      props.username ? props.username[0].toUpperCase() : 'U'
    ));

    /** 能点私信的条件：有 id，且**不是自己** */
    const clickable = computed(() => {
      if (!props.userId) return false;
      const me = authStore.user?.id;
      // 未登录时 me 为 undefined，此时仍然可点 —— 交给路由守卫去引导登录
      return !me || Number(me) !== Number(props.userId);
    });

    const openMessage = () => {
      if (!clickable.value) return;
      router.push({ name: 'messages', query: { with: props.userId } });
    };

    return { t, initial, clickable, openMessage };
  },
};
</script>

<style scoped>
/* 外层插槽：只负责承载调用方传下来的 class 与 flex 布局角色 */
.user-avatar-slot {
  display: inline-flex;
  flex-shrink: 0;
  line-height: 0;
}

.user-avatar-link {
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.user-avatar-link.is-clickable {
  cursor: pointer;
}

.user-avatar-link.is-clickable:hover {
  transform: scale(1.06);
  box-shadow: 0 0 0 3px rgba(95, 176, 136, 0.35);
}
</style>
