<template>
  <!--
    空状态（第 322 批）

    ## 为什么抽成组件

    用户反馈"空状态只有一行干巴巴的文字"。项目里已有 31 处空状态容器
    （`el-empty` / `empty-line` / `empty-state`），如果每处各画一遍 SVG，
    以后换风格要改 31 个地方。抽成组件后：一处改、全站一致。

    ## 为什么用内联 SVG

    不引图标库、不依赖图片资源：跟着 `currentColor` 走，深色/浅色主题都不会变成黑块；
    也没有额外 HTTP 请求（空状态往往出现在弱网时，这正是最不该再拉图片的时刻）。

    ## 用法

    ```vue
    <EmptyState variant="leaf" :description="t('history.empty')" />
    <EmptyState variant="chat" description="还没有提问记录" />
    <EmptyState variant="image" description="还没有识别记录" action-text="去识别" @action="go" />
    ```
  -->
  <div class="empty-state">
    <svg
      class="empty-illustration"
      viewBox="0 0 120 96"
      width="120"
      height="96"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      stroke-width="2.2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <!-- 叶子（历史/百科类） -->
      <template v-if="variant === 'leaf'">
        <path d="M96 14C58 14 34 30 34 52a20 20 0 0 0 20 20c22 0 42-24 42-58z" />
        <path d="M14 84c12-20 28-32 52-40" />
      </template>

      <!-- 对话气泡（问答/通知类） -->
      <template v-else-if="variant === 'chat'">
        <path d="M20 22h80a8 8 0 0 1 8 8v36a8 8 0 0 1-8 8H52l-18 14v-14H20a8 8 0 0 1-8-8V30a8 8 0 0 1 8-8z" />
        <path d="M34 44h52M34 58h34" />
      </template>

      <!-- 图片/相机（识别/图库类） -->
      <template v-else>
        <rect x="14" y="22" width="92" height="62" rx="8" />
        <circle cx="40" cy="42" r="6" />
        <path d="M20 74l24-22 20 18 14-12 20 16" />
      </template>
    </svg>

    <p v-if="description" class="empty-description">{{ description }}</p>

    <el-button v-if="actionText" class="empty-action" size="small" @click="$emit('action')">
      {{ actionText }}
    </el-button>
  </div>
</template>

<script setup>
defineProps({
  /** leaf | chat | image */
  variant: { type: String, default: 'leaf' },
  description: { type: String, default: '' },
  actionText: { type: String, default: '' },
});

defineEmits(['action']);
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 16px;
  color: var(--ink-300, #b7c2bd);
}

.empty-illustration {
  opacity: 0.85;
}

.empty-description {
  margin: 0;
  font-size: 0.9rem;
  color: var(--ink-400, #8a8f8c);
  text-align: center;
  max-width: 420px;
  line-height: 1.6;
}

.empty-action {
  margin-top: 2px;
}
</style>
