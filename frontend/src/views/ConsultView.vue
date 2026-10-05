<template>
  <div class="consult-page">
    <!-- 页头 -->
    <header class="admin-hero">
      <div class="admin-hero-main">
        <span class="admin-hero-icon"><i class="fas fa-user-doctor"></i></span>
        <div>
          <h1>{{ t('consult.title') }}</h1>
          <p>{{ t('consult.subtitle') }}</p>
        </div>
      </div>
      <div class="admin-hero-actions">
        <el-button plain :loading="loading" @click="loadAll">
          <i class="fas fa-sync-alt"></i> {{ t('consult.refresh') }}
        </el-button>
        <el-button type="primary" @click="askDialog = true">
          <i class="fas fa-circle-question"></i> {{ t('consult.askQuestion') }}
        </el-button>
      </div>
    </header>

    <!-- 状态筛选 -->
    <div class="filter-bar">
      <button
        v-for="tab in tabs"
        :key="tab.value"
        type="button"
        class="filter-tab"
        :class="{ 'is-active': tab.value === activeTab }"
        @click="switchTab(tab.value)"
      >
        {{ tab.label }}
        <span v-if="tab.count !== null" class="tab-count">{{ tab.count }}</span>
      </button>
    </div>

    <div class="consult-main">
      <!-- 问题列表 -->
      <section class="panel-card">
        <div class="panel-body">
          <el-skeleton v-if="loading" :rows="6" animated />
          <el-empty v-else-if="!questions.length" :description="t('consult.emptyQuestions')" :image-size="80" />
          <ul v-else class="question-list">
            <li
              v-for="item in questions"
              :key="item.id"
              class="question-item"
              :class="{ 'is-closed': item.status === 'closed' }"
              @click="openDetail(item.id)"
            >
              <div class="question-head">
                <span v-if="item.crop_type" class="crop-tag">{{ localizedField(item, 'crop_type') }}</span>
                <span class="status-chip" :class="`is-${item.status}`">{{ statusLabel(item.status, item.status_display) }}</span>
                <strong class="question-title">{{ item.title }}</strong>
              </div>
              <p class="question-excerpt">{{ item.content }}</p>
              <div class="question-meta">
                <span><i class="fas fa-user"></i> {{ item.asker?.username }}</span>
                <span><i class="fas fa-clock"></i> {{ formatTime(item.created_at) }}</span>
                <span><i class="fas fa-comments"></i> {{ t('consult.answerCount', { count: item.answer_count }) }}</span>
                <span v-if="item.accepted_answer_id" class="accepted-flag">
                  <i class="fas fa-circle-check"></i> {{ t('consult.accepted') }}
                </span>
              </div>
            </li>
          </ul>
        </div>
      </section>

      <!-- 专家列表 -->
      <aside class="consult-side">
        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-user-tie"></i></span>
            <h2 class="panel-title">{{ t('consult.expertsTitle') }}</h2>
            <span class="panel-count">{{ t('consult.expertsCount', { count: experts.length }) }}</span>
          </div>
          <div class="panel-body">
            <el-empty v-if="!experts.length" :description="t('consult.emptyExperts')" :image-size="60" />
            <ul v-else class="expert-list">
              <li v-for="item in experts" :key="item.user.id" class="expert-item">
                <el-avatar :size="36" :src="item.user.avatar || undefined">
                  {{ item.user.username?.[0]?.toUpperCase() }}
                </el-avatar>
                <div class="expert-info">
                  <span class="expert-name">
                    {{ item.user.username }}
                    <em v-if="item.title">{{ item.title }}</em>
                  </span>
                  <span class="expert-meta">
                    {{ t('consult.expertStats', { answered: item.answered_count, accepted: item.accepted_count }) }}
                    <template v-if="item.specialties.length"> · {{ t('consult.specialties') }} {{ item.specialties.join('/') }}</template>
                  </span>
                </div>
                <!-- 第 76 批：此前只能"授予"不能"取消"（revokeExpert 接口早就有了，
                     只是这个页面从未引用过），管理员授错了就没有回头路 -->
                <el-button
                  v-if="isAdmin"
                  size="small"
                  type="danger"
                  link
                  class="expert-revoke"
                  :loading="revokingId === item.user.id"
                  @click.stop="doRevoke(item)"
                >
                  <i class="fas fa-user-slash"></i> {{ t('consult.revokeExpert') }}
                </el-button>
              </li>
            </ul>

            <!-- 管理员授予专家 -->
            <div v-if="isAdmin" class="grant-box">
              <p class="grant-title"><i class="fas fa-user-plus"></i> {{ t('consult.grantExpert') }}</p>
              <el-select
                v-model="grantUserId"
                filterable
                remote
                :remote-method="searchUserOptions"
                :loading="searchingUsers"
                :placeholder="t('consult.searchUser')"
                class="full-width"
              >
                <el-option
                  v-for="user in userOptions"
                  :key="user.id"
                  :value="user.id"
                  :label="user.username"
                />
              </el-select>
              <el-input v-model="grantTitle" :placeholder="t('consult.titlePlaceholder')" class="grant-input" />
              <el-input v-model="grantSpecialties" :placeholder="t('consult.fieldsPlaceholder')" class="grant-input" />
              <el-button type="primary" :loading="granting" :disabled="!grantUserId" @click="doGrant">
                {{ t('consult.grant') }}
              </el-button>
            </div>
          </div>
        </section>
      </aside>
    </div>

    <!-- 提问弹窗 -->
    <el-dialog v-model="askDialog" width="560px" class="form-dialog" :close-on-click-modal="false">
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon"><i class="fas fa-circle-question"></i></span>
          <div>
            <h3>{{ t('consult.askQuestion') }}</h3>
            <p>{{ t('consult.askHint') }}</p>
          </div>
        </div>
      </template>
      <div class="form-dialog-body">
        <el-form label-position="top">
          <el-form-item :label="t('consult.cropLabel')">
            <el-input v-model="askForm.crop_type" :placeholder="t('consult.cropPlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('consult.questionTitle')">
            <el-input v-model="askForm.title" maxlength="200" :placeholder="t('consult.questionTitlePlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('consult.questionDetail')">
            <el-input
              v-model="askForm.content"
              type="textarea"
              :rows="5"
              resize="none"
              maxlength="1000"
              show-word-limit
              :placeholder="t('consult.questionDetailPlaceholder')"
            />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <div class="form-dialog-footer">
          <span class="footer-hint"><i class="fas fa-bell"></i> {{ t('consult.notifyExperts') }}</span>
          <span>
            <el-button @click="askDialog = false">{{ t('consult.cancel') }}</el-button>
            <el-button type="primary" :loading="asking" @click="submitQuestion">{{ t('consult.submitQuestion') }}</el-button>
          </span>
        </div>
      </template>
    </el-dialog>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailDialog" width="720px" top="6vh" class="form-dialog">
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon"><i class="fas fa-comments"></i></span>
          <div>
            <h3>{{ detail?.title }}</h3>
            <p>
              {{ localizedField(detail, 'crop_type') || t('common.noCrop') }} ·
              {{ detail?.asker?.username }} · {{ formatTime(detail?.created_at) }}
            </p>
          </div>
        </div>
      </template>
      <div class="form-dialog-body">
        <el-skeleton v-if="detailLoading" :rows="5" animated />
        <template v-else-if="detail">
          <p class="detail-content">{{ detail.content }}</p>

          <div class="detail-status">
            <span class="status-chip" :class="`is-${detail.status}`">{{ statusLabel(detail.status, detail.status_display) }}</span>
            <span class="detail-meta">{{ t('consult.detailStats', { answers: detail.answer_count, views: detail.view_count }) }}</span>
          </div>

          <section class="answer-section">
            <h4 class="answer-section-title">{{ t('consult.expertAnswer') }}</h4>
            <el-empty v-if="!detail.answers.length" :description="t('consult.emptyAnswers')" :image-size="60" />
            <ul v-else class="answer-list">
              <li
                v-for="answer in detail.answers"
                :key="answer.id"
                class="answer-item"
                :class="{ 'is-accepted': answer.is_accepted }"
              >
                <div class="answer-head">
                  <span class="answer-author">
                    <i class="fas fa-user-tie"></i> {{ answer.author?.username }}
                    <em v-if="answer.author_title">{{ localizedField(answer, 'author_title') }}</em>
                  </span>
                  <span class="answer-time">{{ formatTime(answer.created_at) }}</span>
                  <span v-if="answer.is_accepted" class="accepted-flag">
                    <i class="fas fa-circle-check"></i> {{ t('consult.accepted') }}
                  </span>
                </div>
                <p class="answer-content">{{ answer.content }}</p>
                <div
                  v-if="detail.is_mine && !answer.is_accepted && detail.status !== 'closed'"
                  class="answer-actions"
                >
                  <el-button size="small" type="success" plain @click="doAccept(answer)">
                    <i class="fas fa-check"></i> {{ t('consult.acceptThis') }}
                  </el-button>
                </div>
              </li>
            </ul>
          </section>

          <!-- 专家作答区 -->
          <section v-if="canAnswer && detail.status !== 'closed'" class="answer-compose">
            <h4 class="answer-section-title">
              <i class="fas fa-pen"></i> {{ t('consult.answerTitle') }}
              <span class="compose-role">{{ t('consult.answerWho') }}</span>
            </h4>
            <el-input
              v-model="answerDraft"
              type="textarea"
              :rows="4"
              resize="none"
              maxlength="2000"
              show-word-limit
              :placeholder="t('consult.answerPlaceholder')"
            />
            <div class="compose-actions">
              <span class="compose-hint">{{ t('consult.answerNotify') }}</span>
              <el-button type="primary" :loading="answering" :disabled="!answerDraft.trim()" @click="submitAnswer">
                {{ t('consult.submitAnswer') }}
              </el-button>
            </div>
          </section>
          <p v-else-if="!canAnswer && detail.status !== 'closed'" class="compose-tip">
            <i class="fas fa-circle-info"></i> {{ t('consult.expertOnly') }}
          </p>
        </template>
      </div>
      <template #footer>
        <div class="form-dialog-footer">
          <span class="footer-hint">
            <template v-if="detail?.is_mine && detail?.status !== 'closed'">
              <el-button size="small" text @click="doClose">{{ t('consult.closeQuestion') }}</el-button>
            </template>
          </span>
          <span><el-button @click="detailDialog = false">{{ t('consult.close') }}</el-button></span>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script>
/**
 * 专家咨询（第 49 批）
 * ------------------------------------------------------------------
 * 与论坛的区别：**只有专家/管理员能回答**，并且提问者可以**采纲**一个最佳答案。
 * 列表按状态筛选（待回答 / 已解答 / 我的提问 / 全部）；详情用弹窗，避免多一个路由。
 */
import { computed, onMounted, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  acceptAnswer, closeQuestion, createAnswer, createQuestion,
  fetchExperts, fetchQuestion, fetchQuestions, grantExpert, revokeExpert, searchUsers,
} from '@/api/consult';
import { formatApiError } from '@/api/http';
import { formatTime } from '@/utils/date';
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';  // 第 65 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 78 批：作物名等内容数据多语言

export default {
  name: 'ConsultView',
  setup() {
    const { t } = useI18n();  // 第 65 批：多语言
    const { localizedField } = useLocalized();  // 第 78 批
    const authStore = useAuthStore();

    /**
     * 第 78 批：提问状态文案
     * ------------------------------------------------------------------
     * 原来直接渲染后端的 `status_display`（Django choices 的中文：待回答/已解答/已关闭），
     * 英文界面下这三个字一直是中文。状态是**固定枚举**，改走 i18n。
     */
    const STATUS_KEYS = {
      open: 'consult.statusOpen',
      answered: 'consult.statusAnswered',
      closed: 'consult.statusClosed',
    };
    const statusLabel = (status, fallback) =>
      STATUS_KEYS[status] ? t(STATUS_KEYS[status]) : fallback || status || '';

    const loading = ref(false);
    const questions = ref([]);
    const statusCounts = ref({ open: 0, answered: 0, closed: 0 });
    const activeTab = ref('open');
    const experts = ref([]);

    const askDialog = ref(false);
    const asking = ref(false);
    const askForm = ref({ crop_type: '', title: '', content: '' });

    const detailDialog = ref(false);
    const detailLoading = ref(false);
    const detail = ref(null);
    const answerDraft = ref('');
    const answering = ref(false);

    const grantUserId = ref(null);
    const grantTitle = ref('');
    const grantSpecialties = ref('');
    const granting = ref(false);
    const searchingUsers = ref(false);
    const userOptions = ref([]);
    const revokingId = ref(null);  // 第 76 批：正在取消的专家 user id（按钮 loading）

    const isAdmin = computed(() => Boolean(authStore.isAdmin));
    // 是否具备作答资格：管理员天然可以，其余看后端返回的专家列表
    const canAnswer = computed(() => {
      if (isAdmin.value) return true;
      const me = authStore.user?.id;
      return experts.value.some((item) => item.user.id === me);
    });

    const tabs = computed(() => [
      { value: 'open', label: t('consult.tabPending'), count: statusCounts.value.open },
      { value: 'answered', label: t('consult.tabAnswered'), count: statusCounts.value.answered },
      { value: 'closed', label: t('consult.tabClosed'), count: statusCounts.value.closed },
      { value: 'mine', label: t('consult.tabMine'), count: null },
    ]);

    const loadQuestions = async () => {
      loading.value = true;
      try {
        const params = activeTab.value === 'mine' ? { mine: true } : { status: activeTab.value };
        const data = await fetchQuestions({ ...params, page_size: 20 });
        questions.value = data.results || [];
        statusCounts.value = data.status_counts || { open: 0, answered: 0, closed: 0 };
      } catch (error) {
        ElMessage.error(formatApiError(error, t('consult.loadQuestionsFailed')));
      } finally {
        loading.value = false;
      }
    };

    const loadExperts = async () => {
      try {
        const data = await fetchExperts();
        experts.value = data.results || [];
      } catch (error) {
        console.warn('加载专家列表失败:', error);
      }
    };

    const loadAll = async () => {
      await Promise.all([loadQuestions(), loadExperts()]);
    };

    const switchTab = (value) => {
      activeTab.value = value;
      loadQuestions();
    };

    const submitQuestion = async () => {
      if (!askForm.value.title.trim()) {
        ElMessage.warning(t('consult.titleRequired'));
        return;
      }
      if (askForm.value.content.trim().length < 5) {
        ElMessage.warning(t('consult.detailTooShort'));
        return;
      }
      asking.value = true;
      try {
        await createQuestion({
          crop_type: askForm.value.crop_type.trim(),
          title: askForm.value.title.trim(),
          content: askForm.value.content.trim(),
        });
        ElMessage.success(t('consult.questionSubmitted'));
        askDialog.value = false;
        askForm.value = { crop_type: '', title: '', content: '' };
        activeTab.value = 'open';
        await loadQuestions();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('consult.questionFailed')));
      } finally {
        asking.value = false;
      }
    };

    const openDetail = async (id) => {
      detailDialog.value = true;
      detailLoading.value = true;
      answerDraft.value = '';
      try {
        detail.value = await fetchQuestion(id);
      } catch (error) {
        ElMessage.error(formatApiError(error, t('consult.loadDetailFailed')));
        detailDialog.value = false;
      } finally {
        detailLoading.value = false;
      }
    };

    const submitAnswer = async () => {
      if (!detail.value) return;
      answering.value = true;
      try {
        await createAnswer(detail.value.id, answerDraft.value.trim());
        ElMessage.success(t('consult.answerSubmitted'));
        answerDraft.value = '';
        detail.value = await fetchQuestion(detail.value.id);
        await loadQuestions();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('consult.answerFailed')));
      } finally {
        answering.value = false;
      }
    };

    const doAccept = async (answer) => {
      try {
        await acceptAnswer(answer.id);
        ElMessage.success(t('consult.acceptedOk'));
        detail.value = await fetchQuestion(detail.value.id);
        await Promise.all([loadQuestions(), loadExperts()]);
      } catch (error) {
        ElMessage.error(formatApiError(error, t('consult.acceptFailed')));
      }
    };

    const doClose = async () => {
      try {
        await ElMessageBox.confirm(t('consult.closeConfirm'), t('consult.close'), {
          type: 'warning', confirmButtonText: t('consult.close'), cancelButtonText: t('msg.cancel'),
        });
      } catch {
        return;
      }
      try {
        await closeQuestion(detail.value.id);
        ElMessage.success(t('consult.closedOk'));
        detail.value = await fetchQuestion(detail.value.id);
        await loadQuestions();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('consult.closeFailed')));
      }
    };

    const searchUserOptions = async (keyword) => {
      if (!keyword) return;
      searchingUsers.value = true;
      try {
        const data = await searchUsers(keyword);
        userOptions.value = data.results || data || [];
      } catch (error) {
        console.warn('搜索用户失败:', error);
      } finally {
        searchingUsers.value = false;
      }
    };

    const doGrant = async () => {
      granting.value = true;
      try {
        await grantExpert(grantUserId.value, {
          title: grantTitle.value.trim(),
          specialties: grantSpecialties.value.trim(),
        });
        ElMessage.success(t('consult.grantedOk'));
        grantUserId.value = null;
        grantTitle.value = '';
        grantSpecialties.value = '';
        await loadExperts();
      } catch (error) {
        ElMessage.error(formatApiError(error, t('consult.grantFailed')));
      } finally {
        granting.value = false;
      }
    };

    /**
     * 取消专家身份（第 76 批）
     *
     * 后端是软删除（ExpertProfile.is_active = False），所以取消后：
     *   · 该用户不再出现在这份专家列表里；
     *   · 也不能再回答咨询问题（权限判断直接查库，不读缓存对象）。
     * 已发表的历史回答会保留，只是不再能新增回答。
     */
    const doRevoke = async (item) => {
      const name = item.user?.username || '';
      try {
        await ElMessageBox.confirm(
          t('consult.revokeConfirm', { name }),
          t('consult.revokeExpert'),
          { type: 'warning', confirmButtonText: t('consult.revokeExpert'), cancelButtonText: t('msg.cancel') },
        );
      } catch {
        return; // 用户点了取消
      }
      revokingId.value = item.user.id;
      try {
        await revokeExpert(item.user.id);
        ElMessage.success(t('consult.revokedOk'));
        await loadExperts();
        // 若详情弹窗里正显示这位专家的回答，刷新一下让"专家"身份标记同步失效
        const shown = detail.value?.answers?.some((answer) => answer.author?.id === item.user.id);
        if (detailDialog.value && shown) {
          detail.value = await fetchQuestion(detail.value.id);
        }
      } catch (error) {
        ElMessage.error(formatApiError(error, t('consult.revokeFailed')));
      } finally {
        revokingId.value = null;
      }
    };

    onMounted(loadAll);

    return {
      t,
      loading, questions, statusCounts, activeTab, experts, tabs,
      askDialog, asking, askForm,
      detailDialog, detailLoading, detail, answerDraft, answering,
      grantUserId, grantTitle, grantSpecialties, granting, searchingUsers, userOptions, revokingId,
      isAdmin, canAnswer, formatTime,
      // 第 78 批：作物名 / 状态标签要暴露给模板（Options API 不 return 就是 undefined）
      localizedField, statusLabel,
      loadAll, loadQuestions, switchTab, submitQuestion, openDetail, submitAnswer,
      doAccept, doClose, searchUserOptions, doGrant, doRevoke,
    };
  },
};
</script>

<style scoped>
.consult-page {
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 24px 20px 40px;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.filter-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 15px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: #fff;
  color: var(--ink-600);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
}

.filter-tab.is-active {
  background: var(--gradient-brand);
  border-color: transparent;
  color: #fff;
}

.tab-count {
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.08);
  font-size: 11.5px;
}

.filter-tab.is-active .tab-count {
  background: rgba(255, 255, 255, 0.25);
}

.consult-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 16px;
  align-items: start;
}

.question-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.question-item {
  padding: 13px 15px;
  border: 1px solid var(--brand-100);
  border-radius: var(--radius);
  background: linear-gradient(160deg, #ffffff, #f8fcfa);
  cursor: pointer;
  transition: all 0.18s ease;
}

.question-item:hover {
  border-color: var(--brand-300);
  transform: translateX(3px);
  box-shadow: var(--shadow-sm);
}

.question-item.is-closed {
  opacity: 0.72;
}

.question-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.crop-tag {
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--brand-100);
  color: var(--brand-800, #1a5238);
  font-size: 11.5px;
  font-weight: 700;
}

.status-chip {
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 700;
  background: var(--ink-50);
  color: var(--ink-600);
}

.status-chip.is-open { background: #fdf3e3; color: #8a5a12; }
.status-chip.is-answered { background: #e7f6ee; color: #1f6343; }
.status-chip.is-closed { background: #eef2f7; color: #48596b; }

.question-title {
  font-size: 14.5px;
  color: var(--ink-900);
}

.question-excerpt {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--ink-600);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.question-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12.3px;
  color: var(--ink-400);
}

.question-meta i {
  margin-right: 4px;
}

.accepted-flag {
  color: #1f6343;
  font-weight: 700;
}

/* 侧栏专家 */
.expert-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.expert-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 10px;
  background: var(--ink-50);
}

.expert-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

/* 第 76 批：专家行的「取消」按钮（默认淡，悬停变明显，避免侧栏太吵） */
.expert-revoke {
  flex: none;
  margin-left: auto;
  font-size: 12px;
}

.expert-name {
  font-size: 13.3px;
  font-weight: 700;
  color: var(--ink-800);
}

.expert-name em {
  margin-left: 5px;
  font-style: normal;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--brand-700);
}

.expert-meta {
  font-size: 11.8px;
  color: var(--ink-500);
}

.grant-box {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.grant-title {
  margin: 0;
  font-size: 12.8px;
  font-weight: 700;
  color: var(--ink-700);
}

.grant-title i {
  margin-right: 5px;
  color: var(--brand-600);
}

.full-width {
  width: 100%;
}

/* 详情 */
.detail-content {
  margin: 0 0 12px;
  font-size: 13.8px;
  line-height: 1.85;
  color: var(--ink-800);
  white-space: pre-wrap;
}

.detail-status {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.detail-meta {
  font-size: 12.3px;
  color: var(--ink-400);
}

.answer-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 9px;
  font-size: 13.8px;
  font-weight: 800;
  color: var(--ink-800);
}

.compose-role {
  font-size: 11.8px;
  font-weight: 600;
  color: var(--ink-400);
}

.answer-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.answer-item {
  padding: 11px 13px;
  border: 1px solid var(--brand-100);
  border-left: 3px solid var(--brand-300);
  border-radius: var(--radius);
  background: #fff;
}

.answer-item.is-accepted {
  border-left-color: #1f8a5c;
  background: linear-gradient(160deg, #f3fbf7, #ffffff);
}

.answer-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 6px;
  font-size: 12.5px;
}

.answer-author {
  font-weight: 700;
  color: var(--ink-800);
}

.answer-author em {
  margin-left: 5px;
  font-style: normal;
  font-size: 11.5px;
  color: var(--brand-700);
}

.answer-time {
  color: var(--ink-400);
}

.answer-content {
  margin: 0;
  font-size: 13.3px;
  line-height: 1.8;
  color: var(--ink-700);
  white-space: pre-wrap;
}

.answer-actions {
  margin-top: 9px;
}

.answer-compose {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px dashed var(--border);
}

.compose-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
}

.compose-hint,
.compose-tip {
  font-size: 12.3px;
  color: var(--ink-500);
}

.compose-tip i {
  margin-right: 4px;
  color: var(--brand-500);
}

@media (max-width: 900px) {
  .consult-main {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>

