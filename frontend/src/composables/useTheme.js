import { reactive, computed } from 'vue';

const THEME_KEY = 'staychat_theme';

const state = reactive({
  theme: 'dark'
});

function applyTheme(theme) {
  // 强制深色模式
  state.theme = 'dark';
  document.documentElement.dataset.theme = 'dark';
  try { localStorage.setItem(THEME_KEY, 'dark'); } catch {}
}

export function initTheme() {
  applyTheme('dark');
}

export function useTheme() {
  const theme = computed(() => 'dark');
  const toggleTheme = () => {}; // 禁用切换
  return { theme, toggleTheme };
}

