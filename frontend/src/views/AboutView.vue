<template>
  <div class="about-container">
    <div class="text-end mb-4">
      <router-link to="/" class="home-button">
        <i class="bi bi-house-door"></i> {{ t('about.backHome') }}
      </router-link>
    </div>
    <div class="about-header">
      <h1>{{ t('about.title') }}</h1>
      <p>{{ t('about.subtitle') }}</p>
    </div>

    <div class="about-content">
      <!-- 系统介绍 -->
      <section class="about-section">
        <h2>{{ t('about.introTitle') }}</h2>
        <p>{{ t('about.introP1') }}</p>
        <p>{{ t('about.introP2') }}</p>
      </section>

      <!-- 技术特点 -->
      <section class="about-section">
        <h2>{{ t('about.featuresTitle') }}</h2>
        <div class="features-grid">
          <div class="feature-item" v-for="item in featureCards" :key="item.titleKey">
            <div class="feature-icon">{{ item.icon }}</div>
            <h3>{{ t(item.titleKey) }}</h3>
            <p>{{ t(item.descKey) }}</p>
          </div>
        </div>
      </section>

      <!-- 技术栈 -->
      <section class="about-section">
        <h2>{{ t('about.stackTitle') }}</h2>
        <div class="tech-stack">
          <div class="tech-category" v-for="group in stackGroups" :key="group.titleKey">
            <h3>{{ t(group.titleKey) }}</h3>
            <ul>
              <li v-for="item in tl(group.itemsKey)" :key="item">{{ item }}</li>
            </ul>
          </div>
        </div>
      </section>

      <!-- 支持作物 -->
      <section class="about-section">
        <h2>{{ t('about.cropsTitle') }}</h2>
        <div class="crops-grid">
          <div class="crop-item" v-for="crop in supportedCrops" :key="crop.name">
            <div class="crop-icon">{{ crop.icon }}</div>
            <h4>{{ crop.name }}</h4>
            <p>{{ crop.description }}</p>
          </div>
        </div>
      </section>

      <!-- 联系我们 -->
      <section class="about-section">
        <h2>{{ t('about.contactTitle') }}</h2>
        <div class="contact-info">
          <p>{{ t('about.contactDesc') }}</p>
          <div class="contact-item">
            <strong>{{ t('about.contactEmail') }}</strong> support@crop-disease-ai.com
          </div>
          <div class="contact-item">
            <strong>{{ t('about.contactRepo') }}</strong>
            <a href="https://github.com/your-repo/crop-disease-system" target="_blank">
              GitHub Repository
            </a>
          </div>
        </div>
      </section>

      <!-- 版本信息 -->
      <section class="about-section">
        <h2>{{ t('about.versionTitle') }}</h2>
        <div class="version-info">
          <p><strong>{{ t('about.versionCurrent') }}</strong> v1.0.0</p>
          <p><strong>{{ t('about.versionUpdated') }}</strong> {{ t('about.versionUpdatedValue') }}</p>
          <p><strong>{{ t('about.versionPestTypes') }}</strong> {{ t('about.versionPestTypesValue') }}</p>
          <p><strong>{{ t('about.versionCrops') }}</strong> {{ t('about.versionCropsValue') }}</p>
        </div>
      </section>

      <!-- 第 31 批：看完介绍后给一条"接下来去哪儿"的路，页面底部不再空着 -->
      <PageExtras
        icon="fas fa-compass"
        :title="t('about.nextTitle')"
        :subtitle="t('about.nextSubtitle')"
        :items="nextItems"
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
// 第 31 批：页面底部"接下来去哪儿"补充信息区
import PageExtras from '@/components/PageExtras.vue';
// 第 53 批：多语言（t 取文案、tl 取列表型文案）
import { useI18n } from '@/i18n';

const { t, tl } = useI18n();

// 底部"接下来去哪儿"：文案走 i18n，切语言时跟着变
const nextItems = computed(() => [
  {
    icon: 'fas fa-camera',
    title: t('about.nextDetectTitle'),
    text: t('about.nextDetectText'),
    more: t('about.nextDetectMore'),
    to: '/detect',
  },
  {
    icon: 'fas fa-book-open-reader',
    title: t('about.nextWikiTitle'),
    text: t('about.nextWikiText'),
    more: t('about.nextWikiMore'),
    to: '/pests',
  },
  {
    icon: 'fas fa-comments',
    title: t('about.nextForumTitle'),
    text: t('about.nextForumText'),
    more: t('about.nextForumMore'),
    to: '/forum',
  },
  {
    icon: 'fas fa-comment-dots',
    title: t('about.nextFeedbackTitle'),
    text: t('about.nextFeedbackText'),
    more: t('about.nextFeedbackMore'),
    to: '/feedback',
  },
]);

// 技术特点与技术栈：文案改成 i18n key，渲染时翻译
const featureCards = [
  { icon: '🤖', titleKey: 'about.featureAi', descKey: 'about.featureAiDesc' },
  { icon: '📱', titleKey: 'about.featureEasy', descKey: 'about.featureEasyDesc' },
  { icon: '📊', titleKey: 'about.featureAdvice', descKey: 'about.featureAdviceDesc' },
  { icon: '📈', titleKey: 'about.featureHistory', descKey: 'about.featureHistoryDesc' },
];

const stackGroups = [
  { titleKey: 'about.stackFrontend', itemsKey: 'about.stackFrontendItems' },
  { titleKey: 'about.stackBackend', itemsKey: 'about.stackBackendItems' },
  { titleKey: 'about.stackAi', itemsKey: 'about.stackAiItems' },
];

const supportedCrops = computed(() => [
  {
    name: t('home.cropApple'),
    icon: '🍎',
    description: t('about.cropsApple'),
  },
  {
    name: t('home.cropCorn'),
    icon: '🌽',
    description: t('about.cropsCorn'),
  },
  {
    name: t('home.cropGrape'),
    icon: '🍇',
    description: t('about.cropsGrape'),
  },
  {
    name: t('home.cropPotato'),
    icon: '🥔',
    description: t('about.cropsPotato'),
  },
  {
    name: t('home.cropTomato'),
    icon: '🍅',
    description: t('about.cropsTomato'),
  },
  {
    name: t('home.cropStrawberry'),
    icon: '🍓',
    description: t('about.cropsStrawberry'),
  },
  {
    name: t('home.cropPepper'),
    icon: '🫑',
    description: t('about.cropsPepper'),
  },
  {
    name: t('home.cropCitrus'),
    icon: '🍊',
    description: t('about.cropsCitrus'),
  },
  {
    name: t('home.cropPeach'),
    icon: '🍑',
    description: t('about.cropsPeach'),
  },
  {
    name: t('home.cropPumpkin'),
    icon: '🎃',
    description: t('about.cropsPumpkin'),
  },
]);
</script>

<style scoped>
.home-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background-color: var(--brand-600, #2a7f53);
  color: white;
  border-radius: 4px;
  text-decoration: none;
  font-weight: 500;
  transition: all 0.3s ease;
  border: none;
  font-size: 14px;
  margin-bottom: 20px;
}

.home-button:hover {
  background-color: var(--brand-700, #1f6343);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  color: white;
}

.home-button i {
  font-size: 16px;
}
.about-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

.about-header {
  text-align: center;
  margin-bottom: 3rem;
  padding: 3rem 0;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 12px;
}

.about-header h1 {
  font-size: 3rem;
  font-weight: 700;
  margin-bottom: 1rem;
}

.about-header p {
  font-size: 1.2rem;
  opacity: 0.9;
}

.about-content {
  display: flex;
  flex-direction: column;
  gap: 3rem;
}

.about-section {
  background: white;
  padding: 2rem;
  border-radius: 12px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.08);
}

.about-section h2 {
  font-size: 2rem;
  font-weight: 600;
  color: #2c3e50;
  margin-bottom: 1.5rem;
  border-bottom: 3px solid #667eea;
  padding-bottom: 0.5rem;
}

.about-section p {
  font-size: 1.1rem;
  line-height: 1.7;
  color: #555;
  margin-bottom: 1rem;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 2rem;
  margin-top: 2rem;
}

.feature-item {
  text-align: center;
  padding: 1.5rem;
  border-radius: 8px;
  background: #f8f9fa;
  transition: transform 0.3s ease;
}

.feature-item:hover {
  transform: translateY(-5px);
}

.feature-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.feature-item h3 {
  font-size: 1.3rem;
  font-weight: 600;
  color: #2c3e50;
  margin-bottom: 0.5rem;
}

.feature-item p {
  color: #666;
  font-size: 0.95rem;
}

.tech-stack {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 2rem;
  margin-top: 2rem;
}

.tech-category {
  background: #f8f9fa;
  padding: 1.5rem;
  border-radius: 8px;
  border-left: 4px solid #667eea;
}

.tech-category h3 {
  font-size: 1.3rem;
  font-weight: 600;
  color: #2c3e50;
  margin-bottom: 1rem;
}

.tech-category ul {
  list-style: none;
  padding: 0;
}

.tech-category li {
  padding: 0.5rem 0;
  color: #555;
  border-bottom: 1px solid #e9ecef;
}

.tech-category li:last-child {
  border-bottom: none;
}

.crops-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-top: 2rem;
}

.crop-item {
  text-align: center;
  padding: 1.5rem;
  background: #f8f9fa;
  border-radius: 8px;
  transition: transform 0.3s ease;
}

.crop-item:hover {
  transform: translateY(-3px);
}

.crop-icon {
  font-size: 2.5rem;
  margin-bottom: 0.5rem;
}

.crop-item h4 {
  font-size: 1.1rem;
  font-weight: 600;
  color: #2c3e50;
  margin-bottom: 0.5rem;
}

.crop-item p {
  font-size: 0.9rem;
  color: #666;
  line-height: 1.4;
}

.contact-info {
  background: #f8f9fa;
  padding: 1.5rem;
  border-radius: 8px;
  margin-top: 1rem;
}

.contact-item {
  margin: 0.5rem 0;
  color: #555;
}

.contact-item a {
  color: #667eea;
  text-decoration: none;
}

.contact-item a:hover {
  text-decoration: underline;
}

.version-info {
  background: #f8f9fa;
  padding: 1.5rem;
  border-radius: 8px;
  margin-top: 1rem;
}

.version-info p {
  margin: 0.5rem 0;
  color: #555;
}

@media (max-width: 768px) {
  .about-header h1 {
    font-size: 2rem;
  }

  .about-header p {
    font-size: 1rem;
  }

  .features-grid,
  .tech-stack,
  .crops-grid {
    grid-template-columns: 1fr;
  }
}

/* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
.about-container {
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  padding: 8px 24px 48px;
  box-sizing: border-box;
}

.about-header {
  padding: 46px 32px;
  margin-bottom: 26px;
  text-align: center;
  border-radius: var(--radius-xl);
  background: var(--gradient-hero);
  box-shadow: var(--shadow-lg);
}

.about-header h1 {
  margin: 0 0 12px;
  font-size: 32px;
  font-weight: 800;
  letter-spacing: 1px;
  color: #fff;
}

.about-header p {
  max-width: 720px;
  margin: 0 auto;
  font-size: 15px;
  line-height: 1.9;
  color: rgba(255, 255, 255, 0.85);
}

.about-content {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.about-section {
  padding: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.about-section h2 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 18px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
  font-size: 19px;
  font-weight: 700;
  color: var(--brand-700);
}

.features-grid,
.crops-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 18px;
}

.feature-item,
.crop-item {
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-muted);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease),
    border-color var(--dur) var(--ease);
}

.feature-item:hover,
.crop-item:hover {
  transform: translateY(-4px);
  border-color: var(--brand-200);
  box-shadow: var(--shadow-md);
}

.feature-icon,
.crop-icon {
  width: 52px;
  height: 52px;
  display: grid;
  place-items: center;
  margin-bottom: 14px;
  border-radius: 16px;
  background: var(--brand-50);
  color: var(--brand-600);
  font-size: 22px;
}

.feature-item h3,
.crop-item h3 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 700;
  color: var(--ink-800);
}

.feature-item p,
.crop-item p {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.75;
  color: var(--ink-500);
}

.tech-stack {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.tech-category {
  padding: 16px 18px;
  flex: 1 1 220px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-muted);
}

.tech-category h4 {
  margin: 0 0 8px;
  font-size: 14.5px;
  font-weight: 700;
  color: var(--brand-700);
}

.contact-info {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}

.contact-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-muted);
  font-size: 14px;
  color: var(--ink-700);
}

.contact-item i {
  color: var(--brand-600);
  font-size: 16px;
}

.home-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 28px;
  border: none;
  border-radius: var(--radius-pill);
  background: var(--gradient-brand);
  color: #fff;
  font-size: 14.5px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 10px 22px rgba(31, 99, 67, 0.22);
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.home-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 28px rgba(31, 99, 67, 0.28);
}

@media (max-width: 768px) {
  .about-container {
    padding: 0 16px 32px;
  }

  .about-header {
    padding: 30px 20px;
  }

  .about-header h1 {
    font-size: 23px;
  }

  .about-section {
    padding: 20px;
  }
}
</style>
