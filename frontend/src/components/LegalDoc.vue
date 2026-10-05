<template>
  <div class="legal-doc">
    <!-- 返回入口（用户协议 / 隐私政策都只能从页脚进来，此前没有返回按钮，
         只能靠浏览器后退键） -->
    <BackButton />

    <header class="doc-header">
      <h1>{{ title }}</h1>
      <p v-if="subtitle" class="doc-subtitle">{{ subtitle }}</p>
      <p v-if="updatedAt" class="doc-updated">
        <i class="fas fa-clock-rotate-left"></i> {{ t('legal.lastUpdated') }}{{ updatedAt }}
      </p>
    </header>

    <div class="doc-body">
      <!-- 目录 -->
      <aside class="doc-toc">
        <h2>{{ t('legal.toc') }}</h2>
        <ol>
          <li v-for="section in sections" :key="section.id">
            <a :href="`#${section.id}`" @click.prevent="scrollTo(section.id)">{{ section.heading }}</a>
          </li>
        </ol>
      </aside>

      <!-- 正文 -->
      <article class="doc-content">
        <section v-for="section in sections" :id="section.id" :key="section.id" class="doc-section">
          <h2>{{ section.heading }}</h2>
          <p v-for="(paragraph, index) in section.paragraphs || []" :key="`p${index}`">{{ paragraph }}</p>
          <ul v-if="section.items && section.items.length">
            <li v-for="(item, index) in section.items" :key="`i${index}`" v-html="item"></li>
          </ul>
        </section>

        <p class="doc-footer-note">
          {{ t('legal.contactPrefix') }}
          <RouterLink to="/feedback">{{ t('legal.feedback') }}</RouterLink>
          {{ t('legal.contactSuffix') }}
        </p>
      </article>
    </div>
  </div>
</template>

<script>
/**
 * 法律/说明类文档版式（用户协议、隐私政策共用）
 *
 * 第 26 批新增：把版式与目录抽成组件，两个页面只维护"内容数据"。
 * 第 71 批：正文内容改由页面按当前语言生成，组件内的固定文案走 i18n。
 * 第 87 批：补返回按钮（用户协议 / 隐私政策此前进去就出不来了）。
 */
import { useI18n } from '@/i18n';
import BackButton from '@/components/BackButton.vue';

export default {
  name: 'LegalDoc',
  components: { BackButton },
  props: {
    title: { type: String, required: true },
    subtitle: { type: String, default: '' },
    updatedAt: { type: String, default: '' },
    // [{ id, heading, paragraphs: [], items: [] }]
    sections: { type: Array, default: () => [] },
  },
  setup() {
    const { t } = useI18n();
    const scrollTo = (id) => {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
    return { scrollTo, t };
  },
};
</script>

<style scoped>
.legal-doc {
  max-width: 1040px;
  margin: 0 auto;
  padding: 28px 20px 48px;
}

.doc-header {
  border-bottom: 1px solid #eef0f3;
  padding-bottom: 18px;
  margin-bottom: 22px;
}

.doc-header h1 {
  margin: 0 0 8px;
  font-size: 26px;
  font-weight: 800;
  color: var(--ink-900, #1f2d3d);
}

.doc-subtitle {
  margin: 0 0 6px;
  font-size: 14px;
  color: var(--ink-600, #4b5563);
}

.doc-updated {
  margin: 0;
  font-size: 12px;
  color: var(--ink-400, #9aa4b2);
}

.doc-body {
  display: flex;
  gap: 28px;
  align-items: flex-start;
}

.doc-toc {
  position: sticky;
  top: 84px;
  flex: 0 0 208px;
  padding: 16px 18px;
  background: #fff;
  border: 1px solid #eef0f3;
  border-radius: 12px;
}

.doc-toc h2 {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 700;
  color: var(--ink-500, #7a8699);
  letter-spacing: 0.04em;
}

.doc-toc ol {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.9;
}

.doc-toc a {
  color: var(--ink-700, #374151);
  text-decoration: none;
}

.doc-toc a:hover {
  color: var(--brand-700, #2f7d4f);
  text-decoration: underline;
}

.doc-content {
  flex: 1;
  min-width: 0;
  padding: 22px 26px;
  background: #fff;
  border: 1px solid #eef0f3;
  border-radius: 12px;
}

.doc-section + .doc-section {
  margin-top: 22px;
  padding-top: 18px;
  border-top: 1px dashed #eef0f3;
}

.doc-section h2 {
  margin: 0 0 10px;
  font-size: 17px;
  font-weight: 700;
  color: var(--brand-800, #245c3d);
}

.doc-section p {
  margin: 0 0 10px;
  font-size: 14px;
  line-height: 1.85;
  color: var(--ink-700, #374151);
}

.doc-section ul {
  margin: 0 0 8px;
  padding-left: 20px;
  font-size: 14px;
  line-height: 1.9;
  color: var(--ink-700, #374151);
}

.doc-footer-note {
  margin: 26px 0 0;
  padding-top: 16px;
  border-top: 1px solid #eef0f3;
  font-size: 13px;
  color: var(--ink-500, #7a8699);
}

.doc-footer-note a {
  color: var(--brand-700, #2f7d4f);
}

@media (max-width: 860px) {
  .doc-body {
    flex-direction: column;
  }

  .doc-toc {
    position: static;
    width: 100%;
    flex: none;
  }
}
</style>
