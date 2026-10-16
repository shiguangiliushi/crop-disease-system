
<script setup>
// 首页
// 路由：/
//
// 页面由五块组成（页脚由 App.vue 统一渲染，不在这里）：
//   1) 系统公告横幅（第 37 批，管理员在通知页发）
//   2) 预警提示条（第 46 批，有未读预警才出现）
//   3) 轮播（carouselSlides，文案走 i18n）
//   4) 功能入口网格（features）
//   5) 热门作物卡片（popularCrops）
//
// 改这个文件前值得知道的几件事：
//   · popularCrops 的 diseaseCount 是**从 commonDiseases.length 派生**的
//     （第 107 批改的）—— 不要再手写数字；
//   · 同一份数据里曾经有 diseaseKeys（ML 数据集类别名），**全项目无人读取**，
//     第 107 批已删。要按作物筛选请用 path 上的 crop 查询参数；
//   · navigateTo 会把**任何**导航失败跳到 /404（含用户主动取消导航），
//     这是刻意策略，不是漏写判断。
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { fetchLatestAnnouncement } from '@/api/notify';  // 第 37 批：首页公告横幅
import { fetchAlerts } from '@/api/alert';  // 第 46 批：首页病害预警提示条
import { useAuthStore } from '@/stores/auth';
import { useI18n } from '@/i18n';  // 第 57 批：多语言（首页此前漏接）
import { useLocalized } from '@/utils/localized';  // 第 72 批：预警文案/热门作物的英文内容

const { t, tl } = useI18n();
const { localizedField } = useLocalized();

// 使用内联 SVG 图标，确保显示
// 注意：vue3-carousel 的 CSS 已经在 main.js 中全局导入
import { Carousel, Slide } from 'vue3-carousel';

// 注册组件
const components = {
  Carousel,
  Slide
};

// 说明：原来这里维护了 isLoading / carouselLoaded / preloadImages 三个状态，
// 但模板里从未使用（真正的加载遮罩早就不存在了），且 onMounted 里用固定
// 500ms + 300ms 的 setTimeout 假装加载。现已清理，仅保留必要的初始化日志。

// ============================================================================
// 公告横幅（第 37 批）
// ----------------------------------------------------------------------------
// 管理员在通知中心发布的置顶公告，会在首页顶部显示成一条可关闭的横幅；
// 关闭状态记在 localStorage（按公告 id 记），刷新后不会重复弹同一条。
// ============================================================================
const announcement = ref(null);
const announcementClosed = ref(false);
const ANNOUNCEMENT_KEY = 'dismissed_announcement_id';

const loadAnnouncement = async () => {
  try {
    const data = await fetchLatestAnnouncement();
    const item = data?.announcement;
    if (!item) return;
    if (localStorage.getItem(ANNOUNCEMENT_KEY) === String(item.id)) return;
    announcement.value = item;
  } catch (error) {
    // 公告是附加信息，失败静默即可
    console.warn('获取公告失败:', error);
  }
};

const closeAnnouncement = () => {
  announcementClosed.value = true;
  if (announcement.value) {
    localStorage.setItem(ANNOUNCEMENT_KEY, String(announcement.value.id));
  }
};

// ============================================================================
// 病害预警提示条（第 46 批）
// ----------------------------------------------------------------------------
// 只在确实存在"高发期 / 明显增多"级预警时显示（low 级不进首页，避免狼来了）。
//
// ⚠️ 第 216 批：**不再要求登录**。
// 预警是"当期哪些病害在抬头"的公共信息 —— 挡在登录后面，等于把第一屏最有说服力的
// 内容藏起来（游客只看得到静态文案），而它对游客恰好最有用，也是最好的引流。
//
// 后端 `AlertListView` 已改为 `AllowAny`，并且**核实过不会泄露个人信息**：
// `compute_alerts` 里 `getattr(user, 'is_authenticated', False)` 为假时，
// `is_personal` / `alerted_before` 恒为 False、`my_count` 恒为 0、
// message 里不会出现"你…"前缀（实测 4 条预警，含个人信息 0 条）。
// ============================================================================
const authStore = useAuthStore();
const alertData = ref(null);

const topAlert = computed(() => {
  const alerts = alertData.value?.alerts || [];
  return alerts.find((item) => item.level === 'high') || alerts.find((item) => item.level === 'medium') || null;
});
const alertTotal = computed(() => alertData.value?.summary?.total || 0);

const loadAlerts = async () => {
  try {
    alertData.value = await fetchAlerts({ days: 7 });
  } catch (error) {
    // 预警是附加信息，失败静默
    console.warn('获取病害预警失败:', error);
  }
};

onMounted(() => {
  console.log('HomeView mounted');
  loadAnnouncement();
  loadAlerts();
});

const router = useRouter();

// 导航函数
const navigateTo = (path) => {
  try {
    console.log('Navigating to:', path);
    if (path) {
      router.push(path).catch(err => {
        console.error('Navigation error:', err);
        // 如果是未知路由，跳转到404页面
        if (err.name === 'NavigationDuplicated') {
          console.log('Navigation duplicated, ignoring...');
        } else {
          router.push('/404');
        }
      });
    } else {
      console.warn('Navigation path is empty');
    }
  } catch (error) {
    console.error('Error in navigation:', error);
  }
};

/* ----------------------------------------------------------------------------
 * 第 74 批：轮播卡片配色统一到农业绿
 * ----------------------------------------------------------------------------
 * 原来四张卡分别是 蓝(#4facfe)/粉(#ff9a9e)/紫(#a18cd1)/橙粉(#ff9a9e,#f6d365)，
 * 与全站绿主色并存 —— 首屏第一眼就是一张蓝色大卡，观感上不像同一个系统。
 * 这里改为同一绿色系的四档明度：深绿（识别，主路径）→ 中绿（百科）→
 * 青绿（论坛）→ 黄绿（动态）。四张卡仍可区分，但不再各自为政。
 * 全部为浅色渐变，因此卡内文字继续使用深色（原来是白字，见模板 .hero-card 颜色）。
 * -------------------------------------------------------------------------- */
const SLIDE_THEMES = {
  detect: 'linear-gradient(135deg, #d9f0e2 0%, #a8d8bd 100%)',
  wiki: 'linear-gradient(135deg, #e6f6ec 0%, #bfe3cd 100%)',
  forum: 'linear-gradient(135deg, #dff2ef 0%, #b3ded6 100%)',
  news: 'linear-gradient(135deg, #eef7e4 0%, #cfe6b8 100%)',
};

// 轮播图数据 - 优化后的卡片式设计
const carouselSlides = ref([
  {
    id: 'slide-1',
    titleKey: 'home.slideDetectTitle',
    descKey: 'home.slideDetectDesc',
    buttonKey: 'home.slideDetectButton',
    buttonLink: '/detect',
    icon: `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-14h2v6h-2zm0 8h2v2h-2z"/>
      </svg>
    `,
    bgColor: SLIDE_THEMES.detect,
    featuresKey: 'home.slideDetectFeatures'
  },
  {
    id: 'slide-2',
    titleKey: 'home.slideWikiTitle',
    descKey: 'home.slideWikiDesc',
    buttonKey: 'home.slideWikiButton',
    buttonLink: '/pests',
    icon: `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
        <path d="M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z"/>
      </svg>
    `,
    bgColor: SLIDE_THEMES.wiki,
    featuresKey: 'home.slideWikiFeatures'
  },
  {
    id: 'slide-3',
    titleKey: 'home.slideForumTitle',
    descKey: 'home.slideForumDesc',
    buttonKey: 'home.slideForumButton',
    buttonLink: '/forum',
    icon: `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6l-2 2V6h16v10z"/>
      </svg>
    `,
    bgColor: SLIDE_THEMES.forum,
    featuresKey: 'home.slideForumFeatures'
  },
  {
    id: 'slide-4',
    titleKey: 'home.slideNewsTitle',
    descKey: 'home.slideNewsDesc',
    buttonKey: 'home.slideNewsButton',
    buttonLink: '/news',
    icon: `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
        <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14z"/>
        <path d="M7 10h10v2H7zM7 14h7v2H7z"/>
      </svg>
    `,
    bgColor: SLIDE_THEMES.news,
    featuresKey: 'home.slideNewsFeatures'
  }
]);

// 功能区域数据（第 74 批：配色统一到绿色系四档，原来用蓝#3a7bd5 + 粉#ff9a9e，
// 与全站绿主色并存；四张卡仍可区分，但不再各自为政）
const features = [
  {
    titleKey: 'home.featureDetectTitle',
    descKey: 'home.featureDetectDesc',
    path: '/detect',
    color: '#2a7f53',
    colorRgb: '42, 127, 83',
    svg: `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="48" height="48">
        <path d="M9 2L7.17 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2h-3.17L15 2H9zm3 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5z"/>
        <circle cx="12" cy="12" r="3"/>
      </svg>
    `
  },

  {
    titleKey: 'home.featureWikiTitle',
    descKey: 'home.featureWikiDesc',
    path: '/pests',
    color: '#3d9a68',
    colorRgb: '61, 154, 104',
    svg: `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="48" height="48">
        <path d="M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z"/>
      </svg>
    `
  },

  {
    titleKey: 'home.featurePreventionTitle',
    descKey: 'home.featurePreventionDesc',
    path: '/preventions/1', // 添加默认病害ID，例如1
    color: '#5fb088',
    colorRgb: '95, 176, 136',
    svg: `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="48" height="48">
        <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/>
      </svg>
    `
  },
  {
    titleKey: 'home.featureHistoryTitle',
    descKey: 'home.featureHistoryDesc',
    path: '/history',
    color: '#194f37',
    colorRgb: '25, 79, 55',
    svg: `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="48" height="48">
        <path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"/>
      </svg>
    `
  }
];

// 热门作物数据（文案走 i18n：切语言时作物名与常见病害名一起变）
//
// ⚠️ 第 107 批：删掉了每项里的 `diseaseKeys`，并把 `diseaseCount` 改成**派生值**。
//
// `diseaseKeys` 原本是四组 ML 数据集类别名（`Apple___Cedar_apple_rust` 这种），
// **全项目没有任何地方读它**（grep 确认：4 处定义、0 处读取）——
// 它看起来像"这个卡片的数据源"，实际是死数据；下一个人很可能会去维护它、
// 甚至想按它生成链接，而它根本不影响页面。
//
// `diseaseCount` 原来是手写的数字（苹果 3、马铃薯 2、玉米 3、葡萄 3），
// 与 `commonDiseases.length` 是同一件事的两次书写 —— 多写一次就多一次不一致的机会
// （而且实测已经有偏差：苹果那组 `diseaseKeys` 里的 `Cedar_apple_rust` 是雪松锈病，
//  并不在黑星病/黑腐病/锈病这三个展示项里）。
// 现在由 `commonDiseases.length` 自动得出：
//   · 想改数量只改 `commonDiseases` 一处；
//   · 中英文切换时数量自然跟着文案走（原来数字写死，若某种语言多一条就会对不上）。
const popularCrops = computed(() => {
  // 第 169 批：图标换成**「关于」页那套作物 emoji**（🍎🥔🌽🍇）。
  //
  // 原来这里是 Bootstrap 图标，而且是"凑合"出来的：苹果用 `bi-bug`（一只虫子 ✗）、
  // 马铃薯用 `bi-circle`、玉米用 `bi-flower2`、葡萄用 `bi-basket`（代码里自己写着
  // "使用篮子图标作为替代"）。同一个"苹果"在关于页是 🍎、在首页是一只虫子，
  // 用户看到的就是"两张页面各说各话"（用户反馈要求换成关于页那一套）。
  //
  // 用 emoji 而不是图标字体还有一个实际好处：emoji 由系统字体渲染，
  // 不依赖 Font Awesome / Bootstrap Icons 有没有加载成功 —— 首页首屏最不该出现空方块。
  const crops = [
    {
      name: t('home.cropApple'),
      icon: '🍎',
      path: '/pests?crop=apple',
      commonDiseases: [
        t('home.diseaseAppleScab'),
        t('home.diseaseAppleBlackRot'),
        t('home.diseaseAppleRust'),
      ],
      bgColor: '#ffebee'
    },
    {
      name: t('home.cropPotato'),
      icon: '🥔',
      path: '/pests?crop=potato',
      commonDiseases: [t('home.diseasePotatoEarlyBlight'), t('home.diseasePotatoLateBlight')],
      bgColor: '#e3f2fd'
    },
    {
      name: t('home.cropCorn'),
      icon: '🌽',
      path: '/pests?crop=corn',
      commonDiseases: [
        t('home.diseaseCornCommonRust'),
        t('home.diseaseCornGrayLeafSpot'),
        t('home.diseaseCornNorthernLeafBlight'),
      ],
      bgColor: '#e8f5e9'
    },
    {
      name: t('home.cropGrape'),
      icon: '🍇',
      path: '/pests?crop=grape',
      commonDiseases: [
        t('home.diseaseGrapeLeafBlight'),
        t('home.diseaseGrapeEsca'),
        t('home.diseaseGrapeBlackRot'),
      ],
      bgColor: '#f3e5f5'
    }
  ];

  // 数量从展示项派生，不再手写
  return crops.map((crop) => ({ ...crop, diseaseCount: crop.commonDiseases.length }));
});
</script>

<template>
  <div class="home">
    <!-- 系统公告横幅（第 37 批） -->
    <div v-if="announcement && !announcementClosed" class="announce-bar">
      <span class="announce-icon"><i class="fas fa-bullhorn"></i></span>
      <div class="announce-content">
        <strong>{{ announcement.title }}</strong>
        <span class="announce-text">{{ announcement.content }}</span>
      </div>
      <button type="button" class="announce-close" :title="t('common.dismiss')" @click="closeAnnouncement">
        <i class="fas fa-xmark"></i>
      </button>
    </div>

    <!-- 病害预警提示条（第 46 批）：只在有"高发/明显增多"级预警时出现 -->
    <div v-if="topAlert" class="alert-bar" :class="`is-${topAlert.level}`">
      <span class="alert-icon">
        <i :class="topAlert.level === 'high' ? 'fas fa-bolt' : 'fas fa-triangle-exclamation'"></i>
      </span>
      <div class="alert-content">
        <strong>{{ localizedField(topAlert, 'title') }}</strong>
        <span class="alert-text">{{ localizedField(topAlert, 'message') }}</span>
      </div>
      <RouterLink to="/alerts" class="alert-more">
        {{ alertTotal > 1 ? t('home.alertBarMoreCount', { count: alertTotal }) : t('alerts.title') }}
        <i class="fas fa-arrow-right"></i>
      </RouterLink>
    </div>

    <!-- 顶部轮播 -->
    <section class="hero">
      <div class="hero-inner">
        <carousel
          v-if="carouselSlides.length > 0"
          ref="carousel"
          :autoplay="5000"
          :wrap-around="true"
          :transition="1000"
          :items-to-show="Math.min(3, carouselSlides.length)"
          :breakpoints="{
            320: { itemsToShow: 1 },
            768: { itemsToShow: 2 },
            1024: { itemsToShow: 3 }
          }"
          :snap-align="'start'"
          :mouse-drag="true"
          :touch-drag="true"
        >
          <slide v-for="slide in carouselSlides" :key="'slide-' + slide.id" class="hero-slide">
            <article class="hero-card" :style="{ background: slide.bgColor }">
              <div class="hero-body">
                <div class="hero-icon" v-html="slide.icon"></div>
                <h3 class="hero-title">{{ t(slide.titleKey) }}</h3>
                <p class="hero-desc">{{ t(slide.descKey) }}</p>

                <ul v-if="slide.featuresKey" class="hero-features">
                  <li v-for="(feat, i) in tl(slide.featuresKey)" :key="'feature-' + i">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
                    </svg>
                    <span>{{ feat }}</span>
                  </li>
                </ul>

                <button type="button" class="hero-btn" @click="navigateTo(slide.buttonLink)">
                  <span>{{ t(slide.buttonKey) }}</span>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z" />
                  </svg>
                </button>
              </div>

              <!-- 右下角装饰（第 30 批修复）
                   原来这里是 <img :src="slide.image" :alt="slide.title">，指向
                   public/images/*.jpg —— 但 frontend/public 下**只有 favicon.ico**，
                   这些文件根本不存在：图片 404 后浏览器会在右下角画出"碎图图标 + alt 文字"，
                   而 alt 正好等于卡片标题，于是看起来像"标题又在角落里出现了一次"。
                   现改为用卡片自身的图标做半透明水印：纯 SVG、不发起任何图片请求，
                   永远不会再出现碎图。 -->
              <div class="hero-art" aria-hidden="true" v-html="slide.icon"></div>
            </article>
          </slide>

          <template #addons>
            <div class="hero-controls">
              <button type="button" class="hero-nav" :aria-label="t('home.prevSlide')" @click="$refs.carousel?.prev()">
                <i class="bi bi-chevron-left"></i>
              </button>
              <button type="button" class="hero-nav" :aria-label="t('home.nextSlide')" @click="$refs.carousel?.next()">
                <i class="bi bi-chevron-right"></i>
              </button>
            </div>
          </template>
        </carousel>
      </div>
    </section>

    <!-- 核心功能 -->
    <section class="section features">
      <header class="section-head">
        <h2 class="section-title"><i class="bi bi-stars"></i> {{ t('home.coreFeatures') }}</h2>
        <p class="section-subtitle">{{ t('home.coreFeaturesDesc') }}</p>
      </header>

      <div class="features-grid">
        <article
          v-for="(feature, index) in features"
          :key="index"
          class="feature-card"
          :style="{ '--card-color': feature.color, '--card-rgb': feature.colorRgb }"
          @click="navigateTo(feature.path)"
        >
          <div class="feature-icon" v-html="feature.svg"></div>
          <h3>{{ t(feature.titleKey) }}</h3>
          <p>{{ t(feature.descKey) }}</p>
          <span class="feature-more">
            {{ t('home.details') }}
            <i class="bi bi-arrow-right"></i>
          </span>
        </article>
      </div>
    </section>

    <!-- 热门作物 -->
    <section class="section crops">
      <header class="section-head section-head--row">
        <h2 class="section-title"><i class="bi bi-tags"></i> {{ t('home.hotCrops') }}</h2>
        <a class="view-more" @click="navigateTo('/pests?crop=all')">
          {{ t('home.viewMore') }}
          <i class="bi bi-arrow-right"></i>
        </a>
      </header>

      <div class="crops-grid">
        <article
          v-for="(crop, index) in popularCrops"
          :key="index"
          class="crop-card"
          :style="{ '--crop-bg': crop.bgColor }"
        >
          <div class="crop-main" @click="navigateTo(crop.path)">
            <!-- 第 169 批：图标改为直接渲染 emoji（与「关于」页同一套），不再是图标字体的 class -->
            <div class="crop-icon" aria-hidden="true">{{ crop.icon }}</div>
            <div class="crop-info">
              <!-- 作物名与病害名来自数据库，属"内容"，保持原样 -->
              <h3>{{ crop.name }}</h3>
              <div class="disease-count">{{ crop.diseaseCount }} {{ t('home.cropsUnit') }}</div>
              <div class="disease-tags">
                <span v-for="(disease, i) in crop.commonDiseases" :key="i">{{ disease }}</span>
              </div>
            </div>
          </div>
          <button type="button" class="crop-arrow" :aria-label="t('common.viewCropDiseases')" @click.stop="navigateTo(crop.path)">
            <i class="bi bi-chevron-right"></i>
          </button>
        </article>
      </div>
    </section>
  </div>
</template>


<style scoped>
/* ============================================================
   首页样式（统一使用 assets/theme.css 中的设计变量）
   说明：原文件里这一块是漏写 scoped 的全局样式，且 2000 多行规则中
   存在大量重复定义（.crop-card 定义了 5 次、.feature-card 3 次、
   .section-title 4 次）与已废弃的 .hero-* / .welcome-* 规则。
   这里整体重写为一份自洽的样式，类名与模板一一对应。
   ============================================================ */

.home {
  width: 100%;
  max-width: 1520px;
  margin: 0 auto;
  padding: 0 24px 56px;
  box-sizing: border-box;
}

/* ---------------- 系统公告横幅（第 37 批） ---------------- */
.announce-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  max-width: 1240px;
  margin: 18px auto 0;
  padding: 12px 16px;
  border: 1px solid var(--brand-200, #bfe3cd);
  border-radius: var(--radius, 14px);
  background:
    radial-gradient(80% 120% at 0% 0%, rgba(95, 176, 136, 0.18), transparent 60%),
    linear-gradient(120deg, #f1fbf6, #ffffff);
  box-shadow: var(--shadow-xs, 0 1px 2px rgba(19, 58, 41, 0.05));
}

.announce-icon {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 10px;
  font-size: 14px;
  color: #fff;
  background: linear-gradient(135deg, var(--brand-500, #3d9a68), var(--brand-700, #1f6343));
  box-shadow: 0 6px 14px rgba(25, 79, 55, 0.22);
}

.announce-content {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.announce-content strong {
  font-size: 14px;
  font-weight: 800;
  color: var(--ink-900, #14231c);
}

.announce-text {
  font-size: 13px;
  color: var(--ink-600, #566b60);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  line-clamp: 1;
  -webkit-box-orient: vertical;
}

.announce-close {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--ink-400, #9dada5);
  cursor: pointer;
  transition: all 0.18s ease;
}

.announce-close:hover {
  background: var(--brand-100, #ddf0e5);
  color: var(--brand-700, #1f6343);
}

/* ---------------- 病害预警提示条（第 46 批） ---------------- */
.alert-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  max-width: 1240px;
  margin: 12px auto 0;
  padding: 12px 16px;
  border: 1px solid #f0d9b0;
  border-radius: var(--radius, 14px);
  background:
    radial-gradient(80% 120% at 0% 0%, rgba(217, 146, 47, 0.16), transparent 60%),
    linear-gradient(120deg, #fdf6ea, #ffffff);
  box-shadow: var(--shadow-xs, 0 1px 2px rgba(19, 58, 41, 0.05));
}

.alert-bar.is-high {
  border-color: #f3c9c3;
  background:
    radial-gradient(80% 120% at 0% 0%, rgba(207, 68, 54, 0.14), transparent 60%),
    linear-gradient(120deg, #fdecea, #ffffff);
}

.alert-icon {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 10px;
  font-size: 14px;
  color: #fff;
  background: linear-gradient(135deg, #e0a03c, #b8761b);
  box-shadow: 0 6px 14px rgba(184, 118, 27, 0.22);
}

.alert-bar.is-high .alert-icon {
  background: linear-gradient(135deg, #d9503f, #a32f22);
  box-shadow: 0 6px 14px rgba(163, 47, 34, 0.22);
}

.alert-content {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.alert-content strong {
  font-size: 14px;
  font-weight: 800;
  color: var(--ink-900, #14231c);
}

.alert-text {
  font-size: 13px;
  color: var(--ink-600, #566b60);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  line-clamp: 1;
  -webkit-box-orient: vertical;
}

.alert-more {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 13px;
  border-radius: var(--radius-pill, 999px);
  font-size: 12.5px;
  font-weight: 700;
  color: #8a5a12;
  background: #fff;
  border: 1px solid #f0d9b0;
  text-decoration: none;
  white-space: nowrap;
}

.alert-more:hover {
  background: #fdf3e3;
}

.alert-bar.is-high .alert-more {
  color: #a32f22;
  border-color: #f3c9c3;
}

.alert-bar.is-high .alert-more:hover {
  background: #fdecea;
}

@media (max-width: 640px) {
  .alert-bar {
    flex-wrap: wrap;
  }

  .alert-more {
    margin-left: 44px;
  }
}

/* ---------------- 顶部轮播 ---------------- */
.hero {
  padding: 28px 0 8px;
}

.hero-inner {
  max-width: 1240px;
  margin: 0 auto;
}

.hero-slide {
  padding: 8px;
  height: auto;
}

.hero-card {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 360px;
  padding: 32px;
  border-radius: var(--radius-xl);
  border: 1px solid var(--brand-100, #ddf0e5);
  box-shadow: var(--shadow-sm);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.hero-card::after {
  content: '';
  position: absolute;
  right: -30px;
  top: -50px;
  width: 220px;
  height: 220px;
  border-radius: 50%;
  /* 浅绿渐变底上的装饰圆：白色几乎看不出，改用半透明深绿 */
  background: rgba(31, 99, 67, 0.07);
  pointer-events: none;
}

.hero-card:hover {
  transform: translateY(-5px);
  box-shadow: var(--shadow-lg);
}

.hero-body {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* 浅绿渐变下的文字与图标：全部改用深绿/墨色，保证对比度（原来配的是白字，
   只适用于深色渐变）。这一点与 CSS 变量 --ink-900/--brand-800 保持一致。 */
.hero-icon {
  width: 56px;
  height: 56px;
  margin-bottom: 20px;
  color: var(--brand-700, #1f6343);
}

.hero-icon svg {
  width: 100%;
  height: 100%;
  display: block;
}

.hero-title {
  margin: 0 0 12px;
  font-size: 22px;
  font-weight: 800;
  line-height: 1.35;
  letter-spacing: 0.3px;
  color: var(--brand-900, #123a29);
}

.hero-desc {
  margin: 0 0 18px;
  font-size: 14.5px;
  line-height: 1.75;
  color: var(--ink-700, #3a4d43);
}

.hero-features {
  margin: 0 0 22px;
  padding: 0;
  list-style: none;
}

.hero-features li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--ink-600, #566b60);
}

.hero-features svg {
  flex-shrink: 0;
  margin-top: 2px;
}

.hero-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
  margin-top: auto;
  min-height: 44px;
  padding: 11px 24px;
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  background: var(--brand-600, #2a7f53);
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  transition: background-color var(--dur) var(--ease), transform var(--dur) var(--ease),
    box-shadow var(--dur) var(--ease);
}

.hero-btn:hover {
  background: var(--brand-700, #1f6343);
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgba(31, 99, 67, 0.28);
}

.hero-btn svg {
  transition: transform var(--dur) var(--ease);
}

.hero-btn:hover svg {
  transform: translateX(3px);
}

/* 右下角水印：复用卡片图标（SVG）。浅绿底上不能用白色（会消失），
   改用品牌深绿 + 低不透明度做同色系装饰。 */
.hero-art {
  position: absolute;
  right: -14px;
  bottom: -18px;
  z-index: 1;
  width: 44%;
  max-width: 170px;
  color: var(--brand-700, #1f6343);
  opacity: 0.14;
  pointer-events: none;
}

.hero-art svg {
  display: block;
  width: 100%;
  height: auto;
}

/* 轮播控件 */
.hero-controls {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 18px;
}

.hero-nav {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface);
  color: var(--ink-600);
  font-size: 15px;
  cursor: pointer;
  transition: all var(--dur) var(--ease);
}

.hero-nav:hover {
  background: var(--gradient-brand);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 8px 18px rgba(31, 99, 67, 0.22);
}

:deep(.carousel__pagination-button)::after {
  background: var(--brand-200);
}

:deep(.carousel__pagination-button--active)::after {
  background: var(--brand-600);
}

/* ---------------- 区块通用 ---------------- */
.section {
  padding: 46px 0;
}

.section-head {
  margin-bottom: 32px;
  text-align: center;
}

.section-head--row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  text-align: left;
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 10px;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 0.5px;
  color: var(--ink-900);
}

.section-head--row .section-title {
  margin-bottom: 0;
}

.section-title i {
  color: var(--brand-500);
}

.section-subtitle {
  margin: 0;
  font-size: 14.5px;
  color: var(--ink-500);
}

.view-more {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border: 1px solid var(--brand-300);
  border-radius: var(--radius-pill);
  color: var(--brand-700);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--dur) var(--ease);
}

.view-more:hover {
  background: var(--gradient-brand);
  border-color: transparent;
  color: #fff;
}

/* ---------------- 核心功能 ---------------- */
.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 22px;
}

.feature-card {
  position: relative;
  padding: 30px 24px;
  text-align: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease),
    border-color var(--dur) var(--ease);
}

.feature-card::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(160deg, rgba(var(--card-rgb, 42, 127, 83), 0.09), transparent 60%);
  opacity: 0;
  transition: opacity var(--dur) var(--ease);
  pointer-events: none;
}

.feature-card:hover {
  transform: translateY(-6px);
  box-shadow: var(--shadow-lg);
  border-color: rgba(var(--card-rgb, 42, 127, 83), 0.35);
}

.feature-card:hover::before {
  opacity: 1;
}

.feature-icon {
  position: relative;
  width: 72px;
  height: 72px;
  display: grid;
  place-items: center;
  margin: 0 auto 18px;
  border-radius: 22px;
  background: linear-gradient(135deg, var(--card-color, #2a7f53), rgba(var(--card-rgb, 42, 127, 83), 0.7));
  color: #fff;
  box-shadow: 0 10px 22px rgba(var(--card-rgb, 42, 127, 83), 0.28);
  transition: transform var(--dur) var(--ease);
}

.feature-card:hover .feature-icon {
  transform: scale(1.06) rotate(-3deg);
}

.feature-icon svg {
  width: 34px;
  height: 34px;
}

.feature-card h3 {
  position: relative;
  margin: 0 0 10px;
  font-size: 17px;
  font-weight: 700;
  color: var(--ink-800);
}

.feature-card p {
  position: relative;
  margin: 0 0 18px;
  font-size: 13.5px;
  line-height: 1.75;
  color: var(--ink-500);
}

.feature-more {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--card-color, #2a7f53);
}

.feature-more i {
  transition: transform var(--dur) var(--ease);
}

.feature-card:hover .feature-more i {
  transform: translateX(4px);
}

/* ---------------- 热门作物 ---------------- */
.crops-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 20px;
}

.crop-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 22px 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.crop-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 5px;
  background: var(--crop-bg, var(--brand-200));
}

.crop-card::after {
  content: '';
  position: absolute;
  right: -46px;
  top: -46px;
  width: 140px;
  height: 140px;
  border-radius: 50%;
  background: var(--crop-bg, var(--brand-100));
  opacity: 0.55;
  transition: transform var(--dur) var(--ease);
  pointer-events: none;
}

.crop-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-md);
}

.crop-card:hover::after {
  transform: scale(1.15);
}

.crop-main {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 16px;
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.crop-icon {
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  display: grid;
  place-items: center;
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow-xs);
  /* 第 169 批：这里现在是作物 emoji（与「关于」页同一套），不再是图标字体 */
  font-size: 28px;
  line-height: 1;
  color: var(--brand-700);
}

.crop-info {
  min-width: 0;
}

.crop-info h3 {
  margin: 0 0 4px;
  font-size: 16.5px;
  font-weight: 700;
  color: var(--ink-800);
}

.disease-count {
  margin-bottom: 8px;
  font-size: 12.5px;
  color: var(--ink-500);
}

.disease-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.disease-tags span {
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--ink-50);
  font-size: 12px;
  color: var(--ink-600);
}

.crop-arrow {
  position: relative;
  z-index: 1;
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface);
  color: var(--ink-500);
  cursor: pointer;
  transition: all var(--dur) var(--ease);
}

.crop-card:hover .crop-arrow {
  background: var(--gradient-brand);
  border-color: transparent;
  color: #fff;
}

/* ---------------- 响应式 ---------------- */
@media (max-width: 1024px) {
  .hero-card {
    min-height: 320px;
    padding: 26px;
  }

  .section-title {
    font-size: 22px;
  }
}

@media (max-width: 768px) {
  .home {
    padding: 0 16px 40px;
  }

  .section {
    padding: 32px 0;
  }

  .section-head--row {
    justify-content: flex-start;
  }

  .hero-title {
    font-size: 19px;
  }

  .crops-grid {
    grid-template-columns: 1fr;
  }
}
</style>


