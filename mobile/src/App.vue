<template>
  <van-config-provider :locale="vantLocale">
    <!--
      第 91 批：`<keep-alive>` 保住页面状态
      ------------------------------------------------------------------
      改前是裸 `<router-view />`，于是**切一下 tab 就丢照片**：
      农户在识别页拍完照、切到"记录"看一眼、再切回来 —— 组件被销毁重建，
      `previewUrl` / `selectedFile` 全没了，只能**重新拍一张**（在田里戴着手套，
      这是最烦人的一种返工）。

      只缓存真正需要保状态的页面（识别页、记录页）；结果页/登录页不缓存 ——
      结果页要按路由参数重新取数，缓存了反而会显示上一条。
    -->
    <router-view v-slot="{ Component }">
      <keep-alive :include="cachedViews">
        <component :is="Component" />
      </keep-alive>
    </router-view>

    <!-- 第 91 批：离线队列指示（离线中 / 有照片待补传时才出现） -->
    <OfflineIndicator />

    <TabBar v-if="showTabBar" />
  </van-config-provider>
</template>

<script setup>
/**
 * 应用外壳
 * ----------------------------------------------------------------------------
 * 三个容易踩的点：
 *   1. **Vant 的 locale 与自研 i18n 是两套东西**：ConfigProvider 管组件内建文案
 *      （"加载中""确定"等），而 `showToast()` / `showDialog()` 这类命令式调用
 *      **不经过 ConfigProvider**，必须额外用 `Locale.use()` 全局切换，否则切到英文后
 *      弹窗里还是中文。
 *   2. tabbar 由路由 meta 控制：登录页、结果页不显示（结果页要沉浸看诊断结论，
 *      底部导航会让人误以为还没离开识别流程）。
 *   3. `keep-alive` 的 `include` 匹配的是**组件的 name**（`<script setup>` 里用的是
 *      文件名推导出来的名字），所以下面列的是 'DetectView' / 'HistoryView'，
 *      不是路由名。
 */
import { computed, watch } from 'vue';
import { useRoute } from 'vue-router';
import { Locale } from 'vant';
// ⚠️ 必须带 .mjs 后缀：vant 4.10 的 es 目录只发布 .mjs（没有 .js、也没有 exports 映射），
// 写成 'vant/es/locale/lang/zh-CN' 会在构建期直接 "Rollup failed to resolve import"。
import zhCN from 'vant/es/locale/lang/zh-CN.mjs';
import enUS from 'vant/es/locale/lang/en-US.mjs';
import TabBar from '@/components/TabBar.vue';
import OfflineIndicator from '@/components/OfflineIndicator.vue';
import { useI18n } from '@/i18n';

const route = useRoute();
const { locale } = useI18n();

const vantLocale = computed(() => (locale.value === 'en' ? enUS : zhCN));
const showTabBar = computed(() => route.meta?.tabbar !== false);
/** 需要保留状态的页面（组件 name） */
const cachedViews = ['DetectView', 'HistoryView'];

watch(
  locale,
  (value) => Locale.use(value === 'en' ? 'en-US' : 'zh-CN'),
  { immediate: true },
);
</script>
