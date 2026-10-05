<script setup>
import { ref, onMounted } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth.js';
import ConsoleAuthShell from '@/components/ConsoleAuthShell.vue';
import { useI18n } from '@/i18n';  // 第 53 批：多语言
// 第 101 批：冷静期内取消注销 + 统一错误文案
import { ElMessage } from 'element-plus';
import { cancelMyDeletion } from '@/api/account';
import { formatApiError } from '@/api/http';

const { t } = useI18n();

const username = ref('');
const password = ref('');
const rememberMe = ref(false);
const showPassword = ref(false);
const errorMessage = ref('');
const isLoading = ref(false);
const authStore = useAuthStore();
const router = useRouter();
const route = useRoute();

// ============================================================================
// 第 84 批：显示"为什么被弹回登录页"
// ----------------------------------------------------------------------------
// 路由守卫会把未登录访问受保护页面的人重定向到 /login?reason=loginRequired，
// 但登录页从来没读过这个参数 —— 用户只看到登录框，不知道刚才发生了什么。
// 这里**只认原因码**（不做"把 query 文本直接贴出来"）：query 是用户可以随手改的，
// 直接渲染等于给钓鱼文案留了一个展示位。
// ============================================================================
const LOGIN_REASON_KEYS = {
  loginRequired: 'msg.loginRequired',
  sessionExpired: 'history.sessionExpired',
};

// 用户名建议列表
const usernameSuggestions = ref([]);
const showSuggestions = ref(false);

// ============================================================================
// 第 35 批安全修复：**不再把密码存进 localStorage**
// ----------------------------------------------------------------------------
// 原来这里的 savePassword()/loadPassword() 会把明文密码写进
// `localStorage.saved_passwords`（形如 {"admin":"123456"}），勾选"记住密码"就执行：
//   · localStorage 是明文、同源脚本可任意读取 —— 一旦页面被注入脚本（XSS）或
//     用户共用电脑，密码直接泄露；
//   · 明文密码还会被带到浏览器同步/备份里。
// 现在的做法：
//   · "记住我"只表示**记住登录状态**（持久化 token，由 auth store 负责）；
//   · 账号名仍然记在本地（方便下次选择登录账号），但绝不记密码；
//   · 密码交给浏览器自己的密码管理器（autocomplete="current-password" 已经就位）；
//   · 进页面时顺手**清掉历史遗留的明文密码**。
// ============================================================================
const LEGACY_PASSWORD_KEY = 'saved_passwords';

/** 清掉早期版本遗留的明文密码（升级后第一次打开登录页即执行） */
const purgeLegacySavedPasswords = () => {
  try {
    if (localStorage.getItem(LEGACY_PASSWORD_KEY) !== null) {
      localStorage.removeItem(LEGACY_PASSWORD_KEY);
      console.warn('[安全] 已清除本地保存的明文密码（legacy saved_passwords）');
    }
  } catch (error) {
    console.error('清除历史明文密码失败:', error);
  }
};

// 获取用户名建议列表
const getUsernameSuggestions = () => {
  try {
    // 获取所有登录过的用户名（不管是否记住密码）
    const allUsernames = JSON.parse(localStorage.getItem('all_usernames') || '[]');
    const lastUsername = localStorage.getItem('last_username');

    // 将最后登录的用户名放在第一位
    let usernames = [...allUsernames];
    if (lastUsername && usernames.includes(lastUsername)) {
      usernames.splice(usernames.indexOf(lastUsername), 1);
      usernames.unshift(lastUsername);
    }

    return usernames;
  } catch (error) {
    console.error('Failed to get username suggestions:', error);
    return [];
  }
};

// 显示用户名建议
const showUsernameSuggestions = () => {
  const suggestions = getUsernameSuggestions();
  if (suggestions.length > 0) {
    usernameSuggestions.value = suggestions;
    showSuggestions.value = true;
  }
};

// 隐藏用户名建议
const hideUsernameSuggestions = () => {
  setTimeout(() => {
    showSuggestions.value = false;
  }, 200); // 延迟隐藏，让用户有时间点击建议
};

// 选择用户名建议
const selectUsername = (selectedUsername) => {
  username.value = selectedUsername;
  showSuggestions.value = false;
  onUsernameChange(); // 自动填充密码（如果有的话）
};

// 用户名变化时：只恢复「记住我」偏好，**绝不回填密码**
const onUsernameChange = () => {
  if (!username.value) return;
  // 只有用户之前明确勾选过"记住我"时才自动勾选（密码请交给浏览器密码管理器）
  rememberMe.value = localStorage.getItem(`remember_me_${username.value}`) === 'true';
};

// 页面加载时恢复上次登录的用户名，并清理历史遗留的明文密码
onMounted(() => {
  purgeLegacySavedPasswords();

  // 第 84 批：把路由守卫带过来的"原因码"翻成当前语言显示
  const reasonKey = LOGIN_REASON_KEYS[route.query.reason];
  if (reasonKey) errorMessage.value = t(reasonKey);

  const lastUsername = localStorage.getItem('last_username');
  if (lastUsername) {
    username.value = lastUsername;
    onUsernameChange();
  }
});

const handleLogin = async () => {
  if (isLoading.value) return;

  errorMessage.value = '';
  isLoading.value = true;

  try {
    await authStore.login(
      {
        username: username.value,
        password: password.value,
        remember: rememberMe.value,
      },
      router,
    );

    // 登录成功后只保存**账号名**（用于下次快速选择），密码交给浏览器密码管理器
    localStorage.setItem('last_username', username.value);

    // 保存所有登录过的用户名（不管是否记住登录状态）
    try {
      const allUsernames = JSON.parse(localStorage.getItem('all_usernames') || '[]');
      if (!allUsernames.includes(username.value)) {
        allUsernames.push(username.value);
        localStorage.setItem('all_usernames', JSON.stringify(allUsernames));
      }
    } catch (error) {
      console.error('Failed to save username to all_usernames:', error);
    }

    // 保存"记住我"的选择（仅登录状态，不涉及密码）
    localStorage.setItem(`remember_me_${username.value}`, rememberMe.value.toString());

    // 登录成功后的重定向由 store 处理
  } catch (error) {
    console.error('Login error:', error);
    // 第 101 批：注销冷静期 —— 密码是对的，但账号已停用。
    // 这里必须给一条**出路**（"取消注销"），否则用户只会看到"无法登录"，
    // 而 15 天冷静期就白设了：没人知道还能反悔。
    //
    // ⚠️ 注意读的是 `error.code` 而不是 `error.response.data.code`：
    //    authStore.login 会把 axios error 包成普通 Error（只保留文案），
    //    响应体里的 code 由它转挂到 error.code 上（见 stores/auth.js）。
    pendingDeletion.value = error?.code === 'account_pending_deletion'
      ? { message: error.message || '', daysLeft: error.daysLeft }
      : null;

    errorMessage.value = error?.message || t('auth.networkError');
  } finally {
    isLoading.value = false;
  }
};

// ==========================================================================
// 第 101 批：取消注销（冷静期内账号登不上，所以入口在登录页）
// ==========================================================================
/**
 * 冷静期提示：`{message, daysLeft}` 或 null。
 * 它同时决定"是否显示取消注销按钮"—— 只在后端明确说"可取消"时显示。
 */
const pendingDeletion = ref(null);
const cancelDialogVisible = ref(false);
const cancelLoading = ref(false);
const cancelError = ref('');

const openCancelDialog = () => {
  cancelError.value = '';
  // 账号名已经在输入框里了（用户刚从登录框提交过），这里不再重复问
  cancelDialogVisible.value = true;
};

const confirmCancelDeletion = async () => {
  if (!username.value || !password.value) {
    cancelError.value = t('auth.cancelNeedsBoth');
    return;
  }
  cancelLoading.value = true;
  cancelError.value = '';
  try {
    const result = await cancelMyDeletion({
      username: username.value,
      password: password.value,
    });
    cancelDialogVisible.value = false;
    pendingDeletion.value = null;
    // 后端取消成功后直接签发 Token：写进登录态，用户不必再登一次
    if (result?.token) {
      authStore.setAuth({
        userData: { username: result.username || username.value },
        token: result.token,
      });
    }
    ElMessage.success(t('auth.cancelOk'));
    router.replace(route.query.redirect || '/');
  } catch (error) {
    cancelError.value = formatApiError(error, t('auth.cancelFailed'));
  } finally {
    cancelLoading.value = false;
  }
};
</script>

<template>
  <ConsoleAuthShell
    :eyebrow="t('auth.eyebrowDefault')"
    :title="t('auth.loginTitleDefault')"
    :subtitle="t('auth.consoleLoginSubtitle')"
  >
    <template #topbar-actions>
      {{ t('auth.noAgentAccount') }}<RouterLink to="/register" class="cs-inline-link">{{ t('auth.registerNow') }}</RouterLink>
    </template>

    <form class="cs-form" @submit.prevent="handleLogin">
      <div class="cs-field">
        <label class="cs-label" for="username">
          <span>{{ t('auth.consoleUsernameLabel') }}</span>
          <span class="cs-label-hint">{{ t('auth.employeeIdHint') }}</span>
        </label>
        <div class="cs-input-wrap">
          <i class="fas fa-user cs-lead-icon"></i>
          <input
            type="text"
            id="username"
            class="cs-input"
            v-model="username"
            @input="onUsernameChange"
            @focus="showUsernameSuggestions"
            @blur="hideUsernameSuggestions"
            :disabled="isLoading"
            :placeholder="t('auth.consoleUsernamePlaceholder')"
            autocomplete="username"
            required
          />

          <!-- 用户名建议下拉列表 -->
          <div v-if="showSuggestions && usernameSuggestions.length > 0" class="cs-suggest">
            <div class="cs-suggest-tip"><i class="fas fa-history"></i> {{ t('auth.recentAccounts') }}</div>
            <div
              v-for="(suggestion, index) in usernameSuggestions"
              :key="suggestion"
              class="cs-suggest-item"
              :class="{ 'is-recent': index === 0 }"
              @mousedown.prevent="selectUsername(suggestion)"
            >
              <i class="fas fa-user"></i>
              {{ suggestion }}
            </div>
          </div>
        </div>
      </div>

      <div class="cs-field">
        <label class="cs-label" for="password">{{ t('auth.passwordLabel') }}</label>
        <div class="cs-input-wrap">
          <i class="fas fa-lock cs-lead-icon"></i>
          <input
            :type="showPassword ? 'text' : 'password'"
            id="password"
            class="cs-input has-trailing"
            v-model="password"
            :disabled="isLoading"
            :placeholder="t('auth.passwordOnlyPlaceholder')"
            autocomplete="current-password"
            required
          />
          <button
            type="button"
            class="cs-input-trailing"
            :title="showPassword ? t('auth.hidePassword') : t('auth.showPassword')"
            :aria-label="showPassword ? t('auth.hidePassword') : t('auth.showPassword')"
            @click="showPassword = !showPassword"
          >
            <i :class="showPassword ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
          </button>
        </div>
      </div>

      <div class="cs-row">
        <label class="cs-check" for="rememberMe">
          <input type="checkbox" id="rememberMe" v-model="rememberMe" :disabled="isLoading" />
          <span>{{ t('auth.rememberLogin') }}</span>
        </label>
        <!-- 第 35 批：接上自助找回密码（此前这里写的是"请管理员重置"） -->
        <RouterLink to="/forgot-password" class="cs-inline-link">{{ t('auth.forgotPassword') }}</RouterLink>
      </div>

      <div v-if="errorMessage" class="cs-alert">
        <i class="fas fa-exclamation-circle"></i>
        <span>{{ errorMessage }}</span>
      </div>

      <!--
        第 101 批：注销冷静期的"出路"
        ------------------------------------------------------------------
        冷静期内账号已停用、登录接口会拒，所以**这是用户唯一能自助恢复的地方**。
        只在后端明确回 `can_cancel` 时显示（不猜）。
      -->
      <div v-if="pendingDeletion" class="cs-grace">
        <p class="cs-grace-text">
          <i class="fas fa-clock-rotate-left"></i>
          {{ t('auth.pendingDeletionHint', { days: pendingDeletion.daysLeft }) }}
        </p>
        <button type="button" class="cs-grace-btn" @click="openCancelDialog">
          <i class="fas fa-rotate-left"></i> {{ t('auth.cancelDeletion') }}
        </button>
      </div>

      <button type="submit" :disabled="isLoading" class="cs-submit">
        <span v-if="isLoading" class="cs-spinner"></span>
        <i v-else class="fas fa-sign-in-alt"></i>
        {{ isLoading ? t('auth.signingIn') : t('auth.signInConsole') }}
      </button>
    </form>

    <!-- 取消注销确认（沿用页面自己的对话框，不引 Element Plus 的 MessageBox：
         这里需要显示错误信息，MessageBox 关掉就看不到了） -->
    <div v-if="cancelDialogVisible" class="cs-modal-mask" @click.self="cancelDialogVisible = false">
      <div class="cs-modal">
        <h3>{{ t('auth.cancelDeletionTitle') }}</h3>
        <p class="cs-modal-desc">{{ t('auth.cancelDeletionDesc') }}</p>
        <div v-if="cancelError" class="cs-alert">
          <i class="fas fa-exclamation-circle"></i>
          <span>{{ cancelError }}</span>
        </div>
        <p class="cs-modal-account">
          <i class="fas fa-user"></i> {{ username || t('auth.cancelNeedsBoth') }}
        </p>
        <div class="cs-modal-actions">
          <button type="button" class="cs-modal-cancel" @click="cancelDialogVisible = false">
            {{ t('common.cancel') }}
          </button>
          <button type="button" class="cs-modal-ok" :disabled="cancelLoading" @click="confirmCancelDeletion">
            <span v-if="cancelLoading" class="cs-spinner"></span>
            {{ t('auth.cancelDeletionConfirm') }}
          </button>
        </div>
      </div>
    </div>
  </ConsoleAuthShell>
</template>

<style scoped>
/* 页面结构样式统一定义在 ConsoleAuthShell.vue 中（cs- 前缀），此处仅保留页面级微调 */

/* ============================================================================
   第 101 批：冷静期提示与"取消注销"对话框
   （cs- 前缀的通用样式在 ConsoleAuthShell 里，这里是本页独有的三块）
   ============================================================================ */
.cs-grace {
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid #d8ead9;
  border-radius: 10px;
  background: #f3faf4;
}

.cs-grace-text {
  margin: 0 0 10px;
  font-size: 13.5px;
  line-height: 1.7;
  color: #2c4a35;
}

.cs-grace-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 999px;
  background: var(--gradient-brand, linear-gradient(135deg, #2f855a, #1f6343));
  color: #fff;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
}

.cs-modal-mask {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(16, 32, 24, 0.45);
  padding: 20px;
}

.cs-modal {
  width: 100%;
  max-width: 420px;
  padding: 24px 24px 18px;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 18px 40px rgba(16, 32, 24, 0.24);
}

.cs-modal h3 {
  margin: 0 0 10px;
  font-size: 17px;
  color: #1f3a2a;
}

.cs-modal-desc {
  margin: 0 0 12px;
  font-size: 13.5px;
  line-height: 1.8;
  color: #4a5f52;
}

.cs-modal-account {
  margin: 0 0 16px;
  font-size: 13.5px;
  color: #2c4a35;
  font-weight: 600;
}

.cs-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.cs-modal-cancel,
.cs-modal-ok {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  border-radius: 999px;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
}

.cs-modal-cancel {
  border: 1px solid #d7e2da;
  background: #fff;
  color: #4a5f52;
}

.cs-modal-ok {
  border: none;
  background: var(--gradient-brand, linear-gradient(135deg, #2f855a, #1f6343));
  color: #fff;
}

.cs-modal-ok:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
