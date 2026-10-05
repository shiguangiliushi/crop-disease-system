<template>
  <!--
    补充信息区（第 31 批）
    ------------------------------------------------------------------
    背景：用户反馈"所有页面空白的地方还是太多了，让系统别看起来太空"。
    各业务页面正文往往只有一张卡片，下面就是一大片空白（App.vue 给
    .main-content 设了 min-height，短页面会把这块撑开）。

    这个组件用来在页面底部统一补一块**有用**的内容：
    使用小知识 / 快捷入口 / 相关功能，而不是纯粹的占位装饰。
    页面只需要传 items，文案尽量写"能帮到用户"的实话。

    用法：
      <PageExtras
        icon="fas fa-camera"
        title="识别流程与拍摄建议"
        subtitle="拍得清楚，识别更准"
        :items="[{ icon: 'fas fa-x', title: '标题', text: '说明', more: '去看看', to: '/x' }]"
      />
  -->
  <section class="page-extras">
    <header class="page-extras-head">
      <span class="page-extras-head-icon"><i :class="icon"></i></span>
      <div>
        <h2>{{ title }}</h2>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
    </header>

    <div class="page-extras-grid">
      <component
        :is="item.to ? 'a' : 'div'"
        v-for="(item, index) in items"
        :key="index"
        class="extra-card"
        :class="{ 'is-link': item.to }"
        @click="item.to && go(item.to)"
      >
        <span class="extra-card-icon"><i :class="item.icon"></i></span>
        <h3>{{ item.title }}</h3>
        <p>{{ item.text }}</p>
        <span v-if="item.more && item.to" class="extra-card-more">
          {{ item.more }} <i class="fas fa-arrow-right"></i>
        </span>
      </component>
    </div>
  </section>
</template>

<script>
import { useRouter } from 'vue-router';

export default {
  name: 'PageExtras',
  props: {
    /** Font Awesome 类名，如 'fas fa-camera' */
    icon: { type: String, default: 'fas fa-circle-info' },
    title: { type: String, required: true },
    subtitle: { type: String, default: '' },
    /**
     * 卡片列表：{ icon, title, text, more?, to? }
     * `to` 存在时整块卡片可点击并跳转（内部用 router.push，避免整页刷新）
     */
    items: { type: Array, default: () => [] },
  },
  setup() {
    const router = useRouter();
    const go = (path) => router.push(path);
    return { go };
  },
};
</script>
