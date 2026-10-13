<script setup>
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router';
import { useAuthStore } from './stores/auth';
import { computed, onMounted, onBeforeUnmount, nextTick, ref, watch, onUnmounted } from 'vue';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import enUs from 'element-plus/es/locale/lang/en';
import { Setting, ArrowDown, HomeFilled, Document } from '@element-plus/icons-vue';
import NotificationBell from '@/components/NotificationBell.vue';  // 第 37 批：通知铃铛
import MessageEntry from '@/components/MessageEntry.vue';  // 第 42 批：私信入口
import LanguageSwitcher from '@/components/LanguageSwitcher.vue';  // 第 48 批：语言切换
import OfflineIndicator from '@/components/OfflineIndicator.vue';  // 第 50 批：离线状态
import AdminLayout from '@/components/AdminLayout.vue';  // 第 117 批：管理后台外壳（/admin/**）
import { isNavActive as navIsActive } from '@/utils/navActive';  // 第 74 批：导航高亮判定
import { locale, useI18n } from '@/i18n';  // 第 77 批：Element Plus 语言包；第 81 批：导航文案

/**
 * 第 77 批：Element Plus 的语言包
 * ------------------------------------------------------------------
 * 原来这里把 el-config-provider 的 locale 写死成 zhCn —— 于是英文界面下
 * 日期选择器、分页器（"条/页"）、el-empty（"暂无数据"）、el-select 空态、
 * el-message-box 的按钮等**组件自带文案**仍然是中文。现在跟随 app_locale 切换。
 */
const elementLocale = computed(() => (locale.value === 'en' ? enUs : zhCn));



// 注册图标组件
const components = {
  HomeFilled,
  Document,
  Setting,
  ArrowDown
};

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();

/* ============================================================================
 * 第 81 批：顶栏导航重排（中英共用一套布局）
 * ----------------------------------------------------------------------------
 * 之前的问题（实测）：头高 119px（品牌一行 + 导航一行）；≤1500px 时**品牌全称与
 * "管理"文字被隐藏**（1366/1440 这类最常见的笔记本宽度上只剩一个 logo）；
 * 英文标签更长，窄屏比中文更早换行 —— 两种语言的观感不一致。
 *
 * 现在的规则：
 *   · ≥1200px：**单行**（品牌全称 + 导航 + 用户区，头高回到 72px）。
 *     导航放不下的项自动收进「更多 ▾」下拉 —— 按真实测量计算，绝不裁切；
 *     当前所在页面**一定保持在可见位置**（若它在"更多"里，会与最后一个可见项交换）。
 *   · <1200px：导航独占一行并允许换行（全部可见，无"更多"），品牌全称保留。
 *   · <768px：紧凑排布 + 加大点按区域。
 * 文案：顶栏用 `navShort.*`（紧凑），悬停 title 显示 `nav.*` 全称；
 *       页脚等有空间的地方继续用 `nav.*`。中英各一套，保证布局一致。
 * ========================================================================== */
const { t } = useI18n();

//: 导航分组（组间画一条竖线；分组只影响视觉，10 个入口全部保留）
const NAV_GROUPS = [
  [{ to: '/', key: 'home' }],
  [
    { to: '/detect', key: 'detect' },
    { to: '/pests', key: 'pests' },
    { to: '/history', key: 'history' },
  ],
  [
    { to: '/alerts', key: 'alerts' },
    { to: '/calendar', key: 'calendar' },
    { to: '/consult', key: 'consult' },
  ],
  [
    { to: '/news', key: 'news' },
    { to: '/forum', key: 'forum' },
    { to: '/about', key: 'about' },
  ],
];

//: 拍平后带分组序号，便于判断"两个相邻项之间要不要画竖线"
const navItems = computed(() =>
  NAV_GROUPS.flatMap((group, groupIndex) =>
    group.map((item) => ({
      ...item,
      groupIndex,
      label: t(`navShort.${item.key}`),
      // 悬停提示用完整名称（短标签只是省地方，不是改名）
      fullLabel: t(`nav.${item.key}`),
    })),
  ),
);

//: 单行模式下导航项的间距常量（与 CSS 的 .navigation gap / .nav-sep margin 对齐）
const GAP = 4;                 // .navigation 的 gap
const SEP = 17;                // 竖线宽 1 + 左右 margin 8
const USER_SEP = 15;           // 单行模式下用户区左侧的 14px padding + 1px 竖线
/**
 * 安全余量：用户区宽度会随"私信/通知未读红点"等动态内容变化（实测约 ±20px）。
 * 判定时预留一点余量，避免红点出现/消失时顶栏在"单行 ↔ 两行"之间来回跳。
 */
const SAFETY = 28;
/**
 * 单行形态最多允许把几项收进「更多 ▾」；超过这个数就改用两行（10 项全部可见）。
 * 依据：导航总宽中文 577px / 英文 705px，而 1366 下单行只剩 600 出头 ——
 * "单行 + 把 4~5 个入口塞进更多"并不比"两行全显示"好用。
 * 若希望**任何宽度都保持单行**（放不下的一律进「更多」），把这里改成 10 即可。
 */
const MAX_HIDDEN_INLINE = 2;

//: 可见项的下标（默认全可见；单行模式下按可用宽度收窄）
const visibleIdx = ref(navItems.value.map((_, index) => index));
const navRef = ref(null);        // 可见导航容器
const measureRef = ref(null);    // 隐藏测量行（含全部导航项，用于取真实宽度）
const isCompactHeader = ref(false);  // 是否 <1200px（导航独占一行、不做收纳）
/**
 * 顶栏形态：
 *   'inline'  —— 品牌 + 导航 + 用户区同一行（放不下时最多 1 项进「更多 ▾」）
 *   'wrapped' —— 导航整行下移、允许换行，10 个入口全部可见（窄屏或放不下的语言）
 * 由 recomputeNav 实测决定，CSS 通过 .app-header.is-nav-wrapped 切换。
 */
const navMode = ref('inline');
const isNavWrapped = computed(() => navMode.value === 'wrapped');
/**
 * 用户区是否"收紧"（隐藏用户名 / 管理入口文字）。
 * 只在**单行模式确实放不下**时才收紧 —— 而不是按视口宽度一刀切：
 * 头部的可用宽度是 `min(视口, 1600) − 品牌 − 用户区`，所以 1680 反而比 1920 更宽
 * （1920 时行宽被 max-width 卡在 1600，却又因为"屏幕够大"而展开了用户名）。
 * 这类反直觉的边界，交给实测决定，别写死在媒体查询里。
 */
const isTightUserArea = ref(false);

const visibleItems = computed(() =>
  visibleIdx.value.map((index) => navItems.value[index]).filter(Boolean),
);
const hiddenItems = computed(() =>
  navItems.value.filter((_, index) => !visibleIdx.value.includes(index)),
);
//: 当前页被收进「更多」时，把「更多」按钮也点亮，避免"当前页找不到"
const activeHidden = computed(() =>
  hiddenItems.value.some((item) => navIsActive(route.path, item.to)),
);

/** 相邻两项之间是否需要竖线（跨组才需要）；list 传可见列表或完整列表 */
const sepBefore = (list, index) => {
  if (index <= 0) return false;
  const current = list[index];
  const prev = list[index - 1];
  return Boolean(current && prev) && current.groupIndex !== prev.groupIndex;
};

/**
 * 重算"能放下几项"
 * ------------------------------------------------------------------
 * 用隐藏测量行取每一项的真实宽度（含 padding），再按"可见项 + 竖线 + 间距 +
 * 更多按钮"的累计宽度去比可用宽度。放不下就从尾部往「更多」里收，
 * 最后保证当前页可见（与最后一个可见项交换位置）。
 */
const recomputeNav = async () => {
  if (isCompactHeader.value) {
    // 窄屏：导航独占一行且可换行，全部显示
    navMode.value = 'wrapped';
    isTightUserArea.value = false;
    visibleIdx.value = navItems.value.map((_, index) => index);
    return;
  }

  // 串行化：测量/变更过程中被 ResizeObserver 再次触发时，只记一个"待重算"，
  // 不并发进入（并发会让两轮判定互相覆盖，落到错误形态）。
  if (isRecomputing) {
    recomputePending = true;
    return;
  }
  isRecomputing = true;
  try {
    await runRecompute();
  } finally {
    isRecomputing = false;
    if (recomputePending) {
      recomputePending = false;
      setTimeout(recomputeNav, 0);
    }
  }
};

/**
 * 量出"收紧用户区能回收多少宽度"：用户名 + 管理入口文字 + 它的下拉箭头，
 * 以及它们各自占掉的一个 flex gap。**只读不改 DOM**（见 recomputeNav 的说明）。
 */
const measureTightRecovery = (row) => {
  const gap = parseFloat(getComputedStyle(row).columnGap || getComputedStyle(row).gap) || 0;
  const targets = [
    row.querySelector('.user-name'),
    row.querySelector('.admin-entry-text'),
    row.querySelector('.admin-entry .caret'),
  ];
  let saved = 0;
  targets.forEach((el) => {
    if (el && el.offsetParent !== null) saved += el.getBoundingClientRect().width + gap;
  });
  return saved;
};

const runRecompute = async () => {
  if (isCompactHeader.value) {
    // 窄屏：导航独占一行且可换行，全部显示
    navMode.value = 'wrapped';
    visibleIdx.value = navItems.value.map((_, index) => index);
    return;
  }

  const row = document.querySelector('.header-content');
  const ruler = measureRef.value;
  if (!row || !ruler) return;

  const allIdx = navItems.value.map((_, index) => index);

  /** 按当前 DOM 量一次"单行模式下导航能拿到多少宽度"，并算出能放下几项 */
  const measureInline = async () => {
    await nextTick();
    const brand = row.querySelector('.brand');
    const userInfo = row.querySelector('.user-info');
    if (!brand || !userInfo) return null;
    const rowStyle = getComputedStyle(row);
    const gap = parseFloat(rowStyle.columnGap || rowStyle.gap) || 0;
    /**
     * 用户区宽度取"内核宽度 + 单行模式下的左侧分隔（14px padding + 1px 竖线）"。
     * 必须去掉 padding/border 再补常量：折行模式下这两者被 CSS 去掉了，
     * 直接拿 getBoundingClientRect().width 会让**同一种情况在两种形态下量出不同宽度**，
     * 判定随之来回翻转（实测过：1440 判成两行、1280 反而判成单行）。
     */
    const userStyle = getComputedStyle(userInfo);
    const userCore = userInfo.getBoundingClientRect().width
      - parseFloat(userStyle.paddingLeft) - parseFloat(userStyle.borderLeftWidth);
    const userWidth = userCore + USER_SEP;
    const avail = row.clientWidth
      - parseFloat(rowStyle.paddingLeft) - parseFloat(rowStyle.paddingRight)
      - brand.getBoundingClientRect().width
      - userWidth
      - gap * 2;
    const widths = Array.from(ruler.querySelectorAll('.nav-link:not(.nav-more-trigger)')).map(
      (el) => el.getBoundingClientRect().width,
    );
    const moreEl = ruler.querySelector('.nav-more-trigger');
    const moreWidth = moreEl ? moreEl.getBoundingClientRect().width : 92;
    // 测量尺不可用（被隐藏/尚未挂载）时宽度会全是 0，绝不能据此判定"都放得下"
    if (!widths.length || widths.every((w) => w === 0)) return null;
    return { avail, widths, moreWidth, brandWidth: brand.getBoundingClientRect().width, userWidth };
  };

  /** 贪心：在 avail 里按顺序塞导航项，始终为「更多 ▾」留出位置（并预留安全余量） */
  const fit = ({ avail, widths, moreWidth }) => {
    const budget = avail - SAFETY;
    const kept = [];
    let used = 0;
    for (let index = 0; index < widths.length; index += 1) {
      const item = navItems.value[index];
      const prev = kept.length ? navItems.value[kept[kept.length - 1]] : null;
      const add = widths[index]
        + (kept.length ? GAP : 0)
        + (prev && prev.groupIndex !== item.groupIndex ? SEP : 0);
      const remaining = widths.length - (index + 1);
      const moreCost = remaining > 0 ? moreWidth + GAP : 0;
      if (used + add + moreCost > budget) break;
      used += add;
      kept.push(index);
    }
    if (!kept.length) kept.push(0);
    return kept;
  };

  /**
   * ① 只量**一次**（用户区完整、非收紧状态），后面全是纯计算。
   * ------------------------------------------------------------------
   * 这里曾经用"切换 class 再量一次"的办法来估算收紧后能多出多少宽度，
   * 结果 class 变化又触发 ResizeObserver → 重新进入本函数 → 状态互相打架
   * （实测出现过：导航盒子只有 371px、内容却有 717px，链接糊到品牌文字上）。
   * 现在改为：直接把"收紧会隐藏的那几个元素"的宽度量出来当作可回收空间，
   * 不做任何 DOM 变更，判定因此是**非收紧几何的纯函数**，多次重算结果一致。
   */
  const recovered = measureTightRecovery(row);
  const m = await measureInline();
  if (!m) return;

  const keptFull = fit(m);
  let kept = keptFull;
  let useTight = false;

  if (keptFull.length < m.widths.length) {
    // ② 用户区完整时放不下 → 试试收紧后能否放下（纯计算，不动 DOM）
    const tightFit = fit({ ...m, avail: m.avail + recovered });
    if (tightFit.length > keptFull.length) {
      kept = tightFit;
      useTight = true;
    }
  }

  /**
   * ③ 形态判定：**宁可把导航放到第二行，也不把半个菜单塞进「更多」**。
   * 差 1~2 项用「更多」补（单行更紧凑）；差 3 项以上就整行下移，10 个入口全部可见。
   * 依据：本机实测导航总宽中文 577px / 英文 705px，而 1366 下单行只剩 600 出头。
   */
  const hiddenCount = m.widths.length - kept.length;
  if (hiddenCount > MAX_HIDDEN_INLINE) {
    // 折行形态下导航独占一行，第一行只剩品牌 + 用户区 —— 空间充裕，不必再收紧
    navMode.value = 'wrapped';
    isTightUserArea.value = false;
    visibleIdx.value = allIdx;
    logNavDebug({ ...m, kept: allIdx, mode: 'wrapped', recovered });
    return;
  }

  navMode.value = 'inline';
  isTightUserArea.value = useTight;

  // 当前页必须可见：若它在「更多」里，与最后一个可见项交换
  const activeIndex = navItems.value.findIndex((item) => navIsActive(route.path, item.to));
  if (activeIndex >= 0 && !kept.includes(activeIndex)) {
    kept[kept.length - 1] = activeIndex;
    kept.sort((a, b) => a - b);
  }

  visibleIdx.value = kept.length === m.widths.length ? allIdx : kept;
  logNavDebug({ ...m, kept, mode: 'inline' });
};

/** 开发期调试：把量到的数值挂到 window，便于脚本核对（生产构建不会执行） */
const logNavDebug = (payload) => {
  if (import.meta.env?.DEV) {
    window.__navDebug = {
      ...payload,
      avail: Math.round(payload.avail),
      widths: payload.widths.map((w) => Math.round(w)),
      moreWidth: Math.round(payload.moreWidth),
      brandWidth: Math.round(payload.brandWidth),
      userWidth: Math.round(payload.userWidth),
      tight: isTightUserArea.value,
      sep: SEP,
      gap: GAP,
    };
  }
};

let compactMedia = null;
let resizeObserver = null;
let recomputeTimer = null;
let isRecomputing = false;
let recomputePending = false;

/** 合并短时间内的多次触发（ResizeObserver 会连续回调） */
const scheduleRecompute = () => {
  if (recomputeTimer) clearTimeout(recomputeTimer);
  recomputeTimer = setTimeout(() => {
    recomputeTimer = null;
    recomputeNav();
  }, 60);
};

const onCompactChange = (event) => {
  isCompactHeader.value = event.matches;
  recomputeNav();
};

onMounted(() => {
  compactMedia = window.matchMedia('(max-width: 1199px)');
  isCompactHeader.value = compactMedia.matches;
  compactMedia.addEventListener('change', onCompactChange);
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(scheduleRecompute);
    const el = document.querySelector('.header-content');
    if (el) resizeObserver.observe(el);
  } else {
    window.addEventListener('resize', scheduleRecompute);
  }
  recomputeNav();
});

onBeforeUnmount(() => {
  if (compactMedia) compactMedia.removeEventListener('change', onCompactChange);
  if (resizeObserver) resizeObserver.disconnect();
  else window.removeEventListener('resize', scheduleRecompute);
  if (recomputeTimer) clearTimeout(recomputeTimer);
});

// 切换语言（标签长短变化）与切换路由（当前页变化）都要重算
watch(locale, () => recomputeNav());
watch(() => route.path, () => recomputeNav());
// 字体加载完成后宽度会变，再算一次
if (typeof document !== 'undefined' && document.fonts?.ready) {
  document.fonts.ready.then(() => recomputeNav()).catch(() => {});
}

// 第 116 批：登录 / 注册 / 找回密码 / 管理员登录等**认证页**使用独立全屏布局，
// 不显示站点导航与页脚（这些页面自己带品牌栏，见 AuthShell.vue）
const isBareLayout = computed(() => route.meta?.bareLayout === true);

// 第 117 批：管理后台（/admin/**）用自己的外壳 —— 左侧管理侧栏 + 顶部条，
// **不显示**农户端的顶栏（首页/识别/百科/历史…）与页脚（快速导航/农事工具）。
// 这里只判断"是不是管理区"，具体外壳由 AdminLayout.vue 提供。
const isAdminArea = computed(() => route.meta?.adminArea === true);

// 用户名首字母，用于头像占位
const userInitial = computed(() => {
  const name = authStore.user?.username || 'U';
  return String(name).charAt(0).toUpperCase();
});

// 管理后台入口
const handleAdminCommand = (path) => {
  if (path) router.push(path);
};

// 页脚版权年份：原来写死 2023-2025，跨年后会显得过期，这里跟随当前年份
const currentYear = new Date().getFullYear();

/* ----------------------------------------------------------------------------
 * 导航高亮（第 74 批改为自行判定）
 * ----------------------------------------------------------------------------
 * 原来完全依赖 vue-router 注入的 `.router-link-exact-active`。实测反馈出现
 * "在 /history 页却亮了首页胶囊"这一类串页问题，而项目里只有一处该类选择器、
 * 路由路径（`/` 与 `/history`）也不冲突 —— 这类问题很难复现，但从"谁被点亮"
 * 的角度看，依赖框架的类匹配 + HMR 残留状态，行为不够确定。
 *
 * 判定规则与用例见 utils/navActive.js 及其单测（utils/__tests__/nav-active.spec.js）。
 * -------------------------------------------------------------------------- */
const isNavActive = (path) => navIsActive(route.path, path);

/**
 * 身份核对（第 180 批）
 * ------------------------------------------------------------------
 * · 启动时：`checkAuth()` 是从本地存储恢复（不发请求），之后必须**核对一次**，
 *   否则"管理员刚取消了他的信息编辑员"这件事在本浏览器里要等重新登录才知道；
 * · 标签页重新可见时：管理员改权限通常发生在这期间，回来一刷就生效，不用手动重登。
 *
 * 网络失败时不清登录态（离线模式仍然可用），见 auth.refreshIdentity 的注释。
 */
const refreshIdentitySafely = async () => {
  try {
    await authStore.refreshIdentity();
  } catch (error) {
    console.warn('身份核对失败（保持本地登录态）:', error?.message || error);
  }
};

const onVisibilityChange = () => {
  if (document.visibilityState === 'visible') refreshIdentitySafely();
};

onMounted(async () => {
  if (authStore.authToken) {
    try {
      await authStore.checkAuth();
    } catch (error) {
      console.error('Failed to check auth on mount:', error);
    }
    refreshIdentitySafely();
  }
  document.addEventListener('visibilitychange', onVisibilityChange);
});

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange);
});
</script>

<template>
  <!-- el-config-provider 不产生额外 DOM，仅用于下发 Element Plus 的语言包（跟随界面语言） -->
  <el-config-provider :locale="elementLocale" :z-index="3000">
    <div
      id="app-container"
      :class="{ 'is-bare-layout': isBareLayout, 'is-admin-area': isAdminArea }"
    >
    <header
      v-if="!isBareLayout && !isAdminArea"
      class="app-header"
      :class="{ 'is-nav-wrapped': isNavWrapped, 'is-tight-user': isTightUserArea }"
    >
      <div class="header-content">
        <RouterLink to="/" class="brand" :title="$t('auth.brandName')">
          <span class="brand-logo">
            <img :alt="$t('app.brandAlt')" src="@/assets/农作物病害识别1.png" />
          </span>
          <!-- 品牌文字：≥1500px 显示全称；以下只留图标（鼠标悬停有 title 提示），
               这是为了在 1366/1440 主流桌面宽度下让 10 个导航项保持单行。
               详见 tools/header-feasibility.mjs 的验算。 -->
          <span class="brand-text">
            <strong>{{ $t('auth.brandName') }}</strong>
            <em>Crop Disease Recognition</em>
          </span>
        </RouterLink>

        <!-- 顶栏导航（第 81 批重排）
             · 导航项由 navItems 生成：标签用 navShort.*（紧凑），title 用 nav.* 全称；
             · ≥1200px 单行：放不下的项自动进「更多 ▾」（recomputeNav 实测宽度决定）；
             · <1200px 导航独占一行并换行，全部可见（此时"更多"自动消失）。 -->
        <nav ref="navRef" class="navigation">
          <template v-for="(item, index) in visibleItems" :key="item.to">
            <span v-if="sepBefore(visibleItems, index)" class="nav-sep" aria-hidden="true"></span>
            <RouterLink
              :to="item.to"
              class="nav-link"
              :class="{ 'is-active': isNavActive(item.to) }"
              :title="item.fullLabel"
            >{{ item.label }}</RouterLink>
          </template>

          <!-- 溢出收纳：只有真的放不下时才出现 -->
          <el-dropdown
            v-if="hiddenItems.length"
            trigger="click"
            class="nav-more"
            @command="(path) => path && router.push(path)"
          >
            <span class="nav-link nav-more-trigger" :class="{ 'is-active': activeHidden }">
              {{ $t('nav.more') }}<i class="fas fa-angle-down caret"></i>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="item in hiddenItems"
                  :key="item.to"
                  :command="item.to"
                  :class="{ 'is-current': isNavActive(item.to) }"
                >
                  <i class="fas fa-circle-dot nav-more-dot" :class="{ 'is-on': isNavActive(item.to) }"></i>
                  {{ item.fullLabel }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </nav>

        <!-- 隐藏测量行：与可见导航**同款 class**，保证字号/内边距完全一致（否则量出来的宽度不可信）。
             仅用于取真实宽度：绝对定位 + 0 高度 + visibility:hidden，不参与布局，也不被读屏朗读。 -->
        <nav ref="measureRef" class="navigation nav-measure" aria-hidden="true">
          <template v-for="(item, index) in navItems" :key="`m-${item.to}`">
            <span v-if="sepBefore(navItems, index)" class="nav-sep"></span>
            <span class="nav-link">{{ item.label }}</span>
          </template>
          <span class="nav-link nav-more-trigger">{{ $t('nav.more') }}<i class="fas fa-angle-down caret"></i></span>
        </nav>

        <div class="user-info">
          <!-- 第 50 批：离线状态与待同步队列 -->
          <OfflineIndicator />
          <!-- 第 48 批：语言切换 -->
          <LanguageSwitcher />
          <!-- 管理后台入口（管理员可见，避免管理页无处可进）
               ≤1500px 时只留盾牌图标（title 提示），把文字宽度让给导航，
               使 10 个导航项在主流桌面宽度下保持单行。

               第 117 批：这个下拉**不再重复列 5 个管理页** —— 那些页面现在都在
               管理后台的侧栏里（/admin/**，独立外壳）。农户端这边只留：
               ① 进后台；② 通知中心。

               第 126 批：判定从 `isAdmin` 改成 `canAccessConsole` ——
               第 125 批起信息编辑员（EDITOR）也能进后台，他在这里必须看得到入口，
               否则"有权限却没有门"。（通知中心里的"发布公告"按钮仍然只给全权管理员。） -->
          <el-dropdown v-if="authStore.canAccessConsole" trigger="click" @command="handleAdminCommand">
            <span class="admin-entry" :title="$t('manage.title')">
              <i class="fas fa-user-shield"></i>
              <span class="admin-entry-text">{{ $t('manage.title') }}</span>
              <i class="fas fa-angle-down caret"></i>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="/admin/dashboard">
                  <i class="fas fa-gauge-high"></i> {{ $t('manage.enterConsole') }}
                </el-dropdown-item>
                <!-- 第 37 批：通知中心（发布系统公告也在这里） -->
                <el-dropdown-item command="/notifications">
                  <i class="fas fa-bell"></i> {{ $t('manage.notifications') }}
                </el-dropdown-item>
                <!-- 第 122 批：原来这里有一条「病害百科维护」指向 /pests（那一页头顶曾是
                     管理员工具条）。维护功能已经搬进管理后台侧栏，这里不再重复列。 -->
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <template v-if="authStore.isAuthenticated">
            <!-- 第 42 批：私信入口（未读红点） -->
            <MessageEntry />
            <!-- 第 37 批：通知铃铛（未读红点 + 最近通知下拉） -->
            <NotificationBell />
            <RouterLink
              :to="'/user/profile/' + authStore.user?.id"
              class="user-chip"
              :title="authStore.user?.username"
            >
              <!-- 第 23 批：有真实头像就显示头像，否则用用户名首字母兜底 -->
              <img
                v-if="authStore.user?.avatar"
                :src="authStore.user.avatar"
                :alt="authStore.user?.username || $t('app.avatarAlt')"
                class="user-avatar-img"
              >
              <span v-else class="user-avatar">{{ userInitial }}</span>
              <span class="user-name">{{ authStore.user?.username }}</span>
            </RouterLink>
            <!-- 第 117/118 批：**要把 router 传进去**。不传的话 store 走
                 `window.location.href = '/login'` 整页跳转，而整页卸载会让
                 那个"通知服务端注销 token"的请求被浏览器掐掉（token 服务端仍然有效）。
                 传了 router 就是 SPA 内跳转，页面不卸载，后台请求能跑完。 -->
            <button type="button" class="logout-btn" :title="$t('app.logout')" @click="authStore.logout(router)">
              <i class="fas fa-sign-out-alt"></i>
            </button>
          </template>
          <template v-else>
            <RouterLink to="/login" class="ghost-btn">{{ $t('auth.loginButton') }}</RouterLink>
            <RouterLink to="/register" class="primary-btn">{{ $t('auth.registerNow') }}</RouterLink>
          </template>
        </div>
      </div>
    </header>

    <main class="main-content">
      <!-- 第 117 批：管理页套管理后台外壳（侧栏 + 顶部条），其余页面照旧。
           ⚠️ `<keep-alive>` 只允许**一个**子节点，且 v-if/v-else 必须紧挨着 ——
              所以说明写在 keep-alive 外面（曾把注释写在里面，编译期直接报
              "<KeepAlive> expects exactly one child component"，整站白屏）。 -->
      <RouterView v-slot="{ Component }">
        <keep-alive include="DetectView">
          <AdminLayout v-if="isAdminArea">
            <component :is="Component" />
          </AdminLayout>
          <component v-else :is="Component" />
        </keep-alive>
      </RouterView>
    </main>

    <footer v-if="!isBareLayout && !isAdminArea" class="app-footer">
      <div class="footer-content">
        <div class="footer-brand">
          <div class="footer-brand-head">
            <img :alt="$t('app.brandAlt')" src="@/assets/农作物病害识别1.png" />
            <span>{{ $t('home.heroTitle') }}</span>
          </div>
          <p>{{ $t('footer.intro') }}</p>
          <div class="social-media-icons">
            <button type="button" class="social-icon" :title="$t('app.wechat')" :aria-label="$t('app.wechat')">
              <i class="fab fa-weixin"></i>
            </button>
            <button type="button" class="social-icon" :title="$t('app.weibo')" :aria-label="$t('app.weibo')">
              <i class="fab fa-weibo"></i>
            </button>
            <button type="button" class="social-icon" title="GitHub" aria-label="GitHub">
              <i class="fab fa-github"></i>
            </button>
            <button type="button" class="social-icon" title="QQ" aria-label="QQ">
              <i class="fab fa-qq"></i>
            </button>
          </div>
        </div>

        <div class="footer-section">
          <h3>{{ $t('footer.quickLinks') }}</h3>
          <ul>
            <li><RouterLink to="/">{{ $t('nav.home') }}</RouterLink></li>
            <li><RouterLink to="/detect">{{ $t('nav.detect') }}</RouterLink></li>
            <li><RouterLink to="/pests">{{ $t('nav.pests') }}</RouterLink></li>
            <li><RouterLink to="/history">{{ $t('nav.history') }}</RouterLink></li>
          </ul>
        </div>

        <!-- 农事工具：原来这几项在页脚完全没有入口 -->
        <div class="footer-section">
          <h3>{{ $t('footer.farmTools') }}</h3>
          <ul>
            <li><RouterLink to="/alerts">{{ $t('nav.alerts') }}</RouterLink></li>
            <li><RouterLink to="/calendar">{{ $t('nav.calendar') }}</RouterLink></li>
            <li><RouterLink to="/consult">{{ $t('nav.consult') }}</RouterLink></li>
            <li><RouterLink to="/forum">{{ $t('nav.forum') }}</RouterLink></li>
            <li><RouterLink to="/news">{{ $t('nav.news') }}</RouterLink></li>
          </ul>
        </div>

        <div class="footer-section">
          <h3>{{ $t('footer.contact') }}</h3>
          <ul>
            <li><i class="fas fa-envelope"></i> contact@cropcare.com</li>
            <li><i class="fas fa-phone"></i> 400-123-4567</li>
            <li><i class="fas fa-map-marker-alt"></i> {{ $t('footer.address') }}</li>
            <li><i class="fas fa-clock"></i> {{ $t('footer.workTime') }}</li>
          </ul>
        </div>

        <div class="footer-section">
          <h3>{{ $t('footer.resources') }}</h3>
          <ul>
            <!-- 第 26 批：这四条原来都是 href="#" 的死链，现在指向真实页面 -->
            <li><RouterLink to="/terms">{{ $t('footer.userAgreement') }}</RouterLink></li>
            <li><RouterLink to="/privacy">{{ $t('footer.privacy') }}</RouterLink></li>
            <li><RouterLink to="/help">{{ $t('footer.help') }}</RouterLink></li>
            <li><RouterLink to="/feedback">{{ $t('footer.feedback') }}</RouterLink></li>
          </ul>
        </div>
      </div>

      <div class="footer-bottom">
        <div class="footer-bottom-content">
          <p>&copy; {{ currentYear }} {{ $t('footer.copyright') }}</p>
          <div class="footer-links">
            <!-- 第 26 批：这四条原来也都是 href="#" 死链，改为指向真实页面 -->
            <RouterLink to="/about">{{ $t('nav.about') }}</RouterLink>
            <span class="divider">|</span>
            <RouterLink to="/help">{{ $t('footer.help') }}</RouterLink>
            <span class="divider">|</span>
            <RouterLink to="/terms">{{ $t('footer.userAgreement') }}</RouterLink>
            <span class="divider">|</span>
            <RouterLink to="/privacy">{{ $t('footer.privacy') }}</RouterLink>
          </div>
          <div class="beian">
            <!-- 备案号是国家监管信息，不做翻译 -->
            <a href="https://beian.miit.gov.cn/" target="_blank">京ICP备XXXXXXXX号-1</a>
            <span class="divider">|</span>
            <a href="https://beian.mps.gov.cn/" target="_blank" rel="noopener noreferrer">京公网安备XXXXXXXX号</a>
          </div>
        </div>
      </div>
    </footer>
    </div>
  </el-config-provider>
</template>

<style scoped>
/* ============ 页面骨架 ============ */
#app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  font-family: var(--font-sans);
  color: var(--ink-800);
  background: var(--page-bg);
}

/* 认证页（登录/注册/找回密码/管理员登录）的独立布局 */
#app-container.is-bare-layout {
  background: var(--page-bg);
}

/* ============ 顶栏 ============ */
.app-header {
  position: sticky;
  top: 0;
  z-index: 1000;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(14px) saturate(150%);
  -webkit-backdrop-filter: blur(14px) saturate(150%);
  border-bottom: 1px solid var(--border);
  box-shadow: var(--shadow-xs);
}

.header-content {
  display: flex;
  align-items: center;
  gap: 20px;
  width: 100%;
  max-width: 1600px;
  height: 72px;
  margin: 0 auto;
  padding: 0 28px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
  flex-shrink: 0;
}

.brand-logo {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  background: var(--brand-50);
  border: 1px solid var(--border);
  overflow: hidden;
  transition: transform var(--dur) var(--ease);
}

.brand:hover .brand-logo {
  transform: scale(1.05);
}

.brand-logo img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.brand-text strong {
  font-size: 15.5px;
  font-weight: 700;
  color: var(--brand-800);
  letter-spacing: 0.2px;
  white-space: nowrap;
}

.brand-text em {
  font-style: normal;
  font-size: 10.5px;
  letter-spacing: 1.4px;
  text-transform: uppercase;
  color: var(--ink-400);
}

.navigation {
  display: flex;
  align-items: center;
  /* ≥1200px：单行不换行，宽度由 flex 分配（放不下的项进「更多 ▾」，
     由 recomputeNav 实测决定）；<1200px 由断点改成独占一行 + 换行。 */
  flex: 1 1 auto;
  flex-wrap: nowrap;
  justify-content: center;
  gap: 4px;
  min-width: 0;
  margin: 0 auto;
  /* 不用横向滚动：那等于把末尾项藏起来（滚动条被隐藏后用户看不到也滑不动）。
     溢出改由「更多 ▾」承接。 */
  overflow: visible;
}

/* 隐藏测量行：始终渲染全部导航项，只为取真实宽度。
   不影响布局（absolute + 0 高度 + visibility:hidden），也不被读屏朗读。 */
.nav-measure {
  position: absolute;
  left: -9999px;
  top: 0;
  display: flex;
  align-items: center;
  gap: 4px;
  height: 0;
  overflow: hidden;
  visibility: hidden;
  pointer-events: none;
  white-space: nowrap;
}

/* 单行模式：内边距已在基类统一，这里不再重复覆盖 */

/* 「更多 ▾」按钮：视觉上与导航项一致，便于"当前页在更多里"时点亮 */
.nav-more {
  flex: none;
}

.nav-more-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  outline: none;
  border: 1px dashed var(--brand-200);
  background: var(--brand-50);
  color: var(--brand-700);
}

.nav-more-trigger .caret {
  font-size: 11px;
  opacity: 0.75;
}

.nav-more-trigger:hover {
  background: var(--brand-100);
}

/* 下拉里的当前页：左侧圆点实心 + 加粗，一眼看出"我在这一页" */
.nav-more-dot {
  margin-right: 8px;
  font-size: 7px;
  color: var(--ink-200);
  vertical-align: middle;
}

.nav-more-dot.is-on {
  color: var(--brand-600);
}

/* 组间 1px 竖线分隔（第 73 批）：用 span 而不是 border，
   这样窄屏可以直接 display:none 隐藏，不挤占行宽 */
.nav-sep {
  flex: none;
  width: 1px;
  height: 18px;
  margin: 0 8px;
  background: var(--ink-200);
}

.nav-link {
  display: inline-block;
  /* 第 81 批：内边距/字号**两种形态统一**（原来单行 16px、折行 10px 各一套）。
     统一之后，隐藏测量行量到的宽度在两种形态下都成立，判定不会来回翻转；
     顺带每项省 10px（10 项 100px），正好是"英文放不放得下最后一项"的量级。 */
  padding: 8px 11px;
  border-radius: var(--radius-pill);
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink-600);
  text-decoration: none;
  white-space: nowrap;
  transition: color var(--dur) var(--ease), background-color var(--dur) var(--ease),
    box-shadow var(--dur) var(--ease);
}

.nav-link:hover {
  color: var(--brand-700);
  background: var(--brand-50);
}

/* 当前页：实心绿胶囊 + 白字（一眼可知位置）。
   同时保留对 vue-router 自带 exact-active 的兼容，两者视觉一致。 */
.nav-link.is-active,
.nav-link.router-link-exact-active {
  color: #fff;
  background: var(--brand-600);
  box-shadow: 0 6px 14px rgba(31, 99, 67, 0.22);
}

.nav-link.is-active:hover,
.nav-link.router-link-exact-active:hover {
  color: #fff;
  background: var(--brand-700);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  margin-left: auto;
  /* 用户区与导航之间也加一条竖线，把"导航"和"账户操作"分开 */
  padding-left: 14px;
  border-left: 1px solid var(--ink-200);
}

.admin-entry {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--brand-200);
  background: var(--brand-50);
  color: var(--brand-700);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  outline: none;
  transition: background-color var(--dur) var(--ease), border-color var(--dur) var(--ease);
}

.admin-entry:hover {
  background: var(--brand-100);
  border-color: var(--brand-300);
}

.admin-entry .caret {
  font-size: 11px;
  opacity: 0.7;
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 14px 5px 5px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border);
  background: var(--surface);
  text-decoration: none;
  transition: border-color var(--dur) var(--ease), background-color var(--dur) var(--ease);
}

.user-chip:hover {
  border-color: var(--brand-300);
  background: var(--brand-50);
}

.user-avatar {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--gradient-brand);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
}

/* 真实头像（第 23 批），尺寸与首字母兜底保持一致 */
.user-avatar-img {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  object-fit: cover;
  background: var(--brand-50, #eef7f1);
}

.user-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-700);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 第 81 批：用户区"收紧"形态（由 JS 按实测决定，见 isTightUserArea）
   ----------------------------------------------------------------------------
   实测用户区（离线态 + 语言切换 + 管理入口 + 私信 + 铃铛 + 用户胶囊 + 退出）
   在管理员下占 476px，是"英文导航放不下"的主因。
   只在**单行模式确实放不下**时才收起用户名与管理入口文字（两处都留了 title 悬停提示），
   而不是按视口宽度一刀切 —— 行宽被 max-width 卡在 1600，所以"屏幕更大"并不等于
   "导航位置更多"（1920 反而比 1680 更挤），这种反直觉边界必须实测。 */
.app-header.is-tight-user .user-name {
  display: none;
}

.app-header.is-tight-user .admin-entry-text,
.app-header.is-tight-user .admin-entry .caret {
  display: none;
}

.app-header.is-tight-user .admin-entry {
  padding: 8px 10px;
}

.logout-btn {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--ink-500);
  cursor: pointer;
  transition: all var(--dur) var(--ease);
}

.logout-btn:hover {
  color: var(--danger);
  border-color: #f0d3cf;
  background: #fdf5f4;
}

.ghost-btn {
  padding: 8px 18px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-strong);
  color: var(--ink-700);
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  transition: all var(--dur) var(--ease);
}

.ghost-btn:hover {
  border-color: var(--brand-400);
  color: var(--brand-700);
  background: var(--brand-50);
}

.primary-btn {
  padding: 8px 20px;
  border-radius: var(--radius-pill);
  background: var(--gradient-brand);
  color: #fff !important;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  box-shadow: 0 6px 16px rgba(31, 99, 67, 0.22);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.primary-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgba(31, 99, 67, 0.3);
}

/* ============ 主内容区 ============ */
.main-content {
  flex: 1;
  width: 100%;
  padding: 32px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: calc(100vh - 72px - 380px);
}

#app-container.is-bare-layout .main-content {
  padding: 0;
  min-height: 100vh;
  align-items: stretch;
}

/* 第 117 批：管理后台的内容区由 AdminLayout 自己排（侧栏 + 顶部条 + 内容），
   这里同样去掉主站的居中/内边距，让外壳铺满整屏 */
#app-container.is-admin-area .main-content {
  padding: 0;
  min-height: 100vh;
  align-items: stretch;
}

/* ============ 页脚 ============ */
.app-footer {
  margin-top: 56px;
  background: var(--gradient-hero);
  color: rgba(255, 255, 255, 0.82);
}

.footer-content {
  display: grid;
  /* 五栏：品牌 | 快速导航 | 农事工具 | 联系我们 | 相关资源
     原来只有四栏，论坛 / 预警 / 日历 / 咨询在页脚没有任何入口 ——
     而页脚恰恰是移动端（顶栏折行后）寻找次要入口的地方。
     显式 minmax(0, …) 避免长链接把某栏撑破（grid 默认 min-width:auto）。 */
  grid-template-columns:
    minmax(0, 1.5fr) minmax(0, 0.9fr) minmax(0, 0.9fr)
    minmax(0, 1.1fr) minmax(0, 0.9fr);
  gap: 36px 32px;
  max-width: 1400px;
  margin: 0 auto;
  padding: 56px 32px 36px;
}

.footer-brand-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.footer-brand-head img {
  width: 40px;
  height: 40px;
  object-fit: contain;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.92);
  padding: 4px;
}

.footer-brand-head span {
  font-size: 15.5px;
  font-weight: 700;
  color: #fff;
}

.footer-brand p {
  margin: 0 0 20px;
  font-size: 13.5px;
  line-height: 1.9;
  color: rgba(255, 255, 255, 0.72);
  max-width: 380px;
}

.footer-section h3 {
  position: relative;
  margin: 0 0 16px;
  padding-bottom: 10px;
  font-size: 15.5px;
  font-weight: 700;
  color: #fff;
}

.footer-section h3::after {
  content: '';
  position: absolute;
  left: 0;
  bottom: 0;
  width: 28px;
  height: 2px;
  border-radius: var(--radius-pill);
  background: var(--brand-300);
}

.footer-section ul {
  list-style: none;
  margin: 0;
  padding: 0;
}

/* 页脚正文用 14.5px：深底浅字在户外更难读，比正文档略小但仍高于原来的 13.5px */
.footer-section li {
  margin-bottom: 10px;
  font-size: 14.5px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.78);
}

.footer-section li i {
  width: 16px;
  margin-right: 6px;
  color: var(--brand-300);
}

.footer-section a {
  color: rgba(255, 255, 255, 0.8);
  text-decoration: none;
  transition: color var(--dur) var(--ease), padding-left var(--dur) var(--ease);
}

.footer-section a:hover {
  color: #fff;
  padding-left: 4px;
}

.social-media-icons {
  display: flex;
  gap: 10px;
}

.social-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.85);
  font-size: 15px;
  cursor: pointer;
  transition: all var(--dur) var(--ease);
}

.social-icon:hover {
  transform: translateY(-3px);
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.footer-bottom {
  border-top: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(0, 0, 0, 0.12);
}

.footer-bottom-content {
  max-width: 1400px;
  margin: 0 auto;
  padding: 22px 32px;
  text-align: center;
}

.footer-bottom p {
  margin: 0 0 10px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.66);
}

.footer-links {
  margin-bottom: 10px;
  font-size: 13px;
}

.footer-links a {
  color: rgba(255, 255, 255, 0.78);
  text-decoration: none;
  margin: 0 6px;
  transition: color var(--dur) var(--ease);
}

.footer-links a:hover {
  color: #fff;
}

.divider {
  color: rgba(255, 255, 255, 0.3);
  margin: 0 2px;
}

.beian {
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.55);
}

.beian a {
  color: rgba(255, 255, 255, 0.62);
  text-decoration: none;
  transition: color var(--dur) var(--ease);
}

.beian a:hover {
  color: #fff;
}

/* ============ 响应式 ============ */
/* 断点策略（第 81 批重排，替换掉第 73 批"放不下就折行 / 藏品牌名"的取舍）
 * ----------------------------------------------------------------------------
 * 硬约束没变：品牌 + 10 个导航项 + 用户区要在一行里放下，英文比中文更宽。
 * 但第 73 批的做法（≤1500px 把品牌全称与"管理"文字藏掉、≤2000px 就折到第二行）
 * 带来两个体验问题：1366/1440 上产品名消失、头高长期 119px。
 *
 * 现在的做法：
 *   · ≥1200px —— **单行**，头高 72px；导航用 `navShort.*` 紧凑标签（悬停显示全称），
 *     仍然放不下的项由 JS 实测宽度收进「更多 ▾」，绝不裁切、绝不静默隐藏；
 *   · <1200px —— 导航整行下移并允许换行（全部可见，不再收纳），品牌全称保留；
 *   · 始终 overflow: visible：基类曾经用过 `overflow-x: auto` + 隐藏滚动条，
 *     那等于把末尾项"静默裁切"（就是之前"论坛/历史不见了"的成因）。
 * -------------------------------------------------------------------------- */
/* ----------------------------------------------------------------------------
 * 第 81 批：顶栏两行形态（由 JS 判定，见 recomputeNav 的 navMode）
 * ----------------------------------------------------------------------------
 * 触发条件（实测）：导航放不下 **2 项以上**时，宁可整行下移让 10 个入口全部可见，
 * 也不把半个菜单塞进「更多 ▾」。窄屏（<1200px）同样走这个形态
 * —— 两种情形都由 JS 加上 .is-nav-wrapped，这里的规则只认这个类，
 * 不再用媒体查询重复一遍（避免同一套声明写两处、日后改漏一处）。
 * -------------------------------------------------------------------------- */
.app-header.is-nav-wrapped .header-content {
  flex-wrap: wrap;
  height: auto;
  min-height: 72px;
  padding-top: 8px;
  padding-bottom: 8px;
}

.app-header.is-nav-wrapped .navigation {
  order: 3;
  flex: 1 0 100%;
  width: 100%;
  margin: 0;
  flex-wrap: wrap;
  justify-content: center;
  row-gap: 6px;
  overflow: visible;
  padding-bottom: 2px;
}

/* 整行排布时用户区不再需要左侧分隔线（宽度补偿见 recomputeNav 的 USER_SEP） */
.app-header.is-nav-wrapped .user-info {
  padding-left: 0;
  border-left: none;
}

/* 折行形态下横向更紧：管理入口收成图标（名称仍在 title 里） */
.app-header.is-nav-wrapped .admin-entry-text,
.app-header.is-nav-wrapped .admin-entry .caret {
  display: none;
}

.app-header.is-nav-wrapped .admin-entry {
  padding: 8px 10px;
}

/* 注意：导航项的内边距/字号/竖线间距**不在这里覆盖** —— 两种形态必须一致，
   否则隐藏测量行量到的宽度只在其中一种形态下成立，判定会来回翻转。 */

/* 注意：**不要**在折行形态下隐藏 .nav-measure。
   它是 hidden 但仍在布局中的测量尺，一旦 display:none，量到的宽度全变 0，
   下一轮判定就会认为"10 项都放得下"→切回单行→再量到真宽度→切回两行，
   顶栏会以每秒一次的频率来回跳（实测过）。它绝对定位 + 0 高度，本来就不影响布局。 */

/* ----------------------------------------------------------------------------
 * 第 81 批：删除了原「≤1500px 把品牌全称与"管理"文字收成图标」的规则
 * ----------------------------------------------------------------------------
 * 那条规则是为了在 1366/1440 上硬凑导航单行（详见 tools/header-feasibility.mjs），
 * 代价是产品名在这些宽度上直接消失。现在单行由"紧凑标签 + 「更多 ▾」收纳"保证，
 * 品牌全称始终保留；"管理"文字只在 <1200px（导航独占一行、横向更紧）时收成图标，
 * 规则已并入上面的 1199px 断点。
 * -------------------------------------------------------------------------- */

/* 页脚五栏的退让节奏：1400 → 3 栏 → 2 栏（1024）→ 1 栏（768）。
   品牌栏（第 1 栏）在 3 栏与 2 栏时占满整行，避免被压成很窄的一条。 */
@media (max-width: 1400px) {
  .footer-content {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 32px 28px;
  }

  .footer-brand {
    grid-column: 1 / -1;
    max-width: 560px;
  }
}

@media (max-width: 1024px) {
  .footer-content {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 28px 24px;
    padding: 44px 24px 28px;
  }

  /* 第 81 批：品牌全称保留（不再整体隐藏），空间不够时用省略号，
     并把装饰性的拉丁副标题收掉 —— 产品名是有效信息，不该消失。 */
  .brand-text strong {
    font-size: 14px;
    max-width: 42vw;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .brand-text em {
    display: none;
  }
}
@media (max-width: 768px) {
  .header-content {
    height: auto;
    flex-wrap: wrap;
    gap: 12px;
    padding: 12px 16px;
  }

  .brand {
    flex: 1;
  }

  /* 手机端：自动换行成两行，全部可见。
     原来的横滑（overflow-x:auto）+ 右侧渐隐遮罩（mask-image）在这里去掉 ——
     手机用户不必滑动，也不会误以为"末尾项被裁掉了"。 */
  .navigation {
    order: 3;
    width: 100%;
    margin: 0;
    padding: 4px 0;
    flex-wrap: wrap;
    justify-content: center;
    row-gap: 6px;
    overflow: visible;
    mask-image: none;
    -webkit-mask-image: none;
  }

  /* 竖线在窄屏隐藏，避免挤占行宽 */
  .nav-sep {
    display: none;
  }

  /* 触屏点击区加大（接近 44px 触控标准） */
  .nav-link {
    padding: 10px 14px;
    font-size: 15px;
  }

  .user-info {
    margin-left: 0;
  }

  .main-content {
    padding: 20px 0;
  }

  .footer-content {
    grid-template-columns: 1fr;
    padding: 40px 20px 28px;
  }

  .footer-bottom-content {
    padding: 20px;
  }

  .footer-brand p {
    max-width: none;
  }
}
</style>
