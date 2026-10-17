<script setup>
/**
 * 「内容管理」— 帖子页签（第 183 批）
 * ============================================================================
 * 这一支是**原样搬过来的两页**，合成一个页签：
 *   ① 审核队列 = 原 `/admin/review`「内容审核」页的**帖子部分**（第 38/96/100/128 批）；
 *   ② 帖子管理 = 原 `/admin/forum`「论坛管理」页（第 147/166/181/182 批）。
 * 业务逻辑一行未改：接口、分页、批量、权限判定、提示文案全部照旧，
 * 只是把两页的 `<h1>` 页头换成了页内的区块标题（h2），页面标题由 Hub 提供。
 *
 * ⚠️ 为什么两半都放在这一个页签里（而不是只留审核队列）：
 *   「论坛管理」是**唯一**能按版块/状态/关键字找帖子、置顶加精、下架的地方（第 147/182 批），
 *   合并时把它丢掉等于砍功能。两页本来就都是"帖子"，合成一个页签最自然。
 *
 * ⚠️ 变量名带 `forum` 前缀的那一组来自原「论坛管理」页 —— 两页有同名变量
 *   （loading / acting / bulkActing / selectedIds / rejectReason…），
 *   同一个组件里必须区分开，否则后者会静默覆盖前者。
 *
 * ## 权限（与后端同口径，前端只是"不画"）
 *   · 帖子可见/可审（通过·驳回·批量·置顶·加精）：`review` **或** `forum` 模块
 *     —— 后端 `is_moderator()`（views_forum）；审核队列还额外认 Moderators 组；
 *   · 帖子删除 / 批量删除：**仅全权管理员**（`CanDeletePost`，第 181 批）；
 *   · **敏感词词库**：BROADCAST 能力（第 128 批起仍归"对全体发声"）。
 *     它原本就长在内容审核页的右栏，本批**原样留在帖子页签**里 ——
 *     有 BROADCAST 的一定是全权管理员，而全权管理员必然能进这一页，所以没人因此失去入口。
 *   · **举报处理**已挪到「举报」页签（仅全权管理员），本组件不再请求它。
 */
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { formatTime } from '@/utils/date';
import {
  approvePost,
  bulkReviewPosts,  // 第 100 批：批量审核
  createSensitiveWord,
  deleteSensitiveWord,
  fetchPostsByStatus,
  fetchSensitiveWords,
  fetchSiteConfig,
  rejectPost,
} from '@/api/content';
// 论坛管理那一半（原 AdminForumView.vue，第 147 批）
import {
  bulkDeletePosts, getForumBoards, getPosts, setPostEssence, setPostPinned,
} from '@/api/forum';
import { formatApiError } from '@/api/http';
import { useI18n } from '@/i18n';  // 第 65 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 85 批：帖子预览用英文译文
import { sanitizeRichText } from '@/utils/richText';  // 第 91 批：预览正文净化（存储型 XSS）
import { useAuthStore } from '@/stores/auth';  // 第 128 批：右栏按能力显示
import { useQueryState } from '@/composables/useQueryState';  // 第 98 批：筛选进 URL

defineOptions({ name: 'ContentPostPanel' });

const { t } = useI18n();
const { localizedField } = useLocalized();
const router = useRouter();
const authStore = useAuthStore();

// ---------------------------------------------------------------------------
// 第 128 批：敏感词那一块只给全权管理员（BROADCAST = 全站内容策略开关）
// ---------------------------------------------------------------------------
// 内容编辑员（review / forum 模块）只看审核队列与帖子表 —— 这里不显示，也不去请求。
const canManageWords = computed(() => authStore.hasCapability(authStore.CAP_BROADCAST));

// 敏感词分类标签（文案走 i18n，value 保持后端约定的英文标识）
const CATEGORY_KEYS = [
  { value: 'ad', labelKey: 'review.catAd' },
  { value: 'abuse', labelKey: 'review.catAbuse' },
  { value: 'politics', labelKey: 'review.catPolitics' },
  { value: 'other', labelKey: 'review.catOther' },
];

/* 第 74 批：举报原因 → 后端常量是 ad/abuse/politics/irrelevant/other，
   直接展示后端的 reason_display 在英文界面下会显示中文，这里用 i18n 覆盖。
   ⚠️ 第 183 批：举报列表已挪到 ReportPanel.vue，这份映射跟着那块一起搬走了。 */

const categories = computed(() => CATEGORY_KEYS.map((item) => ({ value: item.value, label: t(item.labelKey) })));

// 词条上显示的分类名：后端返回的是中文 category_display，这里用前端映射覆盖，
// 这样切英文时分类名也能跟着变（词条内容本身仍是数据，不翻译）。
const categoryLabel = (value) => categories.value.find((item) => item.value === value)?.label || value;

// ===========================================================================
// ① 审核队列（原 ContentReviewView.vue 的帖子部分）
// ===========================================================================
const loading = ref(false);
const pendingPosts = ref([]);
const pendingTotal = ref(0);
const publishedTotal = ref(0);
const acting = ref(null);

// ======================================================================
// 第 96 批：待审列表真分页
// ----------------------------------------------------------------------
// 改前是 `fetchPostsByStatus('pending', { page_size: 20 })` 一次性取 20 条，
// 而页头显示的是后端返回的**真实总数**（`pendingTotal`）。
// 后果：有 25 条待审时页头写"25 条待审核"，列表里只有 20 条 —— 剩下 5 条
// 既看不到、也没有任何提示、更没有翻页入口。审核员会以为处理完了。
// ======================================================================
const pendingPage = ref(1);
const pendingPageSize = ref(10);

const words = ref([]);
const newWord = ref('');
const newWordEn = ref('');   // 第 135 批：英文对照（只用于显示）
const newWordCategory = ref('ad');
const addingWord = ref(false);

const siteConfig = ref({ post_require_review: false });

const rejectDialog = ref(false);
const rejectReason = ref('');
const rejectingPost = ref(null);
const previewDialog = ref(false);
const previewingPost = ref(null);

const excerptOf = (post) => {
  // 第 85 批：英文界面下待审列表的摘要用 content_en（否则只有摘要栏是中文）
  const text = String(localizedField(post, 'content') || '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return text.length > 100 ? `${text.slice(0, 100)}…` : text || t('review.noContent');
};

const loadPending = async () => {
  const data = await fetchPostsByStatus('pending', {
    page: pendingPage.value,
    page_size: pendingPageSize.value,
  });
  pendingPosts.value = data?.results || [];
  pendingTotal.value = data?.count || 0;
};

/** 第 96 批：待审分页 —— 改每页条数时回到第 1 页（否则可能落在空页上） */
const handlePendingSizeChange = () => {
  pendingPage.value = 1;
  loadPending();
};

const loadPublishedCount = async () => {
  try {
    const data = await fetchPostsByStatus('published', { page_size: 1 });
    publishedTotal.value = data?.count || 0;
  } catch (error) {
    console.warn('统计已发布数量失败:', error);
  }
};

const loadWords = async () => {
  try {
    const data = await fetchSensitiveWords();
    words.value = Array.isArray(data) ? data : data?.results || [];
  } catch (error) {
    console.warn('加载敏感词失败:', error);
    words.value = [];
  }
};

// ======================================================================
// 第 100 批：批量审核
// ======================================================================
const selectedIds = ref([]);
const bulkActing = ref(false);
const bulkRejectVisible = ref(false);
const bulkRejectReason = ref('');

const toggleSelect = (id, checked) => {
  if (checked) {
    if (!selectedIds.value.includes(id)) selectedIds.value = [...selectedIds.value, id];
  } else {
    selectedIds.value = selectedIds.value.filter((item) => item !== id);
  }
};

const allPageSelected = computed(() =>
  pendingPosts.value.length > 0
  && pendingPosts.value.every((post) => selectedIds.value.includes(post.id)),
);
const somePageSelected = computed(() =>
  !allPageSelected.value
  && pendingPosts.value.some((post) => selectedIds.value.includes(post.id)),
);

const toggleSelectAllPage = (checked) => {
  const pageIds = pendingPosts.value.map((post) => post.id);
  if (checked) {
    selectedIds.value = [...new Set([...selectedIds.value, ...pageIds])];
  } else {
    selectedIds.value = selectedIds.value.filter((id) => !pageIds.includes(id));
  }
};

/**
 * 批量审核结果的统一提示
 *
 * ⚠️ 必须**如实报告被跳过的那几条**：批量接口逐条执行、不整体失败，
 * 如果只弹一句"完成"，管理员会以为全都通过了 —— 而实际上"已发布的帖子"
 * 这类会被跳过。所以有失败时把原因列出来。
 */
const reportBulkResult = (result, successKey) => {
  const succeeded = result?.succeeded ?? 0;
  const failed = result?.failed ?? 0;
  if (failed > 0) {
    const reasons = (result?.results || [])
      .filter((item) => !item.ok)
      .map((item) => `#${item.id}：${item.detail}`)
      .join('；');
    ElMessage.warning(t('review.bulkPartial', { ok: succeeded, failed }) + reasons);
  } else {
    ElMessage.success(t(successKey, { count: succeeded }));
  }
};

/* 审核队列的选中态由上面的 el-checkbox + selectedIds 驱动，清空只清数组即可
   （坑在「帖子管理」那一半的 el-table 上，见那里的 clearSelection） */
const clearSelected = () => {
  selectedIds.value = [];
};

const bulkApprove = async () => {
  if (!selectedIds.value.length) return;
  bulkActing.value = true;
  try {
    const result = await bulkReviewPosts(selectedIds.value, 'approve');
    reportBulkResult(result, 'review.bulkApproveOk');
    clearSelected();
    // 本页可能被清空 → 回到第 1 页（否则停在空白页）
    pendingPage.value = 1;
    await Promise.all([loadPending(), loadPublishedCount()]);
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || t('msg.operationFailed'));
  } finally {
    bulkActing.value = false;
  }
};

const bulkReject = async () => {
  if (!selectedIds.value.length) return;
  bulkActing.value = true;
  try {
    const result = await bulkReviewPosts(
      selectedIds.value, 'reject', bulkRejectReason.value.trim(),
    );
    reportBulkResult(result, 'review.bulkRejectOk');
    bulkRejectVisible.value = false;
    bulkRejectReason.value = '';
    clearSelected();
    pendingPage.value = 1;
    await loadPending();
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || t('msg.operationFailed'));
  } finally {
    bulkActing.value = false;
  }
};

const loadAll = async () => {
  loading.value = true;
  try {
    // 第 128 批：敏感词只给全权管理员 —— 编辑员不该去请求它
    // （既不显示、也省掉一个必然没用的请求）。
    // 第 183 批：举报列表已挪去「举报」页签，这里不再请求（它有自己的 onMounted）。
    const sideTasks = [];
    if (canManageWords.value) sideTasks.push(loadWords());
    const [config] = await Promise.all([
      fetchSiteConfig().catch(() => ({ post_require_review: false })),
      loadPending(),
      loadPublishedCount(),
      ...sideTasks,
    ]);
    siteConfig.value = config || { post_require_review: false };
  } catch (error) {
    console.error('加载审核数据失败:', error);
    ElMessage.error(t('msg.loadFailed'));
  } finally {
    loading.value = false;
  }
};

const approve = async (post) => {
  acting.value = post.id;
  try {
    await approvePost(post.id);
    ElMessage.success(t('review.approvedOk'));
    // 第 96 批：批掉本页最后一条且不在第 1 页时退回上一页（避免停在空页）
    if (pendingPosts.value.length === 1 && pendingPage.value > 1) {
      pendingPage.value -= 1;
    }
    await Promise.all([loadPending(), loadPublishedCount()]);
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || t('msg.operationFailed'));
  } finally {
    acting.value = null;
  }
};

const openReject = (post) => {
  rejectingPost.value = post;
  rejectReason.value = '';
  rejectDialog.value = true;
};

const confirmReject = async () => {
  if (!rejectingPost.value) return;
  acting.value = rejectingPost.value.id;
  try {
    await rejectPost(rejectingPost.value.id, rejectReason.value.trim());
    ElMessage.success(t('review.rejectedOk'));
    rejectDialog.value = false;
    // 第 96 批：同上，拒绝掉本页最后一条时退回上一页
    if (pendingPosts.value.length === 1 && pendingPage.value > 1) {
      pendingPage.value -= 1;
    }
    await loadPending();
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || t('msg.operationFailed'));
  } finally {
    acting.value = null;
  }
};

const previewPost = (post) => {
  previewingPost.value = post;
  previewDialog.value = true;
};

const addWord = async () => {
  const word = newWord.value.trim();
  if (!word) {
    ElMessage.warning(t('review.wordRequired'));
    return;
  }
  addingWord.value = true;
  try {
    // 第 135 批：顺带提交英文对照（只用于显示，不参与拦截）
    await createSensitiveWord({
      word,
      word_en: newWordEn.value.trim(),
      category: newWordCategory.value,
    });
    ElMessage.success(t('msg.addingWord', { word }));
    newWord.value = '';
    newWordEn.value = '';
    await loadWords();
  } catch (error) {
    const data = error?.response?.data;
    ElMessage.error(data?.word?.[0] || data?.detail || t('review.addWordFailed'));
  } finally {
    addingWord.value = false;
  }
};

const removeWord = async (item) => {
  try {
    await ElMessageBox.confirm(t('review.deleteWordConfirm', { word: item.word }), t('msg.confirmDelete'), {
      confirmButtonText: t('msg.delete'),
      cancelButtonText: t('msg.cancel'),
      type: 'warning',
    });
  } catch {
    return;
  }
  try {
    await deleteSensitiveWord(item.id);
    ElMessage.success(t('msg.deleteOk'));
    await loadWords();
  } catch (error) {
    ElMessage.error(t('msg.deleteFailed'));
  }
};

const goForum = () => router.push({ name: 'forum' });

// ===========================================================================
// ② 帖子管理（原 AdminForumView.vue）
// ---------------------------------------------------------------------------
// 变量一律加 `forum` 前缀：本组件上半部分（审核队列）已有 loading / acting /
// bulkActing / selectedIds / rejectReason 等同名变量，不加前缀会互相覆盖。
// ===========================================================================
const forumItems = ref([]);
const forumTotal = ref(0);
const forumLoading = ref(false);
const forumPage = ref(1);
const forumPageSize = ref(10);
const forumBoards = ref([]);
// 第 166 批：默认就是 'all'（不是空串）—— 公开论坛列表默认不含草稿，
// 而控制台一进来就该看到全部状态（第 147 批的设计），所以默认显式要 all。
const forumFilters = ref({ board: '', status: 'all', mark: '', search: '' });
const forumStats = ref({ total: 0, pending: 0, published: 0, hidden: 0 });

const forumActing = ref('');
const forumBulkActing = ref(false);
const forumBulkDeleting = ref(false);
const forumSelectedIds = ref([]);
const forumSelectedRows = ref([]);

const forumPreviewVisible = ref(false);
const forumPreviewPost_ = ref(null);
const forumRejectVisible = ref(false);
const forumRejecting = ref(false);
const forumRejectReason = ref('');
const forumRejectTarget = ref(null);      // null = 批量驳回
const forumBulkRejectMode = ref(false);

// -- 权限 ---------------------------------------------------------------
/**
 * 能审核 / 置顶 / 加精：与后端 `is_moderator()` 对齐
 *
 * 第 151 批：`forum`（论坛交流）也算 —— 只勾这一个模块的编辑员就是"论坛管理员"，
 * 不给他按钮等于这个模块名不副实（E2E 就是这么发现漏改的：后端放行、页面上一个按钮都没有）。
 * 前端仍判不了 Moderators 组（组信息没下发），那种用户看不到按钮但后端放行 —— 见第 145 批说明。
 */
const forumCanModerate = computed(() => Boolean(
  authStore.hasContentModule?.('review')
  || authStore.hasContentModule?.('forum')
  || authStore.user?.is_staff
  || authStore.user?.is_superuser,
));
/** 能批量删除 / 单条删除：仅全权管理员（第 181 批与后端 CanDeletePost 同口径） */
const forumCanDelete = computed(() => Boolean(authStore.isAdmin));
const forumCanManageBoards = computed(() => Boolean(
  authStore.hasCapability?.(authStore.CAP_BROADCAST) || authStore.user?.is_superuser,
));

// -- 状态标签 -----------------------------------------------------------
const statusLabel = (status) => ({
  pending: t('forumAdmin.statusPending'),
  published: t('forumAdmin.statusPublished'),
  draft: t('forumAdmin.statusDraft'),
  hidden: t('forumAdmin.statusHidden'),
}[status] || status);

const statusTagType = (status) => ({
  pending: 'warning',
  published: 'success',
  draft: 'info',
  hidden: 'danger',
}[status] || 'info');

// -- 数据 ---------------------------------------------------------------
const buildParams = () => {
  const params = { page: forumPage.value, page_size: forumPageSize.value };
  if (forumFilters.value.board) params.board = forumFilters.value.board;
  //: ⚠️ 第 219 批：`deleted` 是**前端自己的**筛选项，不是后端的状态值 ——
  //: 后端认的是 `only_deleted=true`（且只对管理员/版主生效，其他人传了也拿不到）。
  //: 这里**不能**再把 `status=deleted` 发过去：那不是合法的 status，
  //: 会让后端按状态过滤 → 一条都查不到（看着像"没有已删除帖子"，实际是参数传错）。
  if (forumFilters.value.status === 'deleted') {
    params.only_deleted = 'true';
  } else if (forumFilters.value.status) {
    params.status = forumFilters.value.status;
  }
  if (forumFilters.value.mark === 'pinned') params.ordering = 'pinned';
  if (forumFilters.value.mark === 'essence') params.is_essence = 'true';
  if (forumFilters.value.search.trim()) params.search = forumFilters.value.search.trim();
  return params;
};

const loadList = async () => {
  forumLoading.value = true;
  try {
    const data = await getPosts(buildParams());
    forumItems.value = data.results || data || [];
    forumTotal.value = data.count ?? forumItems.value.length;
  } catch (error) {
    ElMessage.error(formatApiError(error, t('forumAdmin.loadFailed')));
  } finally {
    forumLoading.value = false;
  }
};

/** 概览：各状态各查一次 count（page_size=1 只为拿 count，与反馈页一致） */
const loadStats = async () => {
  try {
    const [all, pending, published, hidden] = await Promise.all([
      getPosts({ page: 1, page_size: 1 }),
      getPosts({ page: 1, page_size: 1, status: 'pending' }),
      getPosts({ page: 1, page_size: 1, status: 'published' }),
      getPosts({ page: 1, page_size: 1, status: 'hidden' }),
    ]);
    forumStats.value = {
      total: all?.count || 0,
      pending: pending?.count || 0,
      published: published?.count || 0,
      hidden: hidden?.count || 0,
    };
  } catch (error) {
    console.warn('论坛统计加载失败:', error);
  }
};

const loadBoards = async () => {
  try {
    const data = await getForumBoards();
    forumBoards.value = Array.isArray(data) ? data : (data?.results || []);
  } catch (error) {
    console.warn('版块列表加载失败:', error);
  }
};

const forumReload = () => Promise.all([loadList(), loadStats()]);

const applyFilter = () => { forumPage.value = 1; loadList(); };
const handleSizeChange = () => { forumPage.value = 1; loadList(); };
const forumHasFilter = computed(() => Boolean(
  forumFilters.value.board || forumFilters.value.status
  || forumFilters.value.mark || forumFilters.value.search.trim(),
));
const resetFilters = () => {
  // 第 166 批：重置回 'all'（= 不过滤状态，含草稿）而不是空串 ——
  // 空串会让控制台落到"默认排除草稿"的公开列表口径上，与「全部状态」的语义不符。
  forumFilters.value = { board: '', status: 'all', mark: '', search: '' };
  applyFilter();
};

// 第 98 批的约定：筛选与分页进 URL（刷新/分享不丢）
const { isReady: queryReady } = useQueryState({
  fields: {
    page: { ref: forumPage, type: 'int', default: 1 },
    page_size: { ref: forumPageSize, type: 'int', default: 10 },
    board: { ref: { get value() { return forumFilters.value.board; },
                   set value(v) { forumFilters.value.board = v ?? ''; } }, type: 'string', default: '' },
    status: { ref: { get value() { return forumFilters.value.status; },
                    // 第 166 批：URL 里没有 status 时，恢复成 'all'（= 不做状态过滤）而不是空串。
                    // 空串在公开列表口径里意味着"默认排除草稿"，而控制台的「全部」
                    // 是要看全部状态（第 147 批的设计，有测试盯着）。
                    set value(v) { forumFilters.value.status = v ?? 'all'; } }, type: 'string', default: 'all' },
    mark: { ref: { get value() { return forumFilters.value.mark; },
                  set value(v) { forumFilters.value.mark = v ?? ''; } }, type: 'string', default: '' },
    search: { ref: { get value() { return forumFilters.value.search; },
                    set value(v) { forumFilters.value.search = v ?? ''; } }, type: 'string', default: '' },
  },
  onExternalChange: () => forumReload(),
});

// -- 选择 ---------------------------------------------------------------
/**
 * 帖子表格的实例 —— 只为一件事：清空选中时把 **el-table 的内部选中态一起清掉**。
 *
 * ⚠️ 这个坑很难查，值得写清楚（用户报的就是"点批量通过没反应，F12 里一个请求都没有"）：
 *
 *   el-table 的选中态有**两份**：
 *     ① 它内部的 `selection` 数组（勾选框的"视觉"状态由它驱动）；
 *     ② 本组件拿到的 `forumSelectedIds`（`selection-change` 同步过来的，按钮的
 *        `:disabled` 看的是它）。
 *
 *   下面原来只写 `forumSelectedIds.value = []` —— **只清了 ②，没清 ①**。
 *   而 el-table 判"某行是否已选中"按 `row-key`（id）比对，列表重新加载后
 *   同 id 的新行对象照样命中 ① 里的旧对象 → 再点行/表头复选框时
 *   `toggleRowStatus` 认为"已经在里面了"，**不加入、也不派发 selection-change**：
 *   · 复选框看着勾上了（① 仍是选中），
 *   · 批量条却一直停在"勾选左侧复选框可批量处理"，
 *   · 「批量通过」永远 `disabled` —— 点它浏览器**根本不会触发 click**，
 *     所以 Network 里连一条请求都没有（这就是"没反应"的真相）。
 *
 *   最典型的复现路径：**批量驳回（帖子变已隐藏）→ 列表重载 → 再全选想批量通过（恢复）**，
 *   第二次勾选全部失效；其它"批量操作后再勾选"的路径同样中招。
 *
 *   修法：调用 el-table 自己的 `clearSelection()`。它除了清内部数组，还会复位
 *   `isAllSelected`、并派发一次空的 `selection-change`（onSelectionChange 收到后
 *   ② 也归零），两份状态就重新对齐了。
 */
const forumTableRef = ref(null);

const onSelectionChange = (rows) => {
  forumSelectedRows.value = rows;
  forumSelectedIds.value = rows.map((row) => row.id);
};
const clearSelection = () => {
  forumSelectedIds.value = [];
  forumSelectedRows.value = [];
  // ⚠️ 必须连 el-table 的内部选中态一起清，否则勾选会"失灵"（见上面 forumTableRef 的说明）
  forumTableRef.value?.clearSelection?.();
};

// -- 行内动作 -----------------------------------------------------------
const forumApprove = async (row) => {
  forumActing.value = row.id;
  try {
    await approvePost(row.id);
    row.status = 'published';   // 就地更新，先给个即时反馈
    ElMessage.success(t('review.approvedOk'));
    // ⚠️ 必须重新拉列表：在"按状态筛选"的视图里（比如只看待审核），
    //    刚刚通过的帖子已经不属于这个筛选结果了 —— 不刷新它会赖在列表里，
    //    管理员以为没生效、再点一次（第二版才发现的问题）。
    await forumReload();
  } catch (error) {
    ElMessage.error(formatApiError(error, t('forumAdmin.approveFailed')));
  } finally {
    forumActing.value = '';
  }
};

const forumOpenReject = (row) => {
  forumRejectTarget.value = row;
  forumBulkRejectMode.value = false;
  forumRejectReason.value = '';
  forumRejectVisible.value = true;
};

const openBulkReject = () => {
  forumRejectTarget.value = null;
  forumBulkRejectMode.value = true;
  forumRejectReason.value = '';
  forumRejectVisible.value = true;
};

const forumConfirmReject = async () => {
  const reason = forumRejectReason.value.trim();
  if (!reason) {
    ElMessage.warning(t('forumAdmin.rejectReasonRequired'));
    return;
  }
  forumRejecting.value = true;
  try {
    if (forumBulkRejectMode.value) {
      const data = await bulkReviewPosts(forumSelectedIds.value, 'reject', reason);
      reportBulk(data, 'review.bulkRejectOk', 'review.bulkPartial');
      clearSelection();
    } else {
      await rejectPost(forumRejectTarget.value.id, reason);
      forumRejectTarget.value.status = 'hidden';
      ElMessage.success(t('review.rejectedOk'));
    }
    forumRejectVisible.value = false;
    await forumReload();
  } catch (error) {
    ElMessage.error(formatApiError(error, t('forumAdmin.rejectFailed')));
  } finally {
    forumRejecting.value = false;
  }
};

const bulkAct = async (action) => {
  if (action === 'reject') {
    openBulkReject();
    return;
  }
  forumBulkActing.value = true;
  try {
    const data = await bulkReviewPosts(forumSelectedIds.value, 'approve');
    reportBulk(data, 'review.bulkApproveOk', 'review.bulkPartial');
    clearSelection();
    await forumReload();
  } catch (error) {
    ElMessage.error(formatApiError(error, t('forumAdmin.bulkApproveFailed')));
  } finally {
    forumBulkActing.value = false;
  }
};

/** 逐条成败的结果提示（批量接口不整体失败） */
const reportBulk = (data, okKey, partialKey) => {
  if (!data || data.failed === 0) {
    ElMessage.success(t(okKey, { count: data?.succeeded ?? 0 }));
    return;
  }
  ElMessage.warning(t(partialKey, { ok: data.succeeded, failed: data.failed }));
};

const togglePin = async (row) => {
  forumActing.value = `pin-${row.id}`;
  try {
    const data = await setPostPinned(row.id, !row.is_pinned);
    row.is_pinned = data?.is_pinned ?? !row.is_pinned;
    ElMessage.success(row.is_pinned ? t('forum.pinOk') : t('forum.unpinOk'));
  } catch (error) {
    ElMessage.error(formatApiError(error, t('forum.pinFailed')));
  } finally {
    forumActing.value = '';
  }
};

const toggleEssence = async (row) => {
  forumActing.value = `essence-${row.id}`;
  try {
    const data = await setPostEssence(row.id, !row.is_essence);
    row.is_essence = data?.is_essence ?? !row.is_essence;
    ElMessage.success(row.is_essence ? t('forum.essenceOk') : t('forum.unessenceOk'));
  } catch (error) {
    ElMessage.error(formatApiError(error, t('forum.essenceFailed')));
  } finally {
    forumActing.value = '';
  }
};

const removeOne = async (row) => {
  try {
    await ElMessageBox.confirm(
      t('forumAdmin.deleteConfirm', { title: localizedField(row, 'title') }),
      t('forumAdmin.deleteAction'),
      { type: 'warning', confirmButtonText: t('forumAdmin.deleteAction'),
        cancelButtonText: t('common.cancel') },
    );
  } catch {
    return;
  }
  try {
    await bulkDeletePosts([row.id]);
    ElMessage.success(t('forumAdmin.deleteOk'));
    await forumReload();
  } catch (error) {
    ElMessage.error(formatApiError(error, t('forumAdmin.deleteFailed')));
  }
};

const bulkRemove = async () => {
  const count = forumSelectedIds.value.length;
  try {
    await ElMessageBox.confirm(
      t('forumAdmin.bulkDeleteConfirm', { count }),
      t('forumAdmin.bulkDelete'),
      { type: 'warning', confirmButtonText: t('forumAdmin.bulkDelete'),
        cancelButtonText: t('common.cancel') },
    );
  } catch {
    return;
  }
  forumBulkDeleting.value = true;
  try {
    const data = await bulkDeletePosts(forumSelectedIds.value);
    reportBulk(data, 'forumAdmin.bulkDeleteOk', 'forumAdmin.bulkDeletePartial');
    clearSelection();
    await forumReload();
  } catch (error) {
    ElMessage.error(formatApiError(error, t('forumAdmin.bulkDeleteFailed')));
  } finally {
    forumBulkDeleting.value = false;
  }
};

// -- 预览 / 跳转 ---------------------------------------------------------
const forumPreview = (row) => {
  forumPreviewPost_.value = row;
  forumPreviewVisible.value = true;
};
const openInSite = () => {
  const id = forumPreviewPost_.value?.id;
  if (!id) return;
  window.open(router.resolve({ name: 'post-detail', params: { id } }).href, '_blank');
};
const goBoards = () => router.push('/admin/boards');

onMounted(() => {
  loadBoards();
});
// 第 98 批的约定：**等 URL 参数应用完**再查，避免"带参数打开链接"时先按默认值查一次
// （上面那版我误写成 `router.afterEach` —— 那是给全局导航挂钩子，跟这里没关系）
watch(queryReady, (ready) => {
  if (ready) forumReload();
}, { immediate: true });

// 审核队列：原页面的 onMounted(loadAll)
onMounted(loadAll);
</script>

<template>
  <div class="content-post-panel">
    <!-- ==================================================================
         ① 审核队列（原「内容审核」页的帖子部分）
         ================================================================== -->
    <section class="hub-block">
      <header class="hub-block-head">
        <span class="hub-block-icon"><i class="fas fa-clipboard-check"></i></span>
        <div class="hub-block-text">
          <h2>{{ t('review.title') }}</h2>
          <p>{{ t('review.subtitle') }}</p>
        </div>
        <div class="hub-block-actions">
          <el-button plain :loading="loading" @click="loadAll">
            <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
          </el-button>
          <!-- 「去论坛」是去**审核对象**所在的页面，不等于返回，保留（第 117 批的说明） -->
          <el-button plain @click="goForum">
            <i class="fas fa-comments"></i> {{ t('review.goForum') }}
          </el-button>
        </div>
      </header>

      <!-- 审核策略提示 -->
      <div class="policy-bar" :class="{ 'is-on': siteConfig.post_require_review }">
        <i :class="siteConfig.post_require_review ? 'fas fa-shield-halved' : 'fas fa-circle-info'"></i>
        <span v-if="siteConfig.post_require_review">
          {{ t('review.policyPrefix') }}<strong>{{ t('review.policyOn') }}</strong>{{ t('review.policyOnTail') }}
        </span>
        <span v-else>
          {{ t('review.policyPrefix') }}<strong>{{ t('review.policyOff') }}</strong>{{ t('review.policyOffTail') }} <code>POST_REQUIRE_REVIEW</code> {{ t('review.policyOffSetTo') }} <code>true</code>.
        </span>
      </div>

      <!-- 统计 -->
      <div class="admin-stats">
        <div class="stat-tile stat-tile--pending">
          <span class="stat-tile-icon"><i class="fas fa-hourglass-half"></i></span>
          <div>
            <div class="stat-tile-value">{{ pendingTotal }}</div>
            <div class="stat-tile-label">{{ t('review.statPendingPosts') }}</div>
          </div>
        </div>
        <div class="stat-tile stat-tile--ok">
          <span class="stat-tile-icon"><i class="fas fa-check"></i></span>
          <div>
            <div class="stat-tile-value">{{ publishedTotal }}</div>
            <div class="stat-tile-label">{{ t('review.statPublished') }}</div>
          </div>
        </div>
        <!-- ⚠️ 第 215 批：这张卡**必须和侧栏（:922）、加载（:267）用同一个守卫**。
             用户反馈"信息编辑员进内容管理，敏感词条看不到"——
             根因就是这里漏了 `v-if`：编辑员没有 BROADCAST，请求 `/api/sensitive-words/`
             会被 403，而卡片照旧渲染，显示成一个**永远为 0 的"敏感词条"**。
             那不是"数量是 0"，是"根本没权限取" —— 看起来却像"词库是空的"。
             （与第 207/208 批修的"来源虚报"是同一类毛病：**把失败装扮成合法的空值**。） -->
        <div v-if="canManageWords" class="stat-tile">
          <span class="stat-tile-icon"><i class="fas fa-filter"></i></span>
          <div>
            <div class="stat-tile-value">{{ words.length }}</div>
            <div class="stat-tile-label">{{ t('review.statWords') }}</div>
          </div>
        </div>
      </div>

      <div class="review-layout">
        <!-- 待审核列表 -->
        <section class="panel-card">
          <div class="panel-head">
            <span class="panel-icon"><i class="fas fa-list-check"></i></span>
            <h2 class="panel-title">{{ t('review.pendingTitle') }}</h2>
            <span class="panel-count">{{ t('review.totalCount', { count: pendingTotal }) }}</span>
            <!--
              第 100 批：批量审核
              ------------------------------------------------------------------
              为什么需要：待审多起来后只能一条一条点"通过"，每条一次点击 + 一次网络往返；
              更麻烦的是**漏审** —— 列表一分页就很容易看漏中间某条。
              这里给"全选本页 + 批量通过/驳回"。
            -->
            <div class="panel-head-right">
              <template v-if="selectedIds.length">
                <span class="selection-hint">{{ t('review.selectedCount', { count: selectedIds.length }) }}</span>
                <el-button size="small" type="primary" :loading="bulkActing" @click="bulkApprove">
                  <i class="fas fa-check-double"></i> {{ t('review.bulkApprove') }}
                </el-button>
                <el-button size="small" type="danger" plain :disabled="bulkActing" @click="bulkRejectVisible = true">
                  <i class="fas fa-xmark"></i> {{ t('review.bulkReject') }}
                </el-button>
                <el-button size="small" text @click="selectedIds = []">{{ t('review.clearSelection') }}</el-button>
              </template>
            </div>
          </div>

          <div class="panel-body">
            <el-skeleton v-if="loading" :rows="4" animated />

            <el-empty
              v-else-if="pendingPosts.length === 0"
              :description="t('review.emptyPending')"
            />

            <template v-else>
              <div class="bulk-bar">
                <el-checkbox
                  :model-value="allPageSelected"
                  :indeterminate="somePageSelected"
                  @change="toggleSelectAllPage"
                >
                  {{ t('review.selectAllPage') }}
                </el-checkbox>
              </div>

              <ul class="review-list">
                <li v-for="post in pendingPosts" :key="post.id" class="review-item">
                  <el-checkbox
                    class="review-check"
                    :model-value="selectedIds.includes(post.id)"
                    @change="(checked) => toggleSelect(post.id, checked)"
                  />
                  <div class="review-main">
                    <h3 class="review-title">
                      <el-tag size="small" type="warning" effect="dark">{{ t('review.tagPendingReview') }}</el-tag>
                      {{ post.title }}
                    </h3>
                    <p class="review-excerpt">{{ excerptOf(post) }}</p>
                    <div class="review-meta">
                      <span><i class="fas fa-user"></i> {{ post.author?.username || t('review.unknownAuthor') }}</span>
                      <span><i class="fas fa-layer-group"></i> {{ post.board?.name || t('review.unknownBoard') }}</span>
                      <span><i class="fas fa-clock"></i> {{ formatTime(post.created_at) }}</span>
                    </div>
                  </div>

                  <div class="review-actions">
                    <el-button size="small" type="primary" :loading="acting === post.id" @click="approve(post)">
                      <i class="fas fa-check"></i> {{ t('review.approve') }}
                    </el-button>
                    <el-button size="small" type="danger" plain @click="openReject(post)">
                      <i class="fas fa-xmark"></i> {{ t('review.reject') }}
                    </el-button>
                    <el-button size="small" text @click="previewPost(post)">
                      <i class="fas fa-eye"></i> {{ t('review.view') }}
                    </el-button>
                  </div>
                </li>
              </ul>
            </template>

            <!--
              第 96 批：待审列表分页
              ------------------------------------------------------------------
              改前一次性只取 20 条，而页头显示的是**真实总数** —— 有 25 条待审时
              页头写"25 条"，列表里只有 20 条，剩下 5 条没有任何入口能看到。
              审核员会以为"都处理完了"。现在有真分页，页头总数与列表条数一致可核对。
            -->
            <div v-if="pendingTotal > 0" class="pagination-wrap">
              <el-pagination
                v-model:current-page="pendingPage"
                v-model:page-size="pendingPageSize"
                :page-sizes="[10, 20, 50]"
                layout="total, sizes, prev, pager, next"
                :total="pendingTotal"
                background
                @size-change="handlePendingSizeChange"
                @current-change="loadPending"
              />
            </div>
          </div>
        </section>

        <!--
          右栏：敏感词词库（第 128 批起只给全权管理员 / BROADCAST）
          ------------------------------------------------------------------
          第 183 批：举报处理已挪到「举报」页签；敏感词**原样留在帖子页签**里 ——
          它一直长在内容审核页右栏，合并时把它丢掉等于砍功能；
          而有 BROADCAST 的一定是全权管理员，必然能进这一页，所以不会有人因此失去入口。
        -->
        <aside v-if="canManageWords" class="review-side">
          <section class="panel-card">
            <div class="panel-head">
              <span class="panel-icon"><i class="fas fa-filter"></i></span>
              <h3 class="panel-title">{{ t('review.wordsTitle') }}</h3>
              <span class="panel-count">{{ t('review.totalCount', { count: words.length }) }}</span>
            </div>
            <div class="panel-body">
              <div class="word-add">
                <el-input
                  v-model="newWord"
                  size="small"
                  maxlength="50"
                  :placeholder="t('review.wordPlaceholder')"
                  @keyup.enter="addWord"
                />
                <el-select v-model="newWordCategory" size="small" class="word-category">
                  <el-option v-for="item in categories" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
                <el-button size="small" type="primary" :loading="addingWord" @click="addWord">
                  <i class="fas fa-plus"></i>
                </el-button>
              </div>
              <!--
                第 135 批：英文对照（选填、只用于显示）
                ----------------------------------------------------------------
                词条是**被拦截的字面串**，所以中文词库在英文界面下就是一串中文，
                英文管理员看不出每条拦的是什么（用户就是这么反馈的）。
                这里让管理员顺手写一句英文说法，列表里会并排显示。
                ⚠️ 它**不参与拦截** —— 想拦英文垃圾词请直接新增一条英文词条。
              -->
              <div class="word-add word-add--en">
                <el-input
                  v-model="newWordEn"
                  size="small"
                  maxlength="80"
                  :placeholder="t('review.wordEnPlaceholder')"
                  @keyup.enter="addWord"
                />
              </div>
              <p class="field-hint">
                {{ t('review.wordsHint') }}
              </p>
              <p class="field-hint field-hint--muted">
                <i class="fas fa-circle-info"></i> {{ t('review.wordEnHint') }}
              </p>

              <ul v-if="words.length" class="word-list">
                <li v-for="item in words" :key="item.id" class="word-item">
                  <!-- 第 135 批：词条 + 英文对照**竖排**（横排会把"兼职刷单"这种词挤到换行） -->
                  <span class="word-main">
                    <span class="word-text">{{ item.word }}</span>
                    <span v-if="item.word_en" class="word-en">{{ item.word_en }}</span>
                  </span>
                  <span class="word-cat">{{ categoryLabel(item.category) }}</span>
                  <span v-if="!item.is_active" class="word-off">{{ t('review.disabled') }}</span>
                  <button type="button" class="word-del" :title="t('review.delete')" @click="removeWord(item)">
                    <i class="fas fa-trash"></i>
                  </button>
                </li>
              </ul>
              <el-empty v-else :description="t('review.wordsEmpty')" :image-size="60" />
            </div>
          </section>
        </aside>
      </div>
    </section>

    <!-- ==================================================================
         ② 帖子管理（原「论坛管理」页）
         ================================================================== -->
    <section class="hub-block">
      <header class="hub-block-head">
        <span class="hub-block-icon"><i class="fas fa-comments"></i></span>
        <div class="hub-block-text">
          <h2>{{ t('forumAdmin.title') }}</h2>
          <p>{{ t('forumAdmin.subtitle') }}</p>
        </div>
        <div class="hub-block-actions">
          <!-- 版块管理是 BROADCAST 的页面，只有能管版块的人看得到这个跳转 -->
          <el-button v-if="forumCanManageBoards" class="btn-on-brand" @click="goBoards">
            <i class="fas fa-table-columns"></i> {{ t('manage.boards') }}
          </el-button>
          <el-button plain :loading="forumLoading" @click="loadList">
            <i class="fas fa-sync-alt"></i> {{ t('common.refresh') }}
          </el-button>
        </div>
      </header>

      <!-- 概览小卡（各用一次 page_size=1 拿 count，与反馈页同一做法） -->
      <div class="admin-stats">
        <div class="stat-tile">
          <span class="stat-tile-icon"><i class="fas fa-comments"></i></span>
          <div>
            <div class="stat-tile-value">{{ forumStats.total }}</div>
            <div class="stat-tile-label">{{ t('forumAdmin.statTotal') }}</div>
          </div>
        </div>
        <div class="stat-tile stat-tile--pending">
          <span class="stat-tile-icon"><i class="fas fa-hourglass-half"></i></span>
          <div>
            <div class="stat-tile-value">{{ forumStats.pending }}</div>
            <div class="stat-tile-label">{{ t('forumAdmin.statusPending') }}</div>
          </div>
        </div>
        <div class="stat-tile stat-tile--ok">
          <span class="stat-tile-icon"><i class="fas fa-circle-check"></i></span>
          <div>
            <div class="stat-tile-value">{{ forumStats.published }}</div>
            <div class="stat-tile-label">{{ t('forumAdmin.statusPublished') }}</div>
          </div>
        </div>
        <div class="stat-tile stat-tile--processing">
          <span class="stat-tile-icon"><i class="fas fa-eye-slash"></i></span>
          <div>
            <div class="stat-tile-value">{{ forumStats.hidden }}</div>
            <div class="stat-tile-label">{{ t('forumAdmin.statusHidden') }}</div>
          </div>
        </div>
      </div>

      <!-- 筛选 -->
      <div class="filter-bar">
        <el-select v-model="forumFilters.board" :placeholder="t('forumAdmin.boardFilter')" clearable
                   style="width: 170px" @change="applyFilter" @clear="applyFilter">
          <el-option v-for="board in forumBoards" :key="board.id"
                     :label="localizedField(board, 'name')" :value="String(board.id)" />
        </el-select>
        <el-select v-model="forumFilters.status" :placeholder="t('forumAdmin.statusFilter')" clearable
                   style="width: 150px" @change="applyFilter" @clear="applyFilter">
          <!-- 第 166 批：显式传 all —— 公开论坛列表默认不含草稿，控制台「全部」要能看到全部状态 -->
          <el-option :label="t('forumAdmin.statusAll')" value="all" />
          <el-option :label="t('forumAdmin.statusPending')" value="pending" />
          <el-option :label="t('forumAdmin.statusPublished')" value="published" />
          <el-option :label="t('forumAdmin.statusDraft')" value="draft" />
          <el-option :label="t('forumAdmin.statusHidden')" value="hidden" />
          <!-- ⚠️ 第 219 批：**已删除**（审计用）。
               后端第 91 批就支持 `?only_deleted=true`（仅管理员/版主），
               但前端一直没接 —— 于是用户在论坛删掉自己的帖子后，
               管理端**翻不到任何痕迹**（用户就是这样问上来的）。
               选它时走的是 `only_deleted`，不再发 `status`（见 buildParams）。 -->
          <el-option :label="t('forumAdmin.statusDeleted')" value="deleted" />
        </el-select>
        <el-select v-model="forumFilters.mark" :placeholder="t('forumAdmin.markFilter')" clearable
                   style="width: 140px" @change="applyFilter" @clear="applyFilter">
          <el-option :label="t('forumAdmin.markPinned')" value="pinned" />
          <el-option :label="t('forumAdmin.markEssence')" value="essence" />
        </el-select>
        <el-input v-model="forumFilters.search" :placeholder="t('forumAdmin.searchPlaceholder')"
                  clearable style="width: 240px" @clear="applyFilter" @keyup.enter="applyFilter">
          <template #prefix><i class="fas fa-search"></i></template>
          <template #append>
            <el-button @click="applyFilter"><i class="fas fa-search"></i></el-button>
          </template>
        </el-input>
        <el-button plain :disabled="!forumHasFilter" @click="resetFilters">
          <i class="fas fa-rotate-left"></i> {{ t('forumAdmin.resetFilters') }}
        </el-button>
        <span class="total-hint">{{ t('forumAdmin.totalHint', { count: forumTotal }) }}</span>
      </div>

      <!-- 批量操作条：只有能操作帖子的人才看得到 -->
      <!--: ⚠️ 第 219 批：「已删除」视图里**不显示** — 批量通过/驳回/删除对已删除的帖子
           全部会失败（后端按 `Post.active` 取对象 → 404）。留着只会让人以为功能坏了。 -->
      <div v-if="forumCanModerate && forumFilters.status !== 'deleted'" class="bulk-bar">
        <span v-if="forumSelectedIds.length" class="bulk-count">
          {{ t('forumAdmin.selectedCount', { count: forumSelectedIds.length }) }}
        </span>
        <span v-else class="bulk-count muted">{{ t('forumAdmin.selectHint') }}</span>
        <div class="bulk-actions">
          <el-button size="small" type="primary" :disabled="!forumSelectedIds.length || forumBulkActing"
                     @click="bulkAct('approve')">
            <i class="fas fa-check"></i> {{ t('review.bulkApprove') }}
          </el-button>
          <el-button size="small" type="danger" plain :disabled="!forumSelectedIds.length || forumBulkActing"
                     @click="openBulkReject">
            <i class="fas fa-xmark"></i> {{ t('review.bulkReject') }}
          </el-button>
          <!-- 批量删帖是不可逆的破坏性操作：只给全权管理员（后端也是 403） -->
          <el-button v-if="forumCanDelete" size="small" type="danger" :disabled="!forumSelectedIds.length"
                     :loading="forumBulkDeleting" @click="bulkRemove">
            <i class="fas fa-trash"></i> {{ t('forumAdmin.bulkDelete') }}
          </el-button>
          <el-button v-if="forumSelectedIds.length" size="small" text @click="clearSelection">
            {{ t('review.clearSelection') }}
          </el-button>
        </div>
      </div>

      <!-- 列表 -->
      <el-table
        ref="forumTableRef"
        data-testid="forum-table"
        v-loading="forumLoading"
        :data="forumItems"
        row-key="id"
        class="admin-table"
        @selection-change="onSelectionChange"
      >
        <!--: ⚠️ 第 219 批：勾选列同理 —— 「已删除」视图里没有可批量操作的对象，勾了也没用 -->
        <el-table-column v-if="forumCanModerate && forumFilters.status !== 'deleted'"
                         type="selection" width="46" reserve-selection />

        <el-table-column :label="t('forumAdmin.colTitle')" min-width="320">
          <template #default="{ row }">
            <div class="post-title-cell">
              <el-tag v-if="row.is_pinned" size="small" type="danger" effect="dark">{{ t('forum.tagPinned') }}</el-tag>
              <el-tag v-if="row.is_essence" size="small" type="warning" effect="dark">{{ t('forum.tagEssence') }}</el-tag>
              <span class="post-title-text">{{ localizedField(row, 'title') || t('forum.untitled') }}</span>
            </div>
            <div class="post-sub">
              <span><i class="fas fa-user"></i> {{ row.author?.username || t('forum.unknownUser') }}</span>
              <span v-if="row.board"><i class="fas fa-layer-group"></i> {{ localizedField(row.board, 'name') }}</span>
              <!--: ⚠️ 第 219 批：看"已删除"时，**创建时间没有意义，删除时间才有**。
                   软删除会把标题改成 `[已删除]`、正文清空，剩下能读的信息只有
                   "谁发的、哪个版块、什么时候删的"。 -->
              <span v-if="forumFilters.status === 'deleted' && row.deleted_at">
                <i class="fas fa-trash-can"></i> {{ t('forumAdmin.deletedAt', { time: formatTime(row.deleted_at, 'YYYY-MM-DD HH:mm') }) }}
              </span>
              <span v-else><i class="fas fa-clock"></i> {{ formatTime(row.created_at, 'YYYY-MM-DD HH:mm') }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column :label="t('forumAdmin.colStatus')" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)" effect="light">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column :label="t('forumAdmin.colStats')" width="150">
          <template #default="{ row }">
            <span class="muted">
              {{ t('forumAdmin.statCell', { views: row.view_count || 0, comments: row.comment_count || 0 }) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column :label="t('forumAdmin.colActions')" width="330" fixed="right">
          <template #default="{ row }">
            <!--: ⚠️ 第 219 批：已删除的帖子在这个视图里**只能看、不能操作** ——
                 `retrieve` 走 `Post.active`，点「查看」会 404；置顶/加精/驳回对一条已删除的帖子
                 也没有意义。一排点了必然报错的按钮，比没有按钮更糟。 -->
            <span v-if="forumFilters.status === 'deleted'" class="muted">
              {{ t('forumAdmin.deletedNoAction') }}
            </span>
            <template v-else>
              <el-button size="small" text @click="forumPreview(row)">
                {{ t('review.view') }}
              </el-button>
              <!--
                第 188 批：**已隐藏**的帖子也要能在行内恢复发布。
                后端从第 187 批起就让"通过"接受 hidden（`pending`/`hidden` → published），
                但这里原先判的是 `row.status === 'pending'` —— 于是"批量能恢复、单条没入口"，
                管理员点开一条已隐藏的帖子，行内只有「置顶/加精/删除」，没有恢复的办法。
                文案也分开：对待审叫「通过」，对已隐藏叫「恢复发布」，别让人以为
                自己在处理一条待审帖。
              -->
              <el-button v-if="row.status === 'pending' || row.status === 'hidden'"
                         size="small" type="primary" link
                         :loading="forumActing === row.id" @click="forumApprove(row)">
                {{ row.status === 'hidden' ? t('review.restore') : t('review.approve') }}
              </el-button>
              <!-- 驳回只对待审显示：已隐藏的再"驳回"是重复操作（后端也会跳过并说明原因） -->
              <el-button v-if="row.status === 'pending'" size="small" type="danger" link
                         @click="forumOpenReject(row)">
                {{ t('review.reject') }}
              </el-button>
              <!--
                第 182 批：**已发布**的帖子给一个「下架」入口。
                原先界面上没有任何办法撤回已发布的内容：单条驳回只对待审显示、
                批量驳回（后端）只处理 pending —— 用户反馈"点批量驳回没用"就是这个。
                后端第 182 批已允许驳回处理 published（语义=下架，可再次通过恢复），
                这里补上对应入口，走同一个驳回对话框（要填理由，进审核轨迹）。
              -->
              <el-button v-if="row.status === 'published' && forumCanModerate" size="small"
                         type="warning" link @click="forumOpenReject(row)">
                {{ t('review.unpublish') }}
              </el-button>
              <el-button v-if="forumCanModerate" size="small" link
                         :type="row.is_pinned ? 'danger' : 'default'"
                         :loading="forumActing === `pin-${row.id}`" @click="togglePin(row)">
                {{ row.is_pinned ? t('forum.unpinAction') : t('forum.pinAction') }}
              </el-button>
              <el-button v-if="forumCanModerate" size="small" link
                         :type="row.is_essence ? 'warning' : 'default'"
                         :loading="forumActing === `essence-${row.id}`" @click="toggleEssence(row)">
                {{ row.is_essence ? t('forum.unessenceAction') : t('forum.essenceAction') }}
              </el-button>
              <!-- 第 181 批：删帖只给全权管理员（后端 CanDeletePost 的既定口径）—— 原先这个按钮**没有任何 v-if**，编辑员看得到、点了必然 403 -->
              <el-button v-if="forumCanDelete" size="small" type="danger" link title="仅全权管理员可删除帖子；编辑员请用【驳回】或软删评论处置" @click="removeOne(row)">
                {{ t('feedbackAdmin.delete') }}
              </el-button>
            </template>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty :description="t('forumAdmin.empty')" :image-size="80" />
        </template>
      </el-table>

      <el-pagination
        v-model:current-page="forumPage"
        v-model:page-size="forumPageSize"
        :total="forumTotal"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        class="admin-pagination"
        @current-change="loadList"
        @size-change="handleSizeChange"
      />
    </section>

    <!-- 驳回原因（审核队列） -->
    <el-dialog v-model="rejectDialog" width="520px" class="form-dialog" :close-on-click-modal="false">
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon"><i class="fas fa-xmark"></i></span>
          <div>
            <h3>{{ t('review.rejectDialogTitle') }}</h3>
            <p>{{ t('review.rejectDialogHint') }}</p>
          </div>
        </div>
      </template>

      <div class="form-dialog-body">
        <p class="reject-post-title">{{ rejectingPost?.title }}</p>
        <el-input
          v-model="rejectReason"
          type="textarea"
          :rows="4"
          resize="none"
          maxlength="200"
          show-word-limit
          :placeholder="t('review.rejectReasonPlaceholder')"
        />
      </div>

      <template #footer>
        <div class="form-dialog-footer">
          <span class="footer-hint"><i class="fas fa-bell"></i> {{ t('review.authorWillBeNotified') }}</span>
          <span>
            <el-button @click="rejectDialog = false">{{ t('review.cancel') }}</el-button>
            <el-button type="danger" :loading="acting === rejectingPost?.id" @click="confirmReject">
              {{ t('review.confirmReject') }}
            </el-button>
          </span>
        </div>
      </template>
    </el-dialog>

    <!-- 批量驳回（第 100 批）：与单条驳回共用同一个原因输入，逐条通知作者 -->
    <el-dialog v-model="bulkRejectVisible" width="520px" class="form-dialog" :close-on-click-modal="false">
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon"><i class="fas fa-xmark"></i></span>
          <div>
            <h3>{{ t('review.bulkRejectTitle', { count: selectedIds.length }) }}</h3>
            <p>{{ t('review.rejectDialogHint') }}</p>
          </div>
        </div>
      </template>

      <div class="form-dialog-body">
        <el-input
          v-model="bulkRejectReason"
          type="textarea"
          :rows="4"
          resize="none"
          maxlength="200"
          show-word-limit
          :placeholder="t('review.rejectReasonPlaceholder')"
        />
      </div>

      <template #footer>
        <div class="form-dialog-footer">
          <span class="footer-hint"><i class="fas fa-bell"></i> {{ t('review.authorWillBeNotified') }}</span>
          <span>
            <el-button @click="bulkRejectVisible = false">{{ t('review.cancel') }}</el-button>
            <el-button type="danger" :loading="bulkActing" @click="bulkReject">
              {{ t('review.bulkRejectConfirm', { count: selectedIds.length }) }}
            </el-button>
          </span>
        </div>
      </template>
    </el-dialog>

    <!-- 帖子预览（审核队列，第 91 批：净化后再进 v-html） -->
    <el-dialog v-model="previewDialog" width="720px" top="6vh" class="form-dialog">
      <template #header>
        <div class="form-dialog-head">
          <span class="form-dialog-head-icon"><i class="fas fa-eye"></i></span>
          <div>
            <h3>{{ localizedField(previewingPost, 'title') }}</h3>
            <p>{{ previewingPost?.author?.username }} · {{ localizedField(previewingPost?.board, 'name') }}</p>
          </div>
        </div>
      </template>
      <div class="form-dialog-body">
        <!-- 第 91 批（安全）：预览的是**待审帖子正文**（用户写的内容），必须净化后再进 v-html -->
        <div class="post-preview" v-html="sanitizeRichText(localizedField(previewingPost, 'content'))"></div>
      </div>
    </el-dialog>

    <!-- 帖子预览（帖子管理，内容较长，放弹窗里看，避免列表被撑开） -->
    <el-dialog v-model="forumPreviewVisible" :title="forumPreviewPost_?.title || t('forumAdmin.previewTitle')"
               width="720px">
      <div v-if="forumPreviewPost_" class="preview-body">
        <p class="preview-meta">
          <span><i class="fas fa-user"></i> {{ forumPreviewPost_.author?.username || t('forum.unknownUser') }}</span>
          <span><i class="fas fa-layer-group"></i> {{ forumPreviewPost_.board?.name || '' }}</span>
          <span><i class="fas fa-clock"></i> {{ formatTime(forumPreviewPost_.created_at, 'YYYY-MM-DD HH:mm') }}</span>
        </p>
        <!-- ⚠️ 必须净化后再进 v-html —— 与上面"审核队列预览"（:1302）同一条规矩。
             这里是**帖子管理**的预览弹窗，预览的同样是用户写的正文（存储型 XSS 面）。
             第 91 批给审核预览加了 `sanitizeRichText`，却**漏了这一处**：
             两处预览长得一样、代码却不一样，看代码时很容易以为"已经处理过了"。 -->
        <div class="preview-content"
             v-html="sanitizeRichText(localizedField(forumPreviewPost_, 'content')) || t('forumAdmin.noContent')"></div>
      </div>
      <template #footer>
        <el-button @click="forumPreviewVisible = false">{{ t('common.close') }}</el-button>
        <el-button type="primary" @click="openInSite">
          {{ t('forumAdmin.openInSite') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 驳回原因（帖子管理，批量与单条共用同一个弹窗） -->
    <el-dialog v-model="forumRejectVisible" :title="t('review.rejectDialogTitle')" width="460px"
               :close-on-click-modal="false">
      <el-input v-model="forumRejectReason" type="textarea" :rows="3" maxlength="200" show-word-limit
                :placeholder="t('review.rejectReasonPlaceholder')" />
      <p class="field-hint">{{ t('review.rejectDialogHint') }}</p>
      <template #footer>
        <el-button @click="forumRejectVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="danger" :loading="forumRejecting" :disabled="!forumRejectReason.trim()"
                   @click="forumConfirmReject">
          {{ t('review.confirmReject') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ============================================================================
   页签内的区块头（第 183 批）
   ----------------------------------------------------------------------------
   合并前三页各有一个 `.admin-hero`（H1 + 副标题 + 右侧动作）。合并后 H1 归 Hub，
   每个区块保留自己的名字与动作 —— 用 h2，页面里只有一个 h1。
   ============================================================================ */
.hub-block + .hub-block {
  margin-top: 26px;
  padding-top: 22px;
  border-top: 2px dashed var(--border, #e2ebe5);
}

.hub-block-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.hub-block-icon {
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: var(--brand-50, #f1f9f4);
  color: var(--brand-700, #1f6343);
  font-size: 16px;
}

.hub-block-text {
  min-width: 0;
}

.hub-block-text h2 {
  margin: 0 0 3px;
  font-size: 17px;
  font-weight: 800;
  color: var(--ink-900, #1b2b23);
}

.hub-block-text p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--ink-500, #78897f);
}

.hub-block-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* ---------- 审核队列（原 ContentReviewView 的样式） ---------- */
.policy-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 15px;
  padding: 11px 15px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--ink-50);
  font-size: 13px;
  color: var(--ink-600);
}

.policy-bar.is-on {
  border-color: var(--brand-200);
  background: var(--brand-50);
  color: var(--brand-800);
}

.policy-bar code {
  padding: 1px 5px;
  border-radius: 5px;
  background: #fff;
  border: 1px solid var(--border);
  font-size: 12px;
}

.review-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 18px;
  align-items: start;
}

.review-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.review-item {
  display: flex;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid var(--brand-100);
  border-radius: var(--radius);
  background: linear-gradient(160deg, #fffdf7, #ffffff);
}

.review-main {
  flex: 1;
  min-width: 0;
}

.review-title {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 700;
  color: var(--ink-900);
}

.review-excerpt {
  margin: 0 0 8px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-500);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.review-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--ink-400);
}

.review-meta i {
  margin-right: 4px;
}

.review-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
}

.review-actions .el-button + .el-button {
  margin-left: 0;
}

/* 第 135 批：敏感词的英文对照（第二行输入 + 列表里的灰字说明） */
.word-add--en {
  margin-top: 6px;
}

/* 词条与英文对照竖排：占据剩余宽度，长词不换行，对照过长时省略号 */
.word-main {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-width: 0;
}

.word-en {
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--ink-400, #9dada5);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.field-hint--muted {
  margin-top: 4px;
  color: var(--ink-500, #78897f);
  font-size: 11.5px;
}

/* 敏感词 */
.word-add {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.word-category {
  width: 108px;
}

.word-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 320px;
  overflow-y: auto;
}

.word-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--ink-50);
  font-size: 13px;
}

.word-text {
  font-weight: 600;
  color: var(--ink-800);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;   /* 第 135 批：词条本身不换行（换行会把整行撑高、右侧标签错位） */
}

.word-cat {
  padding: 1px 7px;
  border-radius: 999px;
  background: #fff;
  border: 1px solid var(--border);
  font-size: 11px;
  color: var(--ink-500);
}

.word-off {
  font-size: 11px;
  color: #cf4436;
}

.word-del {
  margin-left: auto;
  border: none;
  background: none;
  color: var(--ink-400);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 6px;
}

.word-del:hover {
  background: #fdecea;
  color: #cf4436;
}

.reject-post-title {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 700;
  color: var(--ink-900);
}

.post-preview {
  font-size: 14px;
  line-height: 1.85;
  color: var(--ink-700);
}

.post-preview :deep(img) {
  max-width: 100%;
  border-radius: 10px;
}

@media (max-width: 1080px) {
  .review-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}

/* ============================================================================
   第 96 批：分页条（待审列表在宽面板里右对齐）
   ============================================================================ */
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

/* ============================================================================
   第 100 批：批量审核
   ----------------------------------------------------------------------------
   勾选框放在每条左侧（`review-item` 原本是 flex 行），所以这里改成让勾选框与内容
   并排、操作按钮仍在右侧。全选条压在列表上方，不占额外高度太多。
   ============================================================================ */
.panel-head-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.selection-hint {
  font-size: 13px;
  font-weight: 700;
  color: var(--brand-700, #1f6343);
}

/* 审核队列的批量条（原 ContentReviewView 的样式：全选条压在列表上方） */
.review-layout .bulk-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 2px 10px;
  border-bottom: 1px dashed var(--border, #e2ebe5);
  margin-bottom: 10px;
}

.review-check {
  margin-right: 10px;
  flex: 0 0 auto;
}

/* ---------- 帖子管理（原 AdminForumView 的样式） ---------- */
.post-title-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: var(--ink-800);
}

.post-title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.post-sub {
  margin-top: 4px;
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--ink-400, #9dada5);
}

/* 帖子管理那一半的批量条：是 `.hub-block` 的直接子元素（审核队列那条在 review-layout 里），
   两条样式不同（原两页本来就长得不一样），用子选择器分开，谁也不会覆盖谁。 */
.hub-block > .bulk-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--ink-50);
}

.bulk-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--brand-700, #1c6b4b);
}

.bulk-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.preview-meta {
  display: flex;
  gap: 14px;
  font-size: 12.5px;
  color: var(--ink-400, #9dada5);
  margin: 0 0 10px;
}

.preview-content {
  max-height: 420px;
  overflow-y: auto;
  line-height: 1.7;
}

.admin-pagination {
  margin-top: 14px;
  justify-content: flex-end;
}
</style>
