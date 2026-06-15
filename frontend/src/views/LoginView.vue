<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <h1>知途</h1>
        <p>个性化学习多智能体系统</p>
      </div>

      <div class="tabs">
        <button :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</button>
        <button :class="{ active: mode === 'register' }" @click="mode = 'register'">注册</button>
      </div>

      <form @submit.prevent="submit" class="login-form">
        <input v-model="username" type="text" placeholder="用户名" required minlength="2" />
        <input v-model="password" type="password" placeholder="密码" required minlength="4" />
        <input v-if="mode === 'register'" v-model="nickname" type="text" placeholder="昵称（选填）" />
        <button type="submit" class="submit-btn" :disabled="loading">
          {{ loading ? '处理中...' : mode === 'login' ? '登录' : '注册' }}
        </button>
      </form>

      <div v-if="error" class="error-msg">{{ error }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { apiRequest, setToken, setUser } from '../services/api';

const router = useRouter();
const mode = ref('login');
const username = ref('');
const password = ref('');
const nickname = ref('');
const loading = ref(false);
const error = ref('');

async function submit() {
  error.value = '';
  loading.value = true;
  try {
    const endpoint = mode.value === 'login' ? '/api/auth/login' : '/api/auth/register';
    const body = mode.value === 'login'
      ? { username: username.value, password: password.value }
      : { username: username.value, password: password.value, nickname: nickname.value || username.value };
    const data = await apiRequest(endpoint, { method: 'POST', body });
    setToken(data.token);
    setUser(data.user?.nickname || data.user?.username || username.value);
    router.push('/learn');
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  display: flex; align-items: center; justify-content: center;
  height: 100%; width: 100%;
}
.login-card {
  width: 360px; padding: 36px 32px;
  background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px;
}
.login-header { text-align: center; margin-bottom: 24px; }
.login-header h1 { font-size: 28px; font-weight: 700; color: #fff; margin: 0; }
.login-header p { font-size: 13px; color: #888; margin: 4px 0 0; }

.tabs { display: flex; gap: 0; margin-bottom: 20px; border-radius: 8px; overflow: hidden; border: 1px solid #333; }
.tabs button {
  flex: 1; padding: 10px; border: none; background: #111; color: #888;
  font-size: 14px; cursor: pointer; transition: all 0.15s;
}
.tabs button.active { background: var(--accent); color: #fff; font-weight: 600; }

.login-form { display: flex; flex-direction: column; gap: 12px; }
.login-form input {
  padding: 12px 14px; border-radius: 8px; border: 1px solid #333;
  background: #111; color: #e0e0e0; font-size: 14px; outline: none;
}
.login-form input:focus { border-color: var(--accent); }
.submit-btn {
  padding: 12px; border-radius: 8px; border: none; background: var(--accent);
  color: #fff; font-size: 15px; font-weight: 600; cursor: pointer; transition: opacity 0.15s;
  margin-top: 4px;
}
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.error-msg { margin-top: 16px; padding: 10px; background: #3a1010; color: #ff6b6b; border-radius: 8px; font-size: 13px; text-align: center; }
</style>
