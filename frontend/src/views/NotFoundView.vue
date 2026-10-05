<template>
  <div class="not-found">
    <el-card class="not-found-card">
      <div class="not-found-content">
        <div class="not-found-icon">
          <el-icon><warning-filled /></el-icon>
        </div>
        <h1>404</h1>
        <h2>{{ t('notFound.title') }}</h2>
        <p>{{ t('notFound.desc') }}</p>
        <el-button type="primary" @click="goHome" class="back-home">
          {{ t('notFound.backHome') }}
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 404 页（第 99 批修复）
 * ----------------------------------------------------------------------------
 * 这里原本**没有引入 i18n**，模板却用了 `t('notFound.title')` ——
 * 于是 404 页自己会在渲染时抛 `TypeError: _ctx.t is not a function`（实测）。
 * 后果特别隐蔽：任何拼错的地址、或指向已下线页面的旧链接，用户看到的不是
 * "404 页面不存在"，而是一片空白 + 控制台报错 —— **连"你走错地方了"都说不出来**。
 *
 * 之所以一直没被发现：`component-wiring.spec.js` 的漏 return 检查有
 * `if (!usesI18n(source)) continue` 这道前置条件 —— 它只检查"用了 useI18n 的组件
 * 有没有返回 t"，而这里**压根没用 useI18n**。该检查已在本批补上这条分支。
 */
import { WarningFilled } from '@element-plus/icons-vue';
import { useRouter } from 'vue-router';
import { useI18n } from '@/i18n';

const router = useRouter();
const { t } = useI18n();

const goHome = () => {
  router.push('/');
};
</script>

<style scoped>
.not-found {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 80vh;
  padding: 20px;
  background-color: #f5f7fa;
}

.not-found-card {
  width: 100%;
  max-width: 500px;
  text-align: center;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.not-found-content {
  padding: 40px 20px;
}

.not-found-icon {
  font-size: 64px;
  color: #f56c6c;
  margin-bottom: 20px;
}

h1 {
  font-size: 72px;
  font-weight: 700;
  color: #1a5f3e;
  margin: 0;
  line-height: 1;
}

h2 {
  font-size: 24px;
  color: #303133;
  margin: 10px 0;
}

p {
  color: #606266;
  margin-bottom: 30px;
  font-size: 16px;
}

.back-home {
  padding: 10px 30px;
  font-size: 16px;
}

/* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
.not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: 40px 24px;
}

.not-found-card {
  width: 100%;
  max-width: 520px;
  padding: 48px 36px;
  text-align: center;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: var(--surface);
  box-shadow: var(--shadow-lg);
}

.not-found-icon {
  font-size: 64px;
  line-height: 1;
  margin-bottom: 18px;
  color: var(--brand-400);
}

.not-found-content h1,
.not-found-content h2 {
  margin: 0 0 12px;
  font-size: 26px;
  font-weight: 800;
  color: var(--ink-900);
}

.not-found-content p {
  margin: 0 0 24px;
  font-size: 14.5px;
  line-height: 1.9;
  color: var(--ink-500);
}

.back-home {
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

.back-home:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 28px rgba(31, 99, 67, 0.28);
}
</style>
