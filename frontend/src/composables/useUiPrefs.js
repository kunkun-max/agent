import { reactive, computed } from 'vue';

const KEY = 'staychat_ui_prefs';

const state = reactive({
  // Superhuman-ish: links/interactive elements lean amethyst.
  accent: '#714cb6',
  glassBlur: 0,
  surfaceAlpha: 0.64,
  density: 'comfort', // comfort | compact
  hideRightPanel: false
});

function clamp(n, min, max) {
  const v = Number(n);
  if (!Number.isFinite(v)) return min;
  return Math.min(max, Math.max(min, v));
}

function apply() {
  const root = document.documentElement;
  root.style.setProperty('--accent', state.accent);
  // Derive a soft accent tint so the accent setting visibly impacts UI states.
  // Only do this for full 6-digit hex colors.
  const a = String(state.accent || '').trim();
  if (/^#[0-9a-fA-F]{6}$/.test(a)) {
    root.style.setProperty('--accent-soft', `${a}26`); // ~15% alpha
  }
  root.style.setProperty('--glass-blur', `${clamp(state.glassBlur, 0, 24)}px`);
  root.style.setProperty('--surface-alpha', String(clamp(state.surfaceAlpha, 0.4, 0.95)));
  root.dataset.density = state.density === 'compact' ? 'compact' : 'comfort';
  root.dataset.rightPanel = state.hideRightPanel ? 'hidden' : 'shown';
}

function persist() {
  try {
    localStorage.setItem(KEY, JSON.stringify({
      accent: state.accent,
      glassBlur: state.glassBlur,
      surfaceAlpha: state.surfaceAlpha,
      density: state.density,
      hideRightPanel: state.hideRightPanel
    }));
  } catch {}
}

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    if (data && typeof data === 'object') {
      if (typeof data.accent === 'string' && data.accent.startsWith('#')) {
        const a = String(data.accent).toLowerCase();
        // Migrate older cute-pink defaults to the newer Superhuman-ish amethyst.
        if (a === '#ff4fa7' || a === '#fd68b3') {
          state.accent = '#714cb6';
        } else {
          state.accent = data.accent;
        }
      }
      if (data.glassBlur != null) state.glassBlur = clamp(data.glassBlur, 0, 24);
      if (data.surfaceAlpha != null) state.surfaceAlpha = clamp(data.surfaceAlpha, 0.4, 0.95);
      if (data.density === 'compact' || data.density === 'comfort') state.density = data.density;
      if (typeof data.hideRightPanel === 'boolean') state.hideRightPanel = data.hideRightPanel;
    }
  } catch {}
}

export function initUiPrefs() {
  load();
  apply();
}

export function useUiPrefs() {
  const prefs = computed(() => state);
  const setPrefs = (patch = {}) => {
    if (patch.accent != null) state.accent = String(patch.accent);
    if (patch.glassBlur != null) state.glassBlur = clamp(patch.glassBlur, 0, 24);
    if (patch.surfaceAlpha != null) state.surfaceAlpha = clamp(patch.surfaceAlpha, 0.4, 0.95);
    if (patch.density != null) state.density = patch.density === 'compact' ? 'compact' : 'comfort';
    if (patch.hideRightPanel != null) state.hideRightPanel = Boolean(patch.hideRightPanel);
    persist();
    apply();
  };
  const reset = () => {
    state.accent = '#714cb6';
    state.glassBlur = 0;
    state.surfaceAlpha = 0.64;
    state.density = 'comfort';
    state.hideRightPanel = false;
    persist();
    apply();
  };
  return { prefs, setPrefs, reset };
}
