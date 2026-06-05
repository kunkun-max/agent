<template>
  <AnimatedBackdrop />
  <div class="app-layout">
    <SideNav v-if="showSidebar" :isCollapsed="sidebarCollapsed" @toggle="sidebarCollapsed = !sidebarCollapsed" />
    <main class="main-content">
      <RouterView v-slot="{ Component }">
        <Transition name="fade-slide" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AnimatedBackdrop from './components/AnimatedBackdrop.vue';
import SideNav from './components/SideNav.vue';
import { getToken, clearToken, clearUser, isLoggedIn } from './services/api';

const route = useRoute();
const router = useRouter();
const sidebarCollapsed = ref(false);
const authChecked = ref(false);

const showSidebar = computed(() => route.path !== '/login');

// 启动时验证 Token 有效性
onMounted(async () => {
  if (isLoggedIn()) {
    try {
      const resp = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!resp.ok) {
        clearToken();
        clearUser();
        router.replace('/login');
      }
    } catch {
      // 后端没启动，不处理
    }
  }
  authChecked.value = true;
});
</script>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  position: relative;
  z-index: 1;
}
.main-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
