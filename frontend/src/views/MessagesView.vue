<template>
  <div class="messages-page">
    <!-- 返回入口（第 87 批：本页从顶栏私信/通知进来，此前没有返回按钮） -->
    <BackButton />

    <!-- 页头 -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-envelope-open-text"></i></span>
        <div>
          <h1>{{ t('messages.title') }}</h1>
          <p>{{ t('messages.privateHint') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <!-- ⚠️ 第 112 批：这个按钮是**后补的**，而且它解决的是用户真实反馈
             "私信功能用不了"。查下来的结论是：收发链路完全正常（发信 201、
             未读计数、通知、"我发的"气泡都对），**缺的是"发起新会话"的入口** ——
             私信页只能显示已有会话，新会话的唯一入口是"先进对方主页再点私信"，
             而空列表时页面只写一句"还没有私信"，用户根本不知道该去哪儿找人。

             顺带发现 i18n 里 `messages` 命名空间**本来就定义了** searchPlaceholder /
             selectConversation / deleteConversation 等 10 个键，但 MessagesView
             一个都没用 —— 说明"联系人搜索"当初设计过、没实现。这里把它补上，
             并复用已有的 searchPlaceholder 文案。 -->
        <el-button type="primary" plain @click="openNewMessage">
          <i class="fas fa-pen-to-square"></i> {{ t('messages.newMessage') }}
        </el-button>
        <el-button plain :loading="loadingConversations" @click="loadConversations">
          <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <div class="messages-layout">
      <!-- 会话列表 -->
      <aside class="panel-card conversation-panel">
        <div class="panel-head">
          <span class="panel-icon"><i class="fas fa-comments"></i></span>
          <h2 class="panel-title">{{ t('messages.conversations') }}</h2>
          <span class="panel-count">{{ conversations.length }}</span>
        </div>
        <div class="panel-body">
          <el-skeleton v-if="loadingConversations" :rows="4" animated />
          <el-empty v-else-if="conversations.length === 0" :description="t('messages.emptyConversations')" :image-size="70" />
          <ul v-else class="conversation-list">
            <li
              v-for="item in conversations"
              :key="item.other.id || item.other.username"
              class="conversation-item"
              :class="{ 'is-active': activeUserId === item.other.id }"
              @click="openConversation(item.other.id)"
            >
              <el-avatar :size="38" :src="item.other.avatar || undefined">
                {{ item.other.username ? item.other.username[0].toUpperCase() : 'U' }}
              </el-avatar>
              <div class="conversation-info">
                <div class="conversation-top">
                  <span class="conversation-name">{{ item.other.username }}</span>
                  <span class="conversation-time">{{ relativeTime(item.last_time) }}</span>
                </div>
                <div class="conversation-bottom">
                  <span class="conversation-last">{{ item.last_message }}</span>
                  <span v-if="item.unread" class="conversation-badge">{{ item.unread }}</span>
                </div>
              </div>
            </li>
          </ul>
        </div>
      </aside>

      <!-- 聊天窗口 -->
      <section class="panel-card chat-panel">
        <template v-if="activeUser">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-user"></i></span>
            <h2 class="panel-title">{{ activeUser.username }}</h2>
            <div class="panel-head-right">
              <el-button size="small" text @click="goProfile(activeUser.id)">
                <i class="fas fa-id-card"></i> {{ t('messages.viewProfile') }}
              </el-button>
              <!-- 删除会话（第 114 批）：两个软删字段从第 42 批就在库里，一直没有接口去写 -->
              <el-button
                size="small"
                text
                type="danger"
                :title="t('messages.deleteConversation')"
                @click="confirmDeleteConversation"
              >
                <i class="fas fa-trash-can"></i>
              </el-button>
            </div>
          </div>

          <div ref="threadRef" class="chat-thread" @scroll.passive="onThreadScroll">
            <el-skeleton v-if="loadingMessages" :rows="5" animated />
            <template v-else>
              <!-- 往上翻历史（第 114 批）。原来只能看最近一页，更早的取不到。 -->
              <div v-if="hasMore" class="load-older">
                <el-button size="small" text :loading="loadingOlder" @click="loadOlder">
                  <i class="fas fa-clock-rotate-left"></i>
                  {{ t('messages.loadOlder') }}
                </el-button>
              </div>

              <p v-if="messages.length === 0" class="chat-empty">
                {{ t('messages.emptyThread') }}
              </p>
              <div
                v-for="message in messages"
                :key="message.id"
                class="chat-row"
                :class="{ 'is-mine': isMine(message) }"
              >
                <el-avatar v-if="!isMine(message)" :size="30" :src="message.sender.avatar || undefined">
                  {{ message.sender.username[0]?.toUpperCase() }}
                </el-avatar>
                <div class="chat-bubble">
                  <!-- 图片消息（第 114 批）：点开看大图 -->
                  <el-image
                    v-if="parsed(message).kind === 'image'"
                    class="chat-image"
                    :src="parsed(message).url"
                    :preview-src-list="[parsed(message).url]"
                    :preview-teleported="true"
                    fit="cover"
                  />
                  <p v-else class="chat-text">{{ parsed(message).text }}</p>
                  <span class="chat-time">
                    {{ formatTime(message.created_at) }}
                    <!-- 已读回执（第 114 批）：只标我发的最后一条，避免每条都挂一个"已读" -->
                    <em v-if="isMine(message) && message.id === lastMineId" class="chat-read-state">
                      · {{ message.read_at ? t('messages.read') : t('messages.unread') }}
                    </em>
                  </span>
                </div>
              </div>
            </template>
          </div>

          <div class="chat-compose">
            <el-input
              v-model="draft"
              type="textarea"
              :rows="3"
              resize="none"
              maxlength="1000"
              show-word-limit
              :placeholder="t('messages.composePlaceholder')"
              @keydown.enter.exact.prevent="send"
            />
            <div class="chat-compose-actions">
              <span class="compose-hint">
                <i class="fas fa-shield-halved"></i> {{ t('messages.sensitiveHint') }}
              </span>
              <!-- 发图片（第 114 批）：复用已有的上传接口，不另开一套 -->
              <input
                ref="imageInput"
                type="file"
                accept="image/*"
                class="d-none"
                @change="sendImage"
              />
              <el-button
                :loading="sendingImage"
                :title="t('messages.sendImage')"
                @click="pickImage"
              >
                <i class="fas fa-image"></i>
              </el-button>
              <el-button type="primary" :loading="sending" :disabled="!draft.trim()" @click="send">
                <i class="fas fa-paper-plane"></i> {{ t('messages.send') }}
              </el-button>
            </div>
          </div>
        </template>

        <div v-else class="chat-placeholder">
          <i class="fas fa-envelope-open-text"></i>
          <p>{{ t('messages.pickConversation') }}</p>
        </div>
      </section>
    </div>

    <!-- ⚠️ 第 112 批：发起新私信（搜人）的弹窗。
         没有它的时候，空会话列表等于"这个功能用不了"—— 用户只能等别人先找他。 -->
    <el-dialog
      v-model="newMessageVisible"
      :title="t('messages.newMessageTitle')"
      width="460px"
      class="form-dialog"
    >
      <el-input
        v-model="searchKeyword"
        :placeholder="t('messages.searchPlaceholder')"
        clearable
        @input="onSearchInput"
      >
        <template #prefix><i class="fas fa-magnifying-glass"></i></template>
      </el-input>
      <p class="search-hint">
        <i class="fas fa-circle-info"></i> {{ t('messages.searchHint') }}
      </p>

      <div v-if="searching" class="search-loading">
        <el-skeleton :rows="3" animated />
      </div>
      <!-- 关键词太短时后端会回一句 detail（不是报错），直接显示它 -->
      <p v-else-if="searchHint" class="search-empty">{{ searchHint }}</p>
      <p v-else-if="searchResults.length === 0" class="search-empty">
        {{ searchKeyword.trim().length >= 2 ? t('messages.searchEmpty') : '' }}
      </p>
      <ul v-else class="search-results">
        <li
          v-for="user in searchResults"
          :key="user.id"
          class="search-item"
          @click="startChatWith(user)"
        >
          <el-avatar :size="34" :src="user.avatar || undefined">
            {{ user.username ? user.username[0].toUpperCase() : 'U' }}
          </el-avatar>
          <div class="search-info">
            <span class="search-name">{{ user.username }}</span>
            <span v-if="user.bio" class="search-bio">{{ user.bio }}</span>
          </div>
          <el-button size="small" type="primary" plain>
            {{ t('messages.startChat') }}
          </el-button>
        </li>
      </ul>
    </el-dialog>
  </div>
</template>

<script>
/**
 * 私信页（第 42 批）
 * ------------------------------------------------------------------
 * 左侧会话列表 + 右侧聊天窗口。进入页面可用 `?with=<user_id>` 直接打开某个会话
 * （通知里点"XX 给你发了私信"就是这个地址）。
 * 打开会话会把对方发来的未读标记为已读（后端在 GET 里做）。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useAuthStore } from '@/stores/auth';
import { formatTime, timeAgo } from '@/utils/date';  // 第 84 批：相对时间跟随语言
import {
  deleteConversation,
  encodeImageMessage,
  fetchConversation,
  fetchConversations,
  parseMessageContent,
  searchUsers,
  sendMessage,
} from '@/api/message';
import { uploadImage } from '@/api/forum';  // 第 114 批：图片消息复用帖子插图的上传接口
import { useI18n } from '@/i18n';  // 第 64 批：多语言
import { formatApiError } from '@/api/http';
import BackButton from '@/components/BackButton.vue';  // 第 87 批：返回按钮

/** 每页聊天记录条数（与后端的默认值一致即可，这里显式写出来便于调） */
const PAGE_SIZE = 50;

/** 打开会话时的自动刷新间隔（毫秒）。与通知铃铛/私信红点一样走轮询 */
const POLL_MS = 15000;

export default {
  name: 'MessagesView',
  components: { BackButton },  // 第 87 批：返回按钮
  setup() {
    const { t } = useI18n();  // 必须在 setup 内取，模板才能拿到（放模块顶层会 _ctx.t is not a function）
    const route = useRoute();
    const router = useRouter();
    const authStore = useAuthStore();

    const conversations = ref([]);
    const loadingConversations = ref(false);
    const messages = ref([]);
    const loadingMessages = ref(false);
    const activeUser = ref(null);
    const draft = ref('');
    const sending = ref(false);
    const sendingImage = ref(false);
    const imageInput = ref(null);
    const threadRef = ref(null);

    // ---- 往上翻历史（第 114 批）------------------------------------------
    // 后端原来的实现只能回"最近 100 条"，更早的**取不到**。
    // 现在有了 `before_id` 游标，这里就要把翻页做出来 —— 否则接口白改。
    const hasMore = ref(false);
    const loadingOlder = ref(false);
    /** 往上翻的游标：上一次响应里的 `oldest_id` */
    let oldestId = null;

    // ---- 自动刷新（第 114 批）--------------------------------------------
    // 原来的私信页**完全不会自动更新** —— 对方回了消息，我得手动点"刷新"
    // 或者退出重进才看得到。这是"看起来像坏了"的典型：消息明明发出去了。
    let pollTimer = null;

    /** 解析一条消息的正文（图片 or 文字）。解析逻辑收在 api/message.js 里，便于测试 */
    const parsed = (message) => parseMessageContent(message.content);

    /**
     * 这条消息是不是我发的。
     * ⚠️ 必须定义在 `lastMineId` **之前**：后者在 computed 里调它，
     *    `const` 有暂时性死区，顺序反了会在某些求值时机抛
     *    `Cannot access 'isMine' before initialization`（不是每次必现，更难查）。
     */
    const isMine = (message) => message.sender?.id === authStore.user?.id;

    /** 我发的最后一条消息的 id（只给它挂"已读/未读"，避免每条都挂一个） */
    const lastMineId = computed(() => {
      for (let i = messages.value.length - 1; i >= 0; i -= 1) {
        if (isMine(messages.value[i])) return messages.value[i].id;
      }
      return null;
    });

    // ---- 发起新私信（第 112 批）------------------------------------------
    const newMessageVisible = ref(false);
    const searchKeyword = ref('');
    const searchResults = ref([]);
    const searching = ref(false);
    const searchHint = ref('');
    /** 防抖计时器：搜人是逐字符请求，不防抖会打出一串无用请求 */
    let searchTimer = null;

    const openNewMessage = () => {
      searchKeyword.value = '';
      searchResults.value = [];
      searchHint.value = '';
      newMessageVisible.value = true;
    };

    const onSearchInput = () => {
      if (searchTimer) clearTimeout(searchTimer);
      // 关键词不足 2 个字：本地直接给提示，**不发请求**
      // （后端的限制也是 2 个字，提前拦住能少一半无用请求）
      if (searchKeyword.value.trim().length < 2) {
        searchResults.value = [];
        searchHint.value = searchKeyword.value.trim() ? t('messages.searchTooShort') : '';
        return;
      }
      searching.value = true;
      searchTimer = setTimeout(async () => {
        try {
          const data = await searchUsers(searchKeyword.value.trim());
          searchResults.value = data?.results || [];
          // 后端在关键词太短时会回 detail，把它当提示显示（不是错误）
          searchHint.value = data?.detail || '';
        } catch (error) {
          searchResults.value = [];
          searchHint.value = formatApiError(error, t('messages.searchEmpty'));
        } finally {
          searching.value = false;
        }
      }, 300);
    };

    /**
     * 选中某人 → 关弹窗 → 直接打开与他的会话。
     *
     * 刻意**不**要求"先发一条消息才建会话"：这个后端模型的会话是按参与双方
     * 计算出来的（`conversation_key`），没有"空会话"这种状态 ——
     * 打开一个从未聊过的人就是空聊天窗口，发送键在下面，用户自己决定说什么。
     * 这样也少一次"建会话"的接口往返。
     */
    const startChatWith = (user) => {
      newMessageVisible.value = false;
      openConversation(user.id);
    };

    const activeUserId = computed(() => activeUser.value?.id ?? null);

    // （`isMine` 已在上面定义 —— 它要早于 `lastMineId`，见那处的说明。）

    // 第 84 批：本地这份相对时间实现已并入共享的 timeAgo（跟随界面语言），
    // 这里只留一层薄封装，避免同一套逻辑两处各写一份、改一处漏一处。
    const relativeTime = (value) => timeAgo(value);

    const scrollToBottom = async () => {
      await nextTick();
      const el = threadRef.value;
      if (el) el.scrollTop = el.scrollHeight;
    };

    const loadConversations = async () => {
      loadingConversations.value = true;
      try {
        const data = await fetchConversations();
        conversations.value = data?.results || [];
      } catch (error) {
        console.warn('加载会话失败:', error);
        conversations.value = [];
      } finally {
        loadingConversations.value = false;
      }
    };

    const openConversation = async (userId) => {
      if (!userId) return;
      loadingMessages.value = true;
      activeUser.value = { id: userId, username: t('common.loading'), avatar: null };
      try {
        // 不带 before_id → 最新一页，同时后端会把未读标记为已读
        const data = await fetchConversation(userId, { page_size: PAGE_SIZE });
        activeUser.value = data.other;
        messages.value = data.results || [];
        hasMore.value = Boolean(data.has_more);
        oldestId = data.oldest_id ?? null;
        await scrollToBottom();
        // 打开会话后刷新会话列表（未读数会变）
        loadConversations();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('messages.openFailed')));
        activeUser.value = null;
      } finally {
        loadingMessages.value = false;
      }
    };

    /**
     * 往上翻历史（第 114 批）。
     *
     * ⚠️ 关键点：**翻页后要把滚动位置补回去**。
     * 在顶部插入内容时浏览器不会保持视口 —— 不补偿的话用户会"跳"到
     * 刚插入内容的中间，看起来像页面自己乱滚。
     * 做法：记下插入前的 `scrollHeight`，插入后把 `scrollTop` 加上增量。
     */
    const loadOlder = async () => {
      if (!activeUser.value || !hasMore.value || loadingOlder.value || !oldestId) return;
      loadingOlder.value = true;
      const el = threadRef.value;
      const prevHeight = el ? el.scrollHeight : 0;
      const prevTop = el ? el.scrollTop : 0;
      try {
        const data = await fetchConversation(activeUser.value.id, {
          page_size: PAGE_SIZE,
          before_id: oldestId,
        });
        const older = data.results || [];
        if (older.length) {
          messages.value = [...older, ...messages.value];
        }
        hasMore.value = Boolean(data.has_more);
        oldestId = data.oldest_id ?? oldestId;
        await nextTick();
        if (el) {
          // 补回滚动位置：新增内容的高度差加到原来的 scrollTop 上
          el.scrollTop = prevTop + (el.scrollHeight - prevHeight);
        }
      } catch (error) {
        ElMessage.error(formatApiError(error, t('messages.loadOlderFailed')));
      } finally {
        loadingOlder.value = false;
      }
    };

    /**
     * 滚到顶部附近时自动加载更早的消息。
     *
     * 阈值 80px 而不是 0：用户几乎不可能正好停在 0，
     * 而且要等"滚动事件恰好落在 0"才加载，体验上像是卡住了。
     */
    const onThreadScroll = () => {
      const el = threadRef.value;
      if (!el) return;
      if (el.scrollTop <= 80) loadOlder();
    };

    /** 静默刷新当前会话（轮询用）：不显示骨架屏、不打断滚动 */
    const refreshActiveConversation = async () => {
      const userId = activeUser.value?.id;
      if (!userId) return;
      if (document.visibilityState !== 'visible') return;  // 页面不在前台就别打扰后端
      try {
        const data = await fetchConversation(userId, { page_size: PAGE_SIZE });
        const incoming = data.results || [];
        // 只在"有新消息"时替换，避免把用户正在往上翻的历史整段冲掉
        const lastKnown = messages.value.length ? messages.value[messages.value.length - 1].id : null;
        const newest = incoming.length ? incoming[incoming.length - 1].id : null;
        const grew = newest !== null && newest !== lastKnown;
        const unreadArrived = incoming.some((m) => !m.is_read && !isMine(m));
        if (grew) {
          // 新消息来了才整体替换 + 滚到底（用户本来就在看最新）
          messages.value = incoming;
          hasMore.value = Boolean(data.has_more);
          await scrollToBottom();
          if (unreadArrived) loadConversations();
        } else {
          // 没有新消息，但**已读状态可能变了**（对方刚读了我发的）——
          // 只把 read_at / is_read 同步过来，不动列表结构，也就不影响滚动位置。
          const byId = new Map(incoming.map((m) => [m.id, m]));
          messages.value = messages.value.map((m) => {
            const fresh = byId.get(m.id);
            return fresh ? { ...m, is_read: fresh.is_read, read_at: fresh.read_at } : m;
          });
        }
      } catch (error) {
        // 轮询失败**不打扰用户**：下一轮会再试，弹错误框反而像功能坏了
        console.warn('刷新会话失败:', error);
      }
    };

    const send = async () => {
      const content = draft.value.trim();
      if (!content || !activeUser.value) return;
      sending.value = true;
      try {
        const message = await sendMessage(activeUser.value.id, content);
        messages.value.push(message);
        draft.value = '';
        await scrollToBottom();
        loadConversations();  // 会话列表的"最后一条"要跟着更新
      } catch (error) {
        ElMessage.error(formatApiError(error, t('msg.requestFailed')));
      } finally {
        sending.value = false;
      }
    };

    /** 触发隐藏的图片选择框（与识别页同一套做法：不点系统对话框，转发 click） */
    const pickImage = () => imageInput.value?.click();

    /** 发一张图片（第 114 批） */
    const sendImage = async (event) => {
      const file = event?.target?.files?.[0];
      // 必须清空 input 的 value：否则选同一个文件第二次不会触发 change
      if (event?.target) event.target.value = '';
      if (!file || !activeUser.value) return;

      sendingImage.value = true;
      try {
        // ⚠️ 两点容易写错（我都踩了）：
        //   1. `uploadImage()` 收的是 **FormData**，不是裸 File；
        //   2. 它**已经解包过**（`.then(res => res.data)`），所以拿的是
        //      `{url, image_url, message}`，不要再 `.data`。
        // 后端会做大小（5MB）/真实格式/文件名随机化三重校验，这里不重复判。
        const form = new FormData();
        form.append('image', file);
        const { url } = await uploadImage(form);
        if (!url) throw new Error('上传接口没有返回图片地址');
        const message = await sendMessage(activeUser.value.id, encodeImageMessage(url));
        messages.value.push(message);
        await scrollToBottom();
        loadConversations();  // 会话列表的"最后一条"会显示成 [图片]
      } catch (error) {
        ElMessage.error(formatApiError(error, t('messages.sendImageFailed')));
      } finally {
        sendingImage.value = false;
      }
    };

    /** 删除与当前对象的整个会话（第 114 批） */
    const confirmDeleteConversation = async () => {
      const user = activeUser.value;
      if (!user) return;
      try {
        await ElMessageBox.confirm(
          t('messages.deleteConfirm', { name: user.username }),
          t('messages.deleteConversation'),
          { type: 'warning', confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel') },
        );
      } catch {
        return;  // 用户取消
      }
      try {
        await deleteConversation(user.id);
        ElMessage.success(t('messages.deleted'));
        // 当前会话已经不属于我了 → 清空右侧，回到"选一个会话"的状态
        activeUser.value = null;
        messages.value = [];
        hasMore.value = false;
        oldestId = null;
        await loadConversations();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('messages.deleteFailed')));
      }
    };

    // ⚠️ 第 112 批修：这里原来写的是 `name: 'userProfile'`，而路由表里注册的名字是
    //    **`user-profile`**（带连字符）。名字对不上时 vue-router **不报错、不跳转**，
    //    只往控制台打一条 warn —— 表现就是"点了没反应"。
    //    同类错误在这个文件里找不到第二处，但项目里有一处同样的
    //    （`UserProfileView.vue` 的关注列表跳个人主页），两处一起修了。
    //    全项目 26 处按名字跳转里就这 2 处名字无效（已用脚本对着路由表核过）。
    const goProfile = (id) => router.push({ name: 'user-profile', params: { id } });

    onMounted(async () => {
      await loadConversations();
      const withId = Number(route.query.with);
      if (withId) {
        openConversation(withId);
      } else if (conversations.value.length) {
        openConversation(conversations.value[0].other.id);
      }
      // 第 114 批：自动刷新。原来私信页**完全不会更新** ——
      // 对方回了消息必须手动点"刷新"或退出重进才看得到，
      // 表现上就和"消息没发出去/收不到"一样。
      // 与通知铃铛、未读红点保持同一套约定：15 秒一轮，页面不可见时跳过
      // （`refreshActiveConversation` 内部会判断，这里不必重复）。
      pollTimer = setInterval(() => {
        refreshActiveConversation();
        // 会话列表也顺带刷新 —— 别人给我发的新会话要能出现
        if (document.visibilityState === 'visible') loadConversations();
      }, POLL_MS);
    });

    onBeforeUnmount(() => {
      // 不清理的话，离开页面后计时器还在跑（会一直请求后端，还会在
      // 组件已销毁后改 ref）。轮询类功能最容易漏这一步。
      if (pollTimer) clearInterval(pollTimer);
      if (searchTimer) clearTimeout(searchTimer);
    });

    return {
      t,
      conversations,
      loadingConversations,
      messages,
      loadingMessages,
      activeUser,
      activeUserId,
      draft,
      sending,
      sendingImage,
      imageInput,
      threadRef,
      isMine,
      relativeTime,
      formatTime,
      loadConversations,
      openConversation,
      send,
      pickImage,
      sendImage,
      goProfile,
      // 第 112 批：发起新私信。**必须全部 return** ——
      // 本项目在"setup 里定义了却没 return"上踩过三次
      // （第 64/67/68 批：MessagesView / MessageEntry / NotificationBell），
      // 现象是模板渲染时 `_ctx.xxx is not a function`，而 type-check 不报。
      // `component-wiring.spec.js` 会静态检查这件事。
      newMessageVisible,
      searchKeyword,
      searchResults,
      searching,
      searchHint,
      openNewMessage,
      onSearchInput,
      startChatWith,
      // 第 114 批：翻历史 / 已读回执 / 删除会话
      parsed,
      lastMineId,
      hasMore,
      loadingOlder,
      loadOlder,
      onThreadScroll,
      confirmDeleteConversation,
    };
  },
};
</script>

<style scoped>
.messages-page {
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 24px 20px 40px;
}

/* 第 87 批：返回按钮紧贴左边缘（页面本就是左对齐块级容器，这里只留一点底距） */
.messages-page > .back-button {
  margin-bottom: 12px;
}

.messages-layout {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.conversation-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 560px;
  overflow-y: auto;
}

.conversation-item {
  display: flex;
  gap: 10px;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.18s ease;
}

.conversation-item:hover {
  background: var(--brand-50);
}

.conversation-item.is-active {
  border-color: var(--brand-300);
  background: var(--brand-50);
}

.conversation-info {
  flex: 1;
  min-width: 0;
}

.conversation-top,
.conversation-bottom {
  display: flex;
  align-items: center;
  gap: 8px;
}

.conversation-name {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--ink-800);
}

.conversation-time {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--ink-400);
}

.conversation-last {
  font-size: 12.5px;
  color: var(--ink-500);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-badge {
  margin-left: auto;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: #cf4436;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

/* 聊天窗口 */
.chat-panel {
  display: flex;
  flex-direction: column;
  min-height: 560px;
}

.chat-thread {
  flex: 1;
  max-height: 430px;
  overflow-y: auto;
  padding: 16px 18px;
  background: linear-gradient(180deg, #f8fcfa, #ffffff);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-empty {
  margin: 30px 0;
  text-align: center;
  font-size: 13px;
  color: var(--ink-400);
}

/* ---- 第 114 批：往上翻历史 / 图片消息 / 已读状态 ---------------------- */
.load-older {
  display: flex;
  justify-content: center;
  padding: 4px 0 10px;
}

/* 图片消息：限制最大宽度与高度，别让一张大图把整个聊天窗口撑爆。
   点开可看原图（el-image 的 preview）。 */
.chat-image {
  display: block;
  max-width: 240px;
  max-height: 240px;
  border-radius: 10px;
  cursor: zoom-in;
}

/* 已读/未读：跟在时间后面，字号更小、颜色更淡 ——
   它是次要信息，不该和消息正文争注意力。 */
.chat-read-state {
  margin-left: 4px;
  font-style: normal;
  opacity: 0.75;
}

.chat-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.chat-row.is-mine {
  flex-direction: row-reverse;
}

.chat-bubble {
  max-width: 68%;
  padding: 9px 12px;
  border: 1px solid var(--brand-100);
  border-radius: 12px;
  background: #fff;
  box-shadow: var(--shadow-xs);
}

.chat-row.is-mine .chat-bubble {
  border-color: var(--brand-300);
  background: linear-gradient(160deg, #eaf7f0, #f7fdfa);
}

.chat-text {
  margin: 0 0 4px;
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--ink-800);
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-time {
  font-size: 11px;
  color: var(--ink-400);
}

.chat-compose {
  padding: 14px 18px 16px;
  border-top: 1px solid var(--border);
  background: #fff;
}

.chat-compose-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
}

.compose-hint {
  font-size: 12px;
  color: var(--ink-400);
}

.compose-hint i {
  margin-right: 4px;
  color: var(--brand-500);
}

.chat-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--ink-400);
  font-size: 13px;
}

.chat-placeholder i {
  font-size: 34px;
  color: var(--brand-300);
}

/* ---- 发起新私信的弹窗（第 112 批）------------------------------------ */
.search-hint {
  margin: 8px 0 12px;
  font-size: 12.5px;
  color: var(--ink-500, #6b7c73);
}

.search-hint i {
  margin-right: 4px;
}

.search-empty {
  margin: 18px 0;
  text-align: center;
  font-size: 13.5px;
  color: var(--ink-500, #6b7c73);
}

.search-loading {
  padding: 8px 0;
}

.search-results {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 320px;
  overflow-y: auto;
}

.search-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 8px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.search-item:hover {
  background: var(--brand-50, #eef7f1);
}

.search-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.search-name {
  font-weight: 600;
  color: var(--ink-800, #24352c);
  /* 用户名可能很长，别把"开始聊天"按钮挤出去 */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-bio {
  font-size: 12px;
  color: var(--ink-500, #6b7c73);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 900px) {
  .messages-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>

