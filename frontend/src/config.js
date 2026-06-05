function trimTrailingSlash(value) {
  return String(value || '').replace(/\/+$/, '');
}

function getDefaultApiBase() {
  return '';  // vite proxy 已经把 /api 代理到后端了
}

export const API_BASE = trimTrailingSlash(import.meta.env.VITE_API_BASE_URL || getDefaultApiBase());
