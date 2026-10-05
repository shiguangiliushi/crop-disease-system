<template>
  <div class="auth-container">
    <div class="auth-forms">
      <!-- 登录表单 -->
      <div class="login-section" :class="{ 'active': activeView === 'login' }">
        <div class="form-container">
          <div class="form-header">
            <h1>欢迎回来</h1>
            <p>登录您的账户以使用完整功能</p>
          </div>
          
          <!-- 切换到注册表单的链接 -->
          <div class="switch-form" v-if="activeView === 'login'">
            还没有账号？
            <a href="#" @click.prevent="switchToRegister">立即注册</a>
          </div>
          
          <form @submit.prevent="handleLogin" class="auth-form">
            <div class="form-group">
              <label for="login-username">用户名</label>
              <div class="input-wrapper">
                <i class="fas fa-user"></i>
                <input 
                  type="text" 
                  id="login-username"
                  v-model="loginData.username"
                  :disabled="loginLoading"
                  placeholder="请输入用户名"
                  required
                />
              </div>
            </div>
            
            <div class="form-group">
              <label for="login-password">密码</label>
              <div class="input-wrapper">
                <i class="fas fa-lock"></i>
                <input 
                  type="password" 
                  id="login-password"
                  v-model="loginData.password"
                  :disabled="loginLoading"
                  placeholder="请输入密码"
                  required
                />
              </div>
            </div>
            
            <div class="form-actions">
              <div class="remember-me">
                <input 
                  type="checkbox" 
                  id="rememberMe"
                  v-model="loginData.rememberMe"
                  :disabled="loginLoading"
                />
                <label for="rememberMe">记住我</label>
              </div>
              
              <button type="submit" :disabled="loginLoading" class="submit-btn">
                <span v-if="loginLoading" class="spinner"></span>
                {{ loginLoading ? '登录中...' : '登录' }}
              </button>
            </div>
            
            <div v-if="loginError" class="error-message">
              <i class="fas fa-exclamation-circle"></i>
              {{ loginError }}
            </div>
          </form>
        </div>
      </div>
      
      <!-- 注册表单 -->
      <div class="register-section" :class="{ 'active': activeView === 'register' }">
        <div class="form-container">
          <div class="form-header">
            <h1>创建账户</h1>
            <p>加入我们，开始使用智能病害识别系统</p>
          </div>
          
          <!-- 切换到登录表单的链接 -->
          <div class="switch-form" v-if="activeView === 'register'">
            已有账号？
            <a href="#" @click.prevent="switchToLogin">立即登录</a>
          </div>
          
          <form @submit.prevent="handleRegister" class="auth-form">
            <div class="form-group">
              <label for="register-username">用户名</label>
              <div class="input-wrapper">
                <i class="fas fa-user"></i>
                <input 
                  type="text" 
                  id="register-username"
                  v-model="registerData.username"
                  :disabled="registerLoading"
                  placeholder="请输入用户名"
                  required
                />
              </div>
            </div>
            
            <div class="form-group">
              <label for="register-password">密码</label>
              <div class="input-wrapper">
                <i class="fas fa-lock"></i>
                <input 
                  type="password" 
                  id="register-password"
                  v-model="registerData.password"
                  :disabled="registerLoading"
                  placeholder="请输入密码（至少6位）"
                  required
                />
              </div>
            </div>
            
            <div class="form-group">
              <label for="confirm-password">确认密码</label>
              <div class="input-wrapper">
                <i class="fas fa-lock"></i>
                <input 
                  type="password" 
                  id="confirm-password"
                  v-model="registerData.confirmPassword"
                  :disabled="registerLoading"
                  placeholder="请再次输入密码"
                  required
                />
              </div>
              <div v-if="passwordMismatch" class="error-text">
                两次输入的密码不一致
              </div>
            </div>
            
            <div class="form-actions">
              <button 
                type="submit" 
                :disabled="registerLoading || passwordMismatch" 
                class="submit-btn"
              >
                <span v-if="registerLoading" class="spinner"></span>
                {{ registerLoading ? '注册中...' : '注册' }}
              </button>
            </div>
            
            <div v-if="registerError" class="error-message">
              <i class="fas fa-exclamation-circle"></i>
              {{ registerError }}
            </div>
          </form>
        </div>
      </div>
    </div>
    
    <div class="back-home">
      <router-link to="/">
        <i class="fas fa-home"></i> 返回首页
      </router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuthStore } from '@/stores/auth.js';

const props = defineProps({
  defaultView: {
    type: String,
    default: 'login',
    validator: (value) => ['login', 'register'].includes(value)
  }
});

const route = useRoute();
const activeView = ref(props.defaultView);

// 监听路由变化，更新当前激活的视图
watch(() => route.name, (newRouteName) => {
  if (newRouteName === 'login') {
    activeView.value = 'login';
  } else if (newRouteName === 'register') {
    activeView.value = 'register';
  }
}, { immediate: true });

const router = useRouter();
const authStore = useAuthStore();

// 切换到注册表单
const switchToRegister = () => {
  activeView.value = 'register';
  router.push({ name: 'register' });
};

// 切换到登录表单
const switchToLogin = () => {
  activeView.value = 'login';
  router.push({ name: 'login' });
};

// 登录相关状态
const loginData = ref({
  username: '',
  password: '',
  rememberMe: false
});

const loginLoading = ref(false);
const loginError = ref('');

// 注册相关状态
const registerData = ref({
  username: '',
  password: '',
  confirmPassword: '',
  email: ''
});

const registerLoading = ref(false);
const registerError = ref('');

// 计算属性：密码是否匹配
const passwordMismatch = computed(() => {
  return registerData.value.password && 
         registerData.value.confirmPassword && 
         registerData.value.password !== registerData.value.confirmPassword;
});

// 处理登录
const handleLogin = async () => {
  if (loginLoading.value) return;
  
  loginError.value = '';
  loginLoading.value = true;
  
  try {
    await authStore.login({
      username: loginData.value.username,
      password: loginData.value.password,
      remember: loginData.value.rememberMe
    }, router);
    
    // 登录成功后跳转
    router.push('/');
  } catch (error) {
    console.error('Login error:', error);
    if (error.response?.data?.detail) {
      loginError.value = error.response.data.detail;
    } else if (error.message) {
      loginError.value = error.message;
    } else {
      loginError.value = '登录失败，请检查网络连接或稍后再试。';
    }
  } finally {
    loginLoading.value = false;
  }
};

// 处理注册
const handleRegister = async () => {
  if (registerLoading.value || passwordMismatch.value) return;
  
  // 前端验证
  if (!registerData.value.username.trim()) {
    registerError.value = '用户名不能为空！';
    return;
  }
  
  if (registerData.value.password.length < 6) {
    registerError.value = '密码长度至少需要6位';
    return;
  }
  
  registerError.value = '';
  registerLoading.value = true;
  
  try {
    await authStore.register({
      username: registerData.value.username,
      password: registerData.value.password,
      email: registerData.value.email
    });
    
    // 注册成功提示并跳转到登录
    alert('注册成功！请登录您的账户。');
    // 自动填充登录表单
    loginData.value.username = registerData.value.username;
    loginData.value.password = '';
    // 清空注册表单
    registerData.value = {
      username: '',
      password: '',
      confirmPassword: '',
      email: ''
    };
  } catch (error) {
    console.error('Register error:', error);
    if (error.response?.data?.detail) {
      registerError.value = error.response.data.detail;
    } else if (error.response?.data) {
      registerError.value = Object.values(error.response.data).join(' ');
    } else if (error.message) {
      registerError.value = error.message;
    } else {
      registerError.value = '注册失败，请检查网络连接或稍后再试。';
    }
  } finally {
    registerLoading.value = false;
  }
};
</script>

<style scoped>
.auth-container {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 2rem;
  position: relative;
}

.auth-forms {
  display: flex;
  flex-direction: column;
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  width: 100%;
  max-width: 450px;
  position: relative;
}

.login-section,
.register-section {
  width: 100%;
  padding: 2rem;
  position: relative;
  opacity: 0.6;
  transition: all 0.3s ease;
}

.login-section {
  border-bottom: 1px solid #ecf0f1;
}

.login-section.active,
.register-section.active {
  opacity: 1;
}

.switch-form {
  text-align: center;
  margin: 1rem 0;
  color: #7f8c8d;
  font-size: 0.95rem;
}

.switch-form a {
  color: #667eea;
  text-decoration: none;
  font-weight: 500;
  margin-left: 0.25rem;
  transition: color 0.2s ease;
}

.switch-form a:hover {
  color: #5a6fd8;
  text-decoration: underline;
}

/* 移除分隔线，因为现在使用边框分隔 */

.divider span {
  background: white;
  color: #95a5a6;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #ecf0f1;
  font-size: 0.9rem;
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.form-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.form-header {
  text-align: center;
  margin-bottom: 2rem;
}

.form-header h1 {
  font-size: 1.75rem;
  font-weight: 700;
  color: #2c3e50;
  margin-bottom: 0.5rem;
}

.form-header p {
  color: #7f8c8d;
  font-size: 0.95rem;
}

.auth-form {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.form-group {
  margin-bottom: 1.25rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 600;
  color: #2c3e50;
  font-size: 0.9rem;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.input-wrapper i {
  position: absolute;
  left: 1rem;
  color: #95a5a6;
  font-size: 1rem;
}

.input-wrapper input {
  width: 100%;
  padding: 0.75rem 1rem 0.75rem 2.5rem;
  border: 2px solid #ecf0f1;
  border-radius: 8px;
  font-size: 0.95rem;
  transition: all 0.3s ease;
  background: #f8f9fa;
}

.input-wrapper input:focus {
  outline: none;
  border-color: #667eea;
  background: white;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.input-wrapper input:disabled {
  background: #f1f2f6;
  cursor: not-allowed;
}

.form-actions {
  margin-top: 1.5rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.remember-me {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  color: #5c6b7b;
}

.remember-me input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.submit-btn {
  width: 100%;
  padding: 0.875rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(102, 126, 234, 0.3);
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  transform: none;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid transparent;
  border-top: 2px solid white;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.error-message {
  background: #fee;
  color: #e74c3c;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  margin-top: 1rem;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid #fadbd8;
}

.error-text {
  color: #e74c3c;
  font-size: 0.8rem;
  margin-top: 0.25rem;
  padding-left: 0.25rem;
}

.back-home {
  margin-top: 1.5rem;
  text-align: center;
}

.back-home a {
  color: white;
  text-decoration: none;
  font-size: 0.95rem;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  transition: opacity 0.3s ease;
}

.back-home a:hover {
  opacity: 0.9;
  text-decoration: underline;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .auth-forms {
    flex-direction: column;
    max-width: 450px;
  }
  
  .login-section,
  .register-section {
    padding: 2rem;
  }
  
  .divider {
    width: 100%;
    height: 1px;
    margin: 0;
  }
  
  .divider span {
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
  }
}

@media (max-width: 480px) {
  .auth-container {
    padding: 1rem;
  }
  
  .login-section,
  .register-section {
    padding: 1.5rem;
  }
  
  .form-header h1 {
    font-size: 1.5rem;
  }
  
  .form-header p {
    font-size: 0.9rem;
  }
}
</style>
