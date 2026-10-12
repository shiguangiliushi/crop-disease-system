<template>
  <!--
    ⚠️ Vant 的 locale 与自研 i18n 是两套东西：ConfigProvider 管组件内建文案
    （"加载中""确定"等），而 showToast()/showDialog() 这类命令式调用不经过它，
    必须额外用 Locale.use() 全局切换（见下面 watch）。
    第 173 批：ConfigProvider 同时接管**主题变量**（主色/圆角/字号一处改）。
  -->
  <van-config-provider :locale="vantLocale" :theme-vars="themeVars">
    <!--
      第 173 批：**顶栏收进外壳，由路由 meta 驱动**
      ------------------------------------------------------------------
      改前 7 个页面里只有 5 个自己写了 `<van-nav-bar>`，识别页与登录页**根本没有顶栏** ——
      同一个 App 里两页像 App、两页像网页（基线截图对比很明显）。
      现在统一由外壳渲染，页面只声明 meta：

        meta.title  → 标题（i18n key，取不到就退回 document.title）
        meta.back   → 是否显示返回箭头（详情/表单类页面 true；tab 页与登录页 false）
        meta.navbar → 显式 false 才隐藏整条顶栏（默认都显示）

      另外统一成 `fixed placeholder`：改前登录/注册/找回这三页的顶栏是**随内容滚动**的，
      而识别记录/我的/结果页是固定的 —— 同样是同一个 App 里两种行为。
    -->
    <van-nav-bar
      v-if="showNavBar"
      :title="navTitle"
      :left-arrow="showBack"
      fixed
      placeholder
      @click-left="goBack"
    />

    <!--
      第 91 批：`<keep-alive>` 保住页面状态
      ------------------------------------------------------------------
      改前是裸 `<router-view />`，于是**切一下 tab 就丢照片**：
      农户在识别页拍完照、切到"记录"看一眼、再切回来 —— 组件被销毁重建，
      `previewUrl` / `selectedFile` 全没了，只能**重新拍一张**（在田里戴着手套，
      这是最烦人的一种返工）。
      只缓存真正需要保状态的页面（识别页、记录页）；结果页/登录页不缓存 ——
      结果页要按路由参数重新取数，缓存了反而会显示上一条。

      第 173 批：外面套一层**页面切换动画**（像 App 的推入/淡入，而不是网页的瞬间替换）。
      ⚠️ transition 与 keep-alive 同用必须 `mode="out-in"`，否则两个页面会同时渲染、
      动画期间能看到两层内容叠在一起。顺序也固定：transition → keep-alive → 组件。
    -->
    <router-view v-slot="{ Component }">
      <transition name="fade-slide" mode="out-in">
        <keep-alive :include="cachedViews">
          <component :is="Component" />
        </keep-alive>
      </transition>
    </router-view>

    <!-- 第 91 批：离线队列指示（离线中 / 有照片待补传时才出现） -->
    <OfflineIndicator />

    <TabBar v-if="showTabBar" />

    <!--
      第 173 批：底部安全区留白
      没有底部导航的页面（登录/结果等）贴到屏幕最下沿时，内容会被 iPhone 的
      底部横条压住。这里垫一段 env(safe-area-inset-bottom) —— 有 TabBar 时
      TabBar 自己已经带了（safe-area-inset-bottom），不需要重复垫。
    -->
    <div v-if="!showTabBar" class="safe-bottom" aria-hidden="true" />
  </van-config-provider>
</template>

<script setup>
/**
 * 应用外壳（第 173 批：统一顶栏 + 页面切换动画 + 主题变量）
 * ----------------------------------------------------------------------------
 * 这一层**只影响移动端**：桌面端是另一个工程（frontend/src/App.vue，Element Plus），
 * 两边各自独立构建，唯一的共享面是后端 API。
 *
 * 三个容易踩的点（沿用第 91 批的注释，仍然成立）：
 *   1. Vant locale 与自研 i18n 是两套东西（见模板里的说明）；
 *   2. tabbar 由路由 meta 控制：登录页、结果页不显示（结果页要沉浸看诊断结论）；
 *   3. `keep-alive` 的 `include` 匹配的是**组件的 name**（`<script setup>` 里用的是
 *      文件名推导出来的名字），所以下面列的是 'DetectView' / 'HistoryView'，不是路由名。
 */
import { computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Locale } from 'vant';
// ⚠️ 必须带 .mjs 后缀：vant 4.10 的 es 目录只发布 .mjs（没有 .js、也没有 exports 映射），
// 写成 'vant/es/locale/lang/zh-CN' 会在构建期直接 "Rollup failed to resolve import"。
import zhCN from 'vant/es/locale/lang/zh-CN.mjs';
import enUS from 'vant/es/locale/lang/en-US.mjs';
import TabBar from '@/components/TabBar.vue';
import OfflineIndicator from '@/components/OfflineIndicator.vue';
import { useI18n } from '@/i18n';

const route = useRoute();
const router = useRouter();
const { t, locale } = useI18n();

const vantLocale = computed(() => (locale.value === 'en' ? enUS : zhCN));
const showTabBar = computed(() => route.meta?.tabbar !== false);
/** 需要保留状态的页面（组件 name） */
const cachedViews = ['DetectView', 'HistoryView'];

/**
 * 主题变量：主色与网页端保持一致（`--brand: #2e7d32`，见 styles/app.css），
 * 圆角比 Vant 默认更大一点 —— App 的观感来自"更大的圆角 + 更松的留白"。
 */
const themeVars = {
  primaryColor: '#2e7d32',
  buttonPrimaryBackground: '#2e7d32',
  buttonPrimaryBorderColor: '#2e7d32',
  navBarTitleFontSize: '17px',
  navBarHeight: '48px',
  radiusMd: '10px',
  radiusLg: '14px',
  tabbarItemActiveColor: '#2e7d32',
};

// -- 顶栏（第 173 批）-------------------------------------------------------
const showNavBar = computed(() => route.meta?.navbar !== false);
const showBack = computed(() => route.meta?.back === true);
const navTitle = computed(() => {
  const key = route.meta?.title;
  if (!key) return '';
  const text = t(key);
  // t() 取不到时会把 key 原样返回（界面会露出 'detect.title' 这种字面量）——
  // 这里兜一层：看起来像 key 的就留空，由 document.title 那套兜底。
  return text && text !== key ? text : '';
});

/**
 * 返回：优先浏览器历史；**直接从分享链接打开时没有上一页** →
 * 回识别页（App 的"首页"）。与网页端 `utils/navigation.js` 的 goBackOr 是同一个判据，
 * 只是移动端这里不需要单独抽文件。
 */
const goBack = () => {
  if (window.history?.state?.back) router.back();
  else router.replace('/detect');
};

watch(
  locale,
  (value) => Locale.use(value === 'en' ? 'en-US' : 'zh-CN'),
  { immediate: true },
);
</script>

<style>
/* 页面切换动画（第 173 批）：轻微上移 + 淡入，像 App 的页面推入 */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* 没有底部导航的页面：垫出安全区（见模板里的说明） */
.safe-bottom {
  height: env(safe-area-inset-bottom, 0px);
}
</style>
