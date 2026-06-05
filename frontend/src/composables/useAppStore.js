import { reactive } from 'vue';

const STORE_KEY = 'a3_learning_store';

// 从 localStorage 恢复
function loadStore() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

// 持久化到 localStorage
function saveStore(state) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({
      resources: state.resources,
      profile: state.profile,
      path: state.path,
      studentId: state.studentId,
    }));
  } catch {}
}

const saved = loadStore();

const store = reactive({
  studentId: saved.studentId || ('student_' + Date.now()),

  // 学习资源列表
  resources: saved.resources || [],

  // 学生画像
  profile: saved.profile || null,

  // 学习路径
  path: saved.path || null,

  // ===== 操作方法 =====

  // 添加一份资源（从聊天生成后调用）
  addResource(resource) {
    this.resources.unshift({
      id: 'res_' + Date.now(),
      ...resource,
      createdAt: new Date().toISOString(),
    });
    saveStore(this);
  },

  // 批量添加资源
  addResources(list) {
    for (const r of list) {
      this.resources.unshift({
        id: 'res_' + Date.now(),
        ...r,
        createdAt: new Date().toISOString(),
      });
    }
    saveStore(this);
  },

  // 更新画像
  updateProfile(profile) {
    this.profile = { ...this.profile, ...profile };
    saveStore(this);
  },

  // 更新学习路径
  updatePath(pathData) {
    this.path = pathData;
    saveStore(this);
  },

  // 清空
  clearAll() {
    this.resources = [];
    this.profile = null;
    this.path = null;
    saveStore(this);
  },
});

export function useAppStore() {
  return store;
}
