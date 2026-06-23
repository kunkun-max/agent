import { API_BASE } from '../config';

const TOKEN_KEY = 'a3_auth_token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}
export function setToken(token) { localStorage.setItem(TOKEN_KEY, token); }
export function clearToken() { localStorage.removeItem(TOKEN_KEY); }
export function isLoggedIn() { return !!getToken(); }

const USER_KEY = 'a3_current_user';
export function setUser(name) { localStorage.setItem(USER_KEY, name); }
export function getUser() { return localStorage.getItem(USER_KEY) || ''; }
export function clearUser() { localStorage.removeItem(USER_KEY); }

/**
 * API 请求封装 — 自动带 Token
 */
export async function apiRequest(path, options = {}) {
  const { method = 'GET', body = null } = options;
  const headers = { 'Accept': 'application/json' };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const fetchOptions = { method, headers };
  if (body !== null) {
    headers['Content-Type'] = 'application/json';
    fetchOptions.body = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE}${path}`, fetchOptions);

  if (response.status === 401) {
    clearToken();
    clearUser();
    window.location.hash = '#/login';
    window.location.reload();
    throw new Error('登录已过期，请重新登录');
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`请求失败 (${response.status}): ${text}`);
  }

  const ct = response.headers.get('content-type') || '';
  if (ct.includes('text/event-stream')) return response;
  return response.json();
}

/**
 * SSE 流式读取器 — 自动带 Token
 */
export async function apiStreamReader(path, body) {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST', headers, body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`流式请求失败 (${response.status})`);
  return response.body.getReader();
}
