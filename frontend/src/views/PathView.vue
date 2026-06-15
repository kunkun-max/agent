<template>
  <div class="path-view">
    <header class="view-header glass-panel">
      <h2 class="view-title">学习路径</h2>
      <p class="view-desc">多课程 · 个性化规划</p>
    </header>

    <div v-if="paths.length === 0" class="empty-state">
      <div class="empty-icon">🗺️</div>
      <p class="empty-title">尚未规划学习路径</p>
      <p class="empty-desc">去 AI 对话中说"帮我规划学习路径"来生成</p>
      <router-link to="/learn" class="empty-link">去对话 →</router-link>
    </div>

    <div v-else class="path-content">
      <div v-for="(p, pi) in paths" :key="pi" class="path-section">
        <div class="path-course-header">
          <span class="path-course-title">📚 {{ p.course }}</span>
          <button class="path-delete-btn" @click="deletePath(p.course)">删除</button>
        </div>
        <div class="timeline">
          <div
            v-for="(node, idx) in p.nodes"
            :key="node.topic"
            :class="['timeline-node', { completed: node._completed, locked: idx > 0 && !p.nodes[idx-1]?._completed }]"
            @click="toggleNode(p, idx)"
          >
            <div class="node-dot">
              <span v-if="node._completed">✓</span>
              <span v-else>{{ idx + 1 }}</span>
            </div>
            <div class="node-line"></div>
            <div class="node-card glass-panel">
              <div class="node-header">
                <span :class="['node-check', { done: node._completed }]">
                  {{ node._completed ? '✓' : '○' }}
                </span>
                <h4>{{ node.topic }}</h4>
                <span class="node-time">~{{ node.estimated_minutes }} 分钟</span>
              </div>
              <div v-if="node.goal" class="node-goal">{{ node.goal }}</div>
              <div v-if="node.prerequisites?.length" class="node-prereqs">
                前置：{{ node.prerequisites.join('、') }}
              </div>
              <div v-if="node.resources?.length" class="node-resources">
                <span v-for="r in node.resources" :key="r" class="resource-chip">{{ resLabel(r) }}</span>
              </div>
              <div v-if="node.resources?.some(r => SUPPORTED_TYPES.has(r))" class="node-actions" @click.stop>
                <button
                  v-for="r in node.resources.filter(r => SUPPORTED_TYPES.has(r))"
                  :key="'gen-'+r"
                  :class="['gen-btn', { success: genSuccessKeys.has(nodeKey(p.course, idx, r)) }]"
                  :disabled="generatingKey === nodeKey(p.course, idx, r) || genSuccessKeys.has(nodeKey(p.course, idx, r))"
                  @click.stop="generateNodeResources(p, node, r)"
                >
                  {{ generatingKey === nodeKey(p.course, idx, r) ? '生成中...' : genSuccessKeys.has(nodeKey(p.course, idx, r)) ? '已生成' : genBtnLabel(r) }}
                </button>
              </div>
            </div>
          </div>
        </div>
        <div class="path-stats glass-panel">
          <div class="stat">
            <div class="stat-val">{{ getCompleted(p) }} / {{ p.nodes.length }}</div>
            <div class="stat-label">已完成</div>
          </div>
          <div class="stat">
            <div class="stat-val">{{ getHours(p) }}</div>
            <div class="stat-label">预计总时长（小时）</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { apiRequest, getToken, clearToken, clearUser } from '../services/api';

const paths = ref([]);
const generatingKey = ref('');
const genSuccessKeys = ref(new Set());

// 后端 Agent 支持的资源类型（与 AGENT_TYPE_MAP 对齐）
const SUPPORTED_TYPES = new Set(['doc', 'mindmap', 'quiz', 'code', 'reading']);

onMounted(async () => {
  try {
    const data = await apiRequest('/api/paths');
    if (data.paths?.length) {
      paths.value = data.paths.map(p => {
        const savedCompleted = p.status?.completed || [];
        const nodes = (p.path?.nodes || []).map((n, i) => ({
          ...n, _completed: savedCompleted.includes(i)
        }));
        return { course: p.course, student_summary: p.path?.student_summary || '', nodes };
      });
    }
  } catch (e) { console.log('路径加载失败'); }
});

async function toggleNode(p, idx) {
  if (idx > 0 && !p.nodes[idx - 1]?._completed) return;
  p.nodes[idx]._completed = !p.nodes[idx]._completed;
  // 取消完成 → 重置后续
  if (!p.nodes[idx]._completed) {
    for (let i = idx + 1; i < p.nodes.length; i++) p.nodes[i]._completed = false;
  }
  // 保存到后端
  const completed = p.nodes.map((n, i) => n._completed ? i : -1).filter(i => i >= 0);
  try {
    await apiRequest('/api/path/progress', {
      method: 'POST',
      body: { course: p.course, completed }
    });
  } catch (e) { console.error('[PATH] 进度保存失败:', e.message); }
}

function getCompleted(p) { return p.nodes.filter(n => n._completed).length; }
function getHours(p) {
  const mins = p.nodes.reduce((s, n) => s + (n.estimated_minutes || 0), 0);
  return (mins / 60).toFixed(1);
}
function resLabel(r) {
  const map = { doc: '📄 讲义', mindmap: '🧠 导图', quiz: '✍️ 习题', code: '💻 代码', practice: '🔧 实操', reading: '📖 阅读', video: '🎬 视频' };
  return map[r] || r;
}

async function deletePath(course) {
  try {
    await apiRequest('/api/path?course=' + encodeURIComponent(course), { method: 'DELETE' });
    paths.value = paths.value.filter(p => p.course !== course);
  } catch {}
}

function nodeKey(course, idx, resType) {
  return `${course}_${idx}_${resType}`;
}

function genBtnLabel(r) {
  const map = { doc: '📝 生成讲义', mindmap: '🧠 生成导图', quiz: '✍️ 生成习题', code: '💻 生成代码', reading: '📖 生成阅读' };
  return map[r] || `生成 ${r}`;
}

async function generateNodeResources(pathData, node, resourceType) {
  const idx = pathData.nodes.indexOf(node);
  const realKey = nodeKey(pathData.course, idx, resourceType);
  generatingKey.value = realKey;

  try {
    const body = {
      course: pathData.course || '',
      student_summary: pathData.student_summary || '',
      topic: node.topic || '',
      goal: node.goal || '',
      resource_type: resourceType,
    };

    const headers = { 'Content-Type': 'application/json' };
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const resp = await fetch('/api/path/generate-resources', {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      if (resp.status === 401) { clearToken(); clearUser(); window.location.reload(); return; }
      throw new Error('请求失败');
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);
        if (data === '[DONE]') continue;
        try {
          const parsed = JSON.parse(data);
          if (parsed.__done__) {
            const newSet = new Set(genSuccessKeys.value);
            newSet.add(realKey);
            genSuccessKeys.value = newSet;
          }
        } catch {}
      }
    }
  } catch (e) {
    console.error('资源生成失败:', e);
  } finally {
    generatingKey.value = '';
  }
}
</script>

<style scoped>
.path-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.view-header {
  background: #1a1a1a;
  padding: 16px 24px;
  border-radius: 0;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
}
.view-title { font-size: 17px; font-weight: 600; color: var(--ink); margin: 0; }
.view-desc { font-size: 12px; color: var(--ink-dim); margin: 2px 0 0; }

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--ink-dim);
}
.empty-icon { font-size: 48px; }
.empty-title { font-size: 16px; font-weight: 600; color: var(--ink); }
.empty-desc { font-size: 13px; }
.empty-link {
  margin-top: 12px;
  padding: 8px 20px;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  text-decoration: none;
  font-size: 14px;
}

.path-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
.path-section {
  margin-bottom: 40px;
}
.path-course-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16px; padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
}
.path-course-title { font-size: 16px; font-weight: 600; color: var(--ink); }
.path-delete-btn {
  font-size: 11px; padding: 4px 12px; border-radius: 6px;
  background: transparent; border: 1px solid #e04040; color: #e04040; cursor: pointer;
}
.path-delete-btn:hover { background: #e04040; color: #fff; }

/* 时间线 */
.timeline {
  position: relative;
  padding-left: 48px;
}
.timeline-node {
  position: relative;
  margin-bottom: 0;
}
.timeline-node:not(:last-child) .node-line {
  position: absolute;
  left: -32px;
  top: 28px;
  width: 2px;
  height: calc(100% + 8px);
  background: var(--line);
}
.timeline-node.completed .node-line { background: var(--accent); }
.node-dot {
  position: absolute;
  left: -42px;
  top: 4px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--surface);
  border: 2px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-dim);
  z-index: 1;
}
.timeline-node.completed .node-dot {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.timeline-node.current .node-dot {
  border-color: var(--accent);
  color: var(--accent);
  box-shadow: 0 0 0 4px var(--accent-soft);
}

.node-card {
  padding: 14px 18px;
  margin-bottom: 12px;
  border: 1px solid var(--line);
  cursor: pointer;
  transition: border-color 0.15s;
}
.node-card:hover { border-color: var(--accent); }
.timeline-node.locked .node-card { opacity: 0.5; cursor: default; }
.timeline-node.locked .node-card:hover { border-color: var(--line); }
.timeline-node.completed .node-card { opacity: 0.7; }
.timeline-node.completed .node-card h4 { text-decoration: line-through; }
.timeline-node.current .node-card { border-color: var(--accent); }
.timeline-node.completed .node-card { opacity: 0.7; }

.node-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.node-check {
  font-size: 18px; margin-right: 8px; color: var(--ink-dim);
}
.node-check.done { color: var(--accent); }
.node-header h4 { font-size: 15px; font-weight: 600; margin: 0; color: var(--ink); }
.node-time { font-size: 11px; color: var(--ink-dim); }

.node-prereqs {
  font-size: 11px;
  color: var(--ink-dim);
  margin-top: 6px;
}
.node-goal {
  font-size: 11px; color: var(--ink-dim); margin-top: 4px; line-height: 1.4;
}
.node-resources {
  display: flex;
  gap: 4px;
  margin-top: 8px;
}
.resource-chip {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}

/* 资源生成按钮组 */
.node-actions {
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px;
}
.gen-btn {
  padding: 4px 12px; border-radius: 6px; font-size: 11px;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15);
  color: rgba(255,255,255,0.70); cursor: pointer;
  transition: all 0.15s;
}
.gen-btn:hover:not(:disabled) {
  border-color: var(--accent); color: var(--accent); background: var(--accent-soft);
}
.gen-btn:disabled {
  opacity: 0.5; cursor: not-allowed;
}
.gen-btn.success {
  border-color: #22c55e; color: #22c55e; background: rgba(34,197,94,0.10);
  opacity: 0.8; cursor: default;
}

.path-stats {
  margin-top: 32px;
  padding: 18px;
  display: flex;
  gap: 48px;
  border: 1px solid var(--line);
}
.stat { text-align: center; }
.stat-val { font-size: 28px; font-weight: 700; color: var(--accent); }
.stat-label { font-size: 12px; color: var(--ink-dim); margin-top: 2px; }
</style>
