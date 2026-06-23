<template>
  <nav :class="['side-nav', { collapsed: isCollapsed }]">
    <div class="nav-header">
      <div class="nav-header-row">
        <template v-if="!isCollapsed">
          <span class="nav-logo">知途</span>
          <span class="nav-subtitle">个性化学习小助手喵~</span>
        </template>
        <button class="collapse-btn" @click="$emit('toggle')" :title="isCollapsed ? '展开侧栏' : '收起侧栏'">
          <span v-if="isCollapsed">◀</span>
          <span v-else>▶</span>
        </button>
      </div>
    </div>

    <div class="nav-items">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        :class="{ active: isActive(item.path) }"
        :title="isCollapsed ? item.label : ''"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <span v-if="!isCollapsed" class="nav-label">{{ item.label }}</span>
      </router-link>
    </div>

    <div class="nav-footer">
      <div class="nav-status-wrap" @mouseenter="showMenu = true" @mouseleave="startHideTimer">
        <div class="nav-status" :class="{ clickable: !currentUser }" @click="!currentUser && router.push('/login')">
          <span class="status-dot" :class="{ online: !!currentUser }"></span>
          <span v-if="!isCollapsed" class="status-text">{{ currentUser || '点击登录' }}</span>
        </div>
        <div v-if="currentUser && showMenu" class="status-menu" @mouseenter="showMenu = true" @mouseleave="startHideTimer" @click.stop="handleLogout">
          退出登录
        </div>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useTheme } from '../composables/useTheme';
import { getUser, clearToken, clearUser } from '../services/api';

const currentUser = ref(getUser());
const showMenu = ref(false);
let hideTimer = null;

function startHideTimer() {
  hideTimer = setTimeout(() => { showMenu.value = false; }, 200);
}
function cancelHideTimer() {
  if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
}
const router = useRouter();

// 路由变化时刷新用户名
const route = useRoute();
watch(() => route.path, () => { currentUser.value = getUser(); });

function handleLogout() {
  clearToken();
  clearUser();
  currentUser.value = '';
  showMenu.value = false;
  router.push('/login');
}

defineProps({ isCollapsed: Boolean });
defineEmits(['toggle']);

const { theme, toggleTheme } = useTheme();

const navItems = [
  { path: '/learn', label: 'AI 对话', icon: '💬' },
  { path: '/resources', label: '学习资源', icon: '📚' },
  { path: '/profile', label: '我的画像', icon: '👤' },
  { path: '/path', label: '学习路径', icon: '🗺️' },
  { path: '/evaluate', label: '学习评估', icon: '📊' },
];

function isActive(path) {
  return route.path === path;
}
</script>

<style scoped>
.side-nav {
  width: 220px;
  min-width: 220px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #2a2a2a;
  border-radius: 0;
  padding: 0;
  background: var(--hero);
  transition: width 0.2s, min-width 0.2s;
}
.side-nav.collapsed {
  width: 56px;
  min-width: 56px;
}

.collapse-btn {
  background: none;
  border: none;
  color: var(--ink-dim);
  font-size: 16px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
  transition: all 0.15s;
}
.collapse-btn:hover { color: var(--ink); background: var(--surface-strong); }

.nav-header {
  padding: 14px 12px;
  border-bottom: 1px solid #2a2a2a;
}
.nav-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.side-nav.collapsed .nav-header-row {
  justify-content: center;
}
.nav-logo {
  font-size: 22px;
  font-weight: 700;
  color: var(--ink);
}
.nav-subtitle {
  display: block;
  font-size: 10px;
  color: var(--ink-dim);
  margin-top: 0;
  letter-spacing: 0.5px;
}
.collapse-btn {
  background: none;
  border: none;
  color: var(--ink-dim);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.15s;
  line-height: 1;
}
.collapse-btn:hover { color: var(--ink); background: var(--surface-strong); }

.nav-items {
  flex: 1;
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.side-nav.collapsed .nav-items {
  align-items: center;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  color: var(--ink-dim);
  text-decoration: none;
  font-size: 14px;
  font-weight: 450;
  transition: all 0.15s;
}
.side-nav.collapsed .nav-item {
  justify-content: center;
  padding: 10px;
}
.nav-item:hover { background: var(--surface-strong); color: var(--ink); }
.nav-item.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.nav-icon { font-size: 18px; }
.nav-label { font-size: 13px; }

.nav-footer {
  padding: 12px;
  border-top: 1px solid #2a2a2a;
  display: flex;
  align-items: center;
  gap: 10px;
}
.side-nav.collapsed .nav-footer {
  justify-content: center;
}
.theme-toggle {
  cursor: pointer;
  font-size: 16px;
  padding: 4px;
  border-radius: 8px;
  transition: background 0.15s;
}
.theme-toggle:hover { background: var(--surface-strong); }
.nav-status-wrap {
  position: relative;
}
.nav-status {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-radius: 8px;
  transition: background 0.15s;
}
.nav-status.clickable { cursor: pointer; }
.nav-status-wrap:hover .nav-status { background: var(--surface-strong); }
.status-menu {
  position: absolute;
  bottom: 100%;
  left: 0;
  margin-bottom: 0;
  background: var(--surface-strong);
  border: 1px solid #444;
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 13px;
  color: var(--danger);
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}
.status-menu:hover { background: var(--accent-soft); }
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ink-dim);
}
.status-dot.online { background: #22c55e; }
.status-text { font-size: 12px; color: var(--ink-dim); }
</style>
