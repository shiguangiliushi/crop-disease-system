<template>
  <div class="help-page">
    <!-- 返回入口（页脚进来的二级页面，此前只能靠浏览器后退键） -->
    <BackButton class="help-back" />

    <header class="help-header">
      <h1><i class="fas fa-circle-question"></i> {{ t('help.title') }}</h1>
      <p class="subtitle">{{ t('help.subtitle') }}</p>
      <div class="help-search">
        <el-input
          v-model="keyword"
          :placeholder="t('help.searchPlaceholder')"
          clearable
        >
          <template #prefix><i class="fas fa-search"></i></template>
        </el-input>
      </div>
    </header>

    <!-- {{ t('help.quickStart') }} -->
    <section class="quick-start">
      <h2>{{ t('help.quickStart') }}</h2>
      <div class="start-grid">
        <RouterLink
          v-for="step in quickStart"
          :key="step.to"
          :to="step.to"
          class="start-card"
        >
          <span class="start-icon"><i :class="step.icon"></i></span>
          <h3>{{ step.title }}</h3>
          <p>{{ step.desc }}</p>
        </RouterLink>
      </div>
    </section>

    <!-- {{ t('help.faq') }} -->
    <section class="faq-section">
      <div class="faq-head">
        <h2>{{ t('help.faq') }}</h2>
        <el-radio-group v-model="activeGroup" size="small">
          <el-radio-button value="all">{{ t('help.all') }}</el-radio-button>
          <el-radio-button v-for="group in faqGroups" :key="group.key" :value="group.key">
            {{ group.title }}
          </el-radio-button>
        </el-radio-group>
      </div>

      <el-empty v-if="filteredGroups.length === 0" :description="t('help.emptySearch')" />

      <div v-for="group in filteredGroups" :key="group.key" class="faq-group">
        <h3 class="faq-group-title"><i :class="group.icon"></i> {{ group.title }}</h3>
        <el-collapse>
          <el-collapse-item v-for="(item, index) in group.items" :key="index" :title="item.q">
            <p class="faq-answer" v-html="item.a"></p>
          </el-collapse-item>
        </el-collapse>
      </div>
    </section>

    <!-- 还没解决 -->
    <section class="help-footer">
      <div class="footer-card">
        <div>
          <h3>{{ t('help.noAnswer') }}</h3>
          <p>{{ t('help.noAnswerDesc') }}</p>
        </div>
        <div class="footer-actions">
          <RouterLink to="/feedback">
            <el-button type="primary"><i class="fas fa-comment-dots"></i> {{ t('help.goFeedback') }}</el-button>
          </RouterLink>
          <a href="mailto:contact@cropcare.com">
            <el-button plain><i class="fas fa-envelope"></i> {{ t('help.emailUs') }}</el-button>
          </a>
        </div>
      </div>
    </section>
  </div>
</template>

<script>
/**
 * 帮助中心（第 26 批新增；页脚的原「帮助中心」是一个 href="#" 的死链）
 *
 * FAQ 全部按系统**真实行为**撰写（上传限制、记录删除、草稿可见性、收藏入口、
 * 改密码后旧登录失效、下架新闻对普通用户不可见等），并可从搜索结果直达功能页。
 *
 * 第 79 批修复两件事：
 *   ① **页面一直是坏的**：这是 Options API 组件，模板里调用 `t(...)`，
 *      但 `setup()` 的 return 里没有 `t` → 渲染时抛 `_ctx.t is not a function`，
 *      整页内容渲染不出来（全站中文字符审计因为"内容没渲染"而只看到页脚，
 *      差点把这个 bug 当成"没有中文"放过去）。
 *   ② 正文（快速上手 + 5 组 FAQ，共 20 问答）此前**写死在下面的 script 里**，
 *      只有中文。现在改从 i18n 取（`tl()` 支持数组型文案），中英各一份。
 */
import { ref, computed } from 'vue';
import { useI18n } from '@/i18n';  // 第 79 批
import BackButton from '@/components/BackButton.vue';  // 第 87 批：返回按钮

export default {
  name: 'HelpView',
  components: { BackButton },
  setup() {
    const { t, tl } = useI18n();
    const keyword = ref('');
    const activeGroup = ref('all');

    // 第 79 批：文案来自 i18n（原来是写死的中文常量）
    const quickStart = computed(() => tl('help.quickStartSteps'));
    const faqGroups = computed(() => tl('help.faqGroups'));

    const matchGroup = (group) => {
      const kw = keyword.value.trim().toLowerCase();
      if (!kw) return group;
      const items = group.items.filter(
        (item) => item.q.toLowerCase().includes(kw) || item.a.toLowerCase().includes(kw),
      );
      return items.length ? { ...group, items } : null;
    };

    const filteredGroups = computed(() => {
      const groups = activeGroup.value === 'all'
        ? faqGroups.value
        : faqGroups.value.filter((group) => group.key === activeGroup.value);
      return groups.map(matchGroup).filter(Boolean);
    });

    // 第 79 批修复：模板里用了 t(...)，Options API **必须**把 t 放进 return，
    // 否则渲染时抛 `_ctx.t is not a function`，整页内容出不来（此前就是这样）。
    return { t, quickStart, faqGroups, keyword, activeGroup, filteredGroups };
  },
};
</script>

<style scoped>
.help-page {
  /* 第 32 批：`.main-content` 是 flex + align-items:center，只写 max-width 会被
     按内容收缩（实测 712px，而这里写的是 1000px），两侧白留一大片。
     补 width:100% 才会真正吃满 max-width。 */
  width: 100%;
  max-width: 1000px;
  margin: 0 auto;
  padding: 28px 20px 48px;
}

.help-header {
  text-align: center;
  margin-bottom: 26px;
}

/* 返回按钮：页头是居中的，这里必须显式左对齐（.main-content 是 flex +
   align-items:center，不写 align-self 会被居中到页面中间）—— 第 87 批 */
.help-back {
  align-self: flex-start;
  margin-bottom: 4px;
}

.help-header h1 {
  margin: 0 0 8px;
  font-size: 26px;
  font-weight: 800;
  color: var(--ink-900, #1f2d3d);
}

.subtitle {
  margin: 0 0 16px;
  font-size: 14px;
  color: var(--ink-500, #7a8699);
}

.help-search {
  max-width: 460px;
  margin: 0 auto;
}

.quick-start h2,
.faq-section h2 {
  font-size: 18px;
  font-weight: 800;
  color: var(--ink-900, #1f2d3d);
  margin: 0 0 14px;
}

.start-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
  margin-bottom: 30px;
}

.start-card {
  display: block;
  padding: 18px;
  background: #fff;
  border: 1px solid #eef0f3;
  border-radius: 12px;
  text-decoration: none;
  color: inherit;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.start-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 22px rgba(0, 0, 0, 0.07);
}

.start-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--brand-50, #eef7f1);
  color: var(--brand-700, #2f7d4f);
  font-size: 18px;
  margin-bottom: 10px;
}

.start-card h3 {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 700;
  color: var(--ink-800, #2c3e50);
}

.start-card p {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--ink-500, #7a8699);
}

.faq-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.faq-group {
  margin-bottom: 18px;
}

.faq-group-title {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 700;
  color: var(--brand-800, #245c3d);
}

.faq-answer {
  margin: 0;
  font-size: 14px;
  line-height: 1.85;
  color: var(--ink-700, #374151);
}

.help-footer {
  margin-top: 28px;
}

.footer-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 20px 22px;
  border-radius: 14px;
  background: linear-gradient(135deg, #eef7f1, #f7fbf8);
  border: 1px solid var(--brand-100, #d8ecdf);
}

.footer-card h3 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 800;
  color: var(--brand-800, #245c3d);
}

.footer-card p {
  margin: 0;
  font-size: 13px;
  color: var(--ink-600, #4b5563);
}

.footer-actions {
  display: flex;
  gap: 10px;
}
</style>
