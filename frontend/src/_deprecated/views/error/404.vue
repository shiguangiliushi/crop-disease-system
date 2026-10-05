<template>
  <div class="error-page error-404">
    <div class="error-content">
      <div class="error-illustration">
        <img src="@/assets/images/404.svg" alt="404" class="illustration">
      </div>
      <h1 class="error-code">404</h1>
      <h2 class="error-message">页面未找到</h2>
      <p class="error-desc">抱歉，您访问的页面不存在或已被移除</p>
      <div class="error-actions">
        <el-button type="primary" @click="goBack">返回上一页</el-button>
        <el-button @click="goHome">返回首页</el-button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'NotFound',
  methods: {
    goBack() {
      this.$router.go(-1);
    },
    goHome() {
      this.$router.push('/');
    }
  }
};
</script>

<style scoped>
.error-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background-color: #f5f7fa;
  text-align: center;
  padding: 20px;
}

.error-content {
  max-width: 600px;
  padding: 40px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.error-illustration {
  margin-bottom: 24px;
}

.illustration {
  max-width: 100%;
  height: auto;
  max-height: 200px;
}

.error-code {
  font-size: 72px;
  font-weight: 700;
  color: #909399;
  margin: 0 0 16px;
}

.error-message {
  font-size: 24px;
  color: #303133;
  margin: 0 0 16px;
}

.error-desc {
  font-size: 16px;
  color: #606266;
  margin-bottom: 32px;
}

.error-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
}

@media (max-width: 768px) {
  .error-content {
    padding: 24px;
  }
  
  .error-code {
    font-size: 60px;
  }
  
  .error-message {
    font-size: 20px;
  }
  
  .error-desc {
    font-size: 14px;
  }
  
  .error-actions {
    flex-direction: column;
    gap: 12px;
  }
  
  .error-actions .el-button {
    width: 100%;
  }
}
</style>
