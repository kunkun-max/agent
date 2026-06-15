<template>
  <div class="evaluate-view">
    <header class="view-header glass-panel">
      <h2 class="view-title">学习评估</h2>
      <p class="view-desc">多维度评估 · 雷达图可视化 · 动态追踪</p>
      <button class="trigger-btn" @click="triggerEvaluate" :disabled="triggering">
        {{ triggering ? '评估中...' : '重新评估' }}
      </button>
    </header>

    <div v-if="!evaluation" class="empty-state">
      <div class="empty-icon">📊</div>
      <p class="empty-title">暂无评估数据</p>
      <p class="empty-desc">在AI对话中说"帮我评估一下学习效果"，或点击上方按钮手动触发</p>
      <button class="trigger-btn-lg" @click="triggerEvaluate" :disabled="triggering">
        {{ triggering ? '正在生成评估...' : '开始评估' }}
      </button>
    </div>

    <div v-else class="eval-content">
      <!-- 总分 + 雷达图 -->
      <div class="eval-top">
        <div class="score-ring glass-panel">
          <div class="ring-label">总体评分</div>
          <div class="ring-value">{{ animatedScore }}</div>
          <div class="ring-date">{{ formatDate(evaluation.created_at) }}</div>
        </div>
        <div class="radar-wrap glass-panel">
          <svg viewBox="0 0 400 400" class="radar-svg">
            <!-- 背景五边形（3层） -->
            <polygon v-for="level in [0.2, 0.6, 1.0]" :key="level"
              :points="radarBgPoints(level)" class="radar-bg" />
            <!-- 轴线 -->
            <line v-for="(ax, i) in axisEndpoints" :key="'ax'+i"
              :x1="200" :y1="200" :x2="ax.x" :y2="ax.y" class="radar-axis" />
            <!-- 数据多边形 -->
            <polygon :points="radarDataPoints" class="radar-fill" />
            <!-- 数据点圆圈 -->
            <circle v-for="(pt, i) in radarDataCoords" :key="'pt'+i"
              :cx="pt.x" :cy="pt.y" r="5" class="radar-dot" />
            <!-- 维度标签 -->
            <text v-for="(label, i) in dimensionLabels" :key="'lb'+i"
              :x="labelPositions[i].x" :y="labelPositions[i].y"
              :text-anchor="labelPositions[i].anchor"
              class="radar-label">{{ label.name }} {{ label.value }}</text>
          </svg>
        </div>
      </div>

      <!-- 优势与待改进 -->
      <div class="eval-tags-row">
        <section class="tag-card glass-panel">
          <h3>💪 优势</h3>
          <div class="tag-list">
            <span v-for="s in evaluation.strengths" :key="s" class="tag green">{{ s }}</span>
            <span v-if="!evaluation.strengths?.length" class="dim-text">暂无数据</span>
          </div>
        </section>
        <section class="tag-card glass-panel">
          <h3>⚠️ 待改进</h3>
          <div class="tag-list">
            <span v-for="w in evaluation.weaknesses" :key="w" class="tag red">{{ w }}</span>
            <span v-if="!evaluation.weaknesses?.length" class="dim-text">暂无数据</span>
          </div>
        </section>
      </div>

      <!-- 改进建议 -->
      <section v-if="evaluation.recommendations?.length" class="rec-card glass-panel">
        <h3>📋 改进建议</h3>
        <div class="rec-list">
          <div v-for="(rec, i) in evaluation.recommendations" :key="i" class="rec-item">
            <span :class="['rec-priority', priorityClass(rec.priority)]">{{ rec.priority || '建议' }}</span>
            <div class="rec-body">
              <div class="rec-action">{{ rec.action }}</div>
              <div v-if="rec.reason" class="rec-reason">{{ rec.reason }}</div>
            </div>
            <span v-if="rec.suggested_time" class="rec-time">{{ rec.suggested_time }}</span>
          </div>
        </div>
      </section>

      <!-- 鼓励语 -->
      <div v-if="evaluation.encouragement" class="encourage glass-panel">
        {{ evaluation.encouragement }}
      </div>

      <!-- 历史趋势 -->
      <section v-if="history.length > 1" class="history-card glass-panel">
        <h3>📈 评估趋势</h3>
        <div class="trend-chart">
          <div v-for="(item, i) in history" :key="i" class="trend-bar-wrap">
            <div class="trend-bar" :style="{ height: barHeight(item.eval_data?.overall_score || 0) }">
              <span class="trend-val">{{ item.eval_data?.overall_score || 0 }}</span>
            </div>
            <span class="trend-date">{{ formatShortDate(item.created_at) }}</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import { apiRequest } from '../services/api';

const evaluation = ref(null);
const history = ref([]);
const triggering = ref(false);
const animatedScore = ref(0);

const DIMENSION_KEYS = ['知识掌握', '实践应用', '学习投入', '进步趋势', '风险预警'];
const DIMENSION_COUNT = 5;
const CENTER = 200;
const RADIUS = 140;

// 计算雷达图各维度标签和坐标
const dimensionLabels = computed(() => {
  const dims = evaluation.value?.dimensions || {};
  return DIMENSION_KEYS.map(name => ({
    name,
    value: dims[name] ?? 0,
  }));
});

// 各轴端点
const axisEndpoints = computed(() => {
  return Array.from({ length: DIMENSION_COUNT }, (_, i) => {
    const angle = (Math.PI * 2 * i) / DIMENSION_COUNT - Math.PI / 2;
    return {
      x: CENTER + RADIUS * Math.cos(angle),
      y: CENTER + RADIUS * Math.sin(angle),
    };
  });
});

// 标签位置（稍微往外偏移）
const labelPositions = computed(() => {
  return Array.from({ length: DIMENSION_COUNT }, (_, i) => {
    const angle = (Math.PI * 2 * i) / DIMENSION_COUNT - Math.PI / 2;
    const lx = CENTER + (RADIUS + 32) * Math.cos(angle);
    const ly = CENTER + (RADIUS + 32) * Math.sin(angle);
    const anchor = Math.abs(Math.cos(angle)) < 0.1 ? 'middle' : Math.cos(angle) > 0 ? 'start' : 'end';
    return { x: lx, y: ly + 4, anchor };
  });
});

// 数据点坐标
const radarDataCoords = computed(() => {
  const dims = evaluation.value?.dimensions || {};
  return DIMENSION_KEYS.map((name, i) => {
    const value = (dims[name] ?? 0) / 100;
    const angle = (Math.PI * 2 * i) / DIMENSION_COUNT - Math.PI / 2;
    return {
      x: CENTER + RADIUS * value * Math.cos(angle),
      y: CENTER + RADIUS * value * Math.sin(angle),
    };
  });
});

// 数据多边形 points
const radarDataPoints = computed(() => {
  return radarDataCoords.value.map(p => `${p.x},${p.y}`).join(' ');
});

// 背景多边形 points
function radarBgPoints(scale) {
  return Array.from({ length: DIMENSION_COUNT }, (_, i) => {
    const angle = (Math.PI * 2 * i) / DIMENSION_COUNT - Math.PI / 2;
    return `${CENTER + RADIUS * scale * Math.cos(angle)},${CENTER + RADIUS * scale * Math.sin(angle)}`;
  }).join(' ');
}

// 总分动画
function animateScore(target) {
  const duration = 800;
  const start = animatedScore.value;
  const diff = target - start;
  const startTime = performance.now();
  function step(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    animatedScore.value = Math.round(start + diff * eased);
    if (progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

watch(evaluation, (val) => {
  if (val?.overall_score != null) {
    animateScore(val.overall_score);
  }
}, { immediate: true });

function priorityClass(p) {
  if (!p) return '';
  const s = String(p);
  if (s.includes('高')) return 'high';
  if (s.includes('中')) return 'mid';
  return 'low';
}

function barHeight(score) {
  return Math.max(8, score * 1.6) + 'px';
}

function formatDate(dt) {
  if (!dt) return '';
  return dt.replace('T', ' ').slice(0, 16);
}
function formatShortDate(dt) {
  if (!dt) return '';
  return dt.slice(5, 10);
}

async function loadData() {
  try {
    const data = await apiRequest('/api/evaluate');
    if (data.evaluation) {
      evaluation.value = {
        ...data.evaluation.eval_data,
        created_at: data.evaluation.created_at,
      };
    }
  } catch {}
  try {
    const hist = await apiRequest('/api/evaluate/history');
    history.value = hist.evaluations || [];
  } catch {}
}

async function triggerEvaluate() {
  triggering.value = true;
  try {
    const data = await apiRequest('/api/evaluate/trigger', { method: 'POST' });
    if (data.evaluation) {
      evaluation.value = { ...data.evaluation, created_at: new Date().toISOString() };
      // 重新加载历史
      const hist = await apiRequest('/api/evaluate/history');
      history.value = hist.evaluations || [];
    }
  } catch (e) {
    console.error('评估失败:', e);
  } finally {
    triggering.value = false;
  }
}

onMounted(loadData);
</script>

<style scoped>
.evaluate-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.view-header {
  background: var(--surface);
  padding: 16px 24px;
  border-bottom: 1px solid var(--line);
  position: relative;
}
.view-title { font-size: 17px; font-weight: 600; color: var(--ink); margin: 0; }
.view-desc { font-size: 12px; color: var(--ink-dim); margin: 2px 0 0; }
.trigger-btn {
  position: absolute; right: 20px; top: 14px;
  padding: 6px 18px; border-radius: 8px; font-size: 13px;
  background: var(--accent); color: #fff; border: none; cursor: pointer;
  transition: opacity 0.15s;
}
.trigger-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.trigger-btn:not(:disabled):hover { opacity: 0.85; }

/* 空状态 */
.empty-state {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 8px; color: var(--ink-dim);
}
.empty-icon { font-size: 48px; }
.empty-title { font-size: 16px; font-weight: 600; color: var(--ink); }
.empty-desc { font-size: 13px; max-width: 400px; text-align: center; }
.trigger-btn-lg {
  margin-top: 16px; padding: 10px 28px; border-radius: 10px; font-size: 15px;
  background: var(--accent); color: #fff; border: none; cursor: pointer;
  transition: opacity 0.15s;
}
.trigger-btn-lg:disabled { opacity: 0.5; cursor: not-allowed; }

/* 评估内容 */
.eval-content {
  flex: 1; overflow-y: auto; padding: 20px 24px;
  display: flex; flex-direction: column; gap: 16px;
}

/* 顶部：总分 + 雷达图 */
.eval-top {
  display: flex; gap: 16px; align-items: stretch;
}
.score-ring {
  width: 180px; flex-shrink: 0; padding: 28px 20px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  border: 1px solid var(--line);
}
.ring-label { font-size: 13px; color: var(--ink-dim); margin-bottom: 8px; }
.ring-value { font-size: 56px; font-weight: 800; color: var(--accent); line-height: 1; }
.ring-date { font-size: 11px; color: var(--ink-dim); margin-top: 8px; }

.radar-wrap {
  flex: 1; padding: 16px; border: 1px solid var(--line);
  display: flex; align-items: center; justify-content: center;
}
.radar-svg { width: 100%; max-width: 400px; }
.radar-bg { fill: none; stroke: rgba(255,255,255,0.08); stroke-width: 1; }
.radar-axis { stroke: rgba(255,255,255,0.12); stroke-width: 1; }
.radar-fill {
  fill: rgba(189, 187, 255, 0.18);
  stroke: var(--accent); stroke-width: 2;
  transition: points 0.6s ease;
}
.radar-dot { fill: var(--accent); stroke: #fff; stroke-width: 2; }
.radar-label {
  font-size: 13px; fill: rgba(255,255,255,0.85); font-weight: 500;
}

/* 优势/待改进 */
.eval-tags-row { display: flex; gap: 16px; }
.tag-card {
  flex: 1; padding: 18px; border: 1px solid var(--line);
}
.tag-card h3 { font-size: 15px; font-weight: 600; color: var(--ink); margin: 0 0 12px; }
.tag-list { display: flex; flex-wrap: wrap; gap: 6px; }
.tag {
  display: inline-block; padding: 4px 14px; border-radius: 20px;
  font-size: 13px; font-weight: 500;
}
.tag.green { background: #dcfce7; color: #15803d; }
.tag.red { background: #fee2e2; color: #dc2626; }
.dim-text { font-size: 13px; color: var(--ink-dim); font-style: italic; }

/* 建议列表 */
.rec-card { padding: 18px; border: 1px solid var(--line); }
.rec-card h3 { font-size: 15px; font-weight: 600; color: var(--ink); margin: 0 0 14px; }
.rec-list { display: flex; flex-direction: column; gap: 10px; }
.rec-item { display: flex; align-items: flex-start; gap: 12px; }
.rec-priority {
  flex-shrink: 0; padding: 2px 10px; border-radius: 6px;
  font-size: 11px; font-weight: 600; margin-top: 2px;
}
.rec-priority.high { background: #fee2e2; color: #dc2626; }
.rec-priority.mid { background: #fef9c3; color: #a16207; }
.rec-priority.low { background: #dbeafe; color: #1d4ed8; }
.rec-body { flex: 1; }
.rec-action { font-size: 14px; color: var(--ink); line-height: 1.5; }
.rec-reason { font-size: 12px; color: var(--ink-dim); margin-top: 2px; }
.rec-time { flex-shrink: 0; font-size: 11px; color: var(--ink-dim); margin-top: 2px; }

/* 鼓励语 */
.encourage {
  padding: 16px 20px; border: 1px solid var(--line);
  font-size: 15px; color: var(--accent); text-align: center;
  font-weight: 500; line-height: 1.6;
}

/* 历史趋势 */
.history-card { padding: 18px; border: 1px solid var(--line); }
.history-card h3 { font-size: 15px; font-weight: 600; color: var(--ink); margin: 0 0 16px; }
.trend-chart {
  display: flex; align-items: flex-end; gap: 12px; height: 180px;
  padding-bottom: 28px; position: relative;
}
.trend-bar-wrap {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  height: 100%; justify-content: flex-end;
}
.trend-bar {
  width: 100%; max-width: 48px; background: var(--accent);
  border-radius: 6px 6px 0 0; position: relative;
  transition: height 0.5s ease;
  display: flex; align-items: flex-start; justify-content: center;
}
.trend-val {
  font-size: 12px; font-weight: 700; color: #fff;
  padding-top: 4px;
}
.trend-date {
  font-size: 10px; color: var(--ink-dim); margin-top: 6px;
  white-space: nowrap;
}

@media (max-width: 700px) {
  .eval-top { flex-direction: column; }
  .eval-tags-row { flex-direction: column; }
}
</style>
