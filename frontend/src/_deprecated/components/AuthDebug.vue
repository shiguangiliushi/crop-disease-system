<template>
  <div class="auth-debug" v-if="showDebug">
    <div class="debug-panel">
      <h3>认证状态调试</h3>
      <div class="debug-info">
        <p><strong>用户:</strong> {{ authStore.user ? authStore.user.username : "未登录" }}</p>
        <p><strong>Token:</strong> {{ authStore.authToken ? authStore.authToken.substring(0, 20) + "..." : "无" }}</p>
        <p><strong>已认证:</strong> {{ authStore.isAuthenticated ? "是" : "否" }}</p>
        <p><strong>本地存储:</strong> {{ localStorageStatus }}</p>
      </div>
      <div class="debug-actions">
        <button @click="testAuth" :disabled="isTesting" class="debug-btn">
          {{ isTesting ? "测试中..." : "测试认证" }}
        </button>
        <button @click="clearAuth" class="debug-btn">清除认证</button>
        <button @click="refreshPage" class="debug-btn">刷新页面</button>
      </div>
      <div v-if="testResult" class="test-result">
        <p><strong>测试结果:</strong> {{ testResult }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const isTesting = ref(false);
const testResult = ref("");
const showDebug = ref(true);

const localStorageStatus = computed(() => {
  const user = localStorage.getItem("user");
  const token = localStorage.getItem("auth_token");
  return `用户: ${user ? "有" : "无"}, Token: ${token ? "有" : "无"}`;
});

const testAuth = async () => {
  isTesting.value = true;
  testResult.value = "";
  
  try {
    const result = await authStore.checkAuth();
    testResult.value = `认证检查结果: ${result ? "成功" : "失败"}`;
  } catch (error) {
    testResult.value = `认证检查错误: ${error.message}`;
  } finally {
    isTesting.value = false;
  }
};

const clearAuth = () => {
  authStore.clearAuth();
  testResult.value = "认证状态已清除";
};

const refreshPage = () => {
  window.location.reload();
};
</script>

<style scoped>
.auth-debug {
  position: fixed;
  top: 80px;
  right: 20px;
  z-index: 1000;
}

.debug-panel {
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1rem;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  max-width: 300px;
}

.debug-panel h3 {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  color: #333;
}

.debug-info p {
  margin: 0.5rem 0;
  font-size: 0.9rem;
  color: #666;
}

.debug-actions {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.debug-btn {
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #f8f9fa;
  cursor: pointer;
  font-size: 0.8rem;
}

.debug-btn:hover {
  background: #e9ecef;
}

.debug-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.test-result {
  margin-top: 1rem;
  padding: 0.5rem;
  background: #f8f9fa;
  border-radius: 4px;
  border-left: 3px solid #409eff;
}

.test-result p {
  margin: 0;
  font-size: 0.9rem;
  color: #495057;
}
</style>
