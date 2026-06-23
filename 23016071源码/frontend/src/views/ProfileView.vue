<template>
  <div class="profile-view">
    <header class="view-header glass-panel">
      <h2 class="view-title">学习画像</h2>
      <p class="view-desc">基于对话自动构建 · 6个维度 · 随学随新</p>
      <button class="reset-btn" @click="resetProfile" title="重置画像">🔄 重置</button>
    </header>

    <div class="profile-content">
      <!-- 维度1：知识基础 -->
      <section class="profile-card glass-panel">
        <h3>📚 知识基础</h3>
        <p class="dim-desc">已掌握的知识点及程度</p>
        <div v-if="profile.knowledge_base && Object.keys(profile.knowledge_base).length" class="kb-list">
          <div v-for="(level, topic) in profile.knowledge_base" :key="topic" class="kb-item">
            <span class="kb-label">{{ topic }}</span>
            <div class="kb-bar"><div class="kb-fill" :style="{ width: (level * 100) + '%' }"></div></div>
            <span class="kb-pct">{{ Math.round(level * 100) }}%</span>
          </div>
        </div>
        <p v-else class="dim-empty">通过学习和测验来积累知识</p>
      </section>

      <!-- 维度2：认知风格 -->
      <section class="profile-card glass-panel">
        <h3>🎯 认知风格</h3>
        <p class="dim-desc">你的学习偏好方式</p>
        <span class="dim-tag purple">{{ styleLabel }}</span>
      </section>

      <!-- 维度3：易错点 -->
      <section class="profile-card glass-panel">
        <h3>⚠️ 薄弱项</h3>
        <p class="dim-desc">需要重点攻克的知识点</p>
        <div v-if="profile.weak_points?.length" class="tag-list">
          <span v-for="wp in profile.weak_points" :key="wp" class="dim-tag red">{{ wp }}</span>
        </div>
        <p v-else class="dim-empty">多做题能帮助发现薄弱项</p>
      </section>

      <!-- 维度4：学习目标 -->
      <section class="profile-card glass-panel">
        <h3>🎯 学习目标</h3>
        <p class="dim-desc">你的学习目的</p>
        <span class="dim-tag green">{{ goalLabel }}</span>
      </section>

      <!-- 维度5：学习节奏 -->
      <section class="profile-card glass-panel">
        <h3>⏱️ 学习节奏</h3>
        <p class="dim-desc">你的学习进度偏好</p>
        <span class="dim-tag blue">{{ paceLabel }}</span>
      </section>

      <!-- 维度6：兴趣方向 -->
      <section class="profile-card glass-panel">
        <h3>💡 兴趣方向</h3>
        <p class="dim-desc">你感兴趣的子领域</p>
        <div v-if="profile.interests?.length" class="tag-list">
          <span v-for="i in profile.interests" :key="i" class="dim-tag yellow">{{ i }}</span>
        </div>
        <p v-else class="dim-empty">多探索不同的学习内容来发现兴趣</p>
      </section>

      <!-- 学习统计 -->
      <section v-if="profile.total_study_time_minutes" class="profile-card glass-panel stats-card">
        <h3>📊 学习统计</h3>
        <div class="stats-grid">
          <div class="stat">
            <div class="stat-val">{{ profile.total_study_time_minutes || 0 }}</div>
            <div class="stat-label">学习分钟</div>
          </div>
          <div class="stat">
            <div class="stat-val">{{ profile.completed_topics?.length || 0 }}</div>
            <div class="stat-label">已学知识点</div>
          </div>
          <div class="stat">
            <div class="stat-val">{{ profile.quiz_history?.length || 0 }}</div>
            <div class="stat-label">测验次数</div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { apiRequest } from '../services/api';

const profile = ref({});
const loading = ref(false);

onMounted(async () => {
  loading.value = true;
  try {
    const data = await apiRequest('/api/profile');
    if (data && data.profile) profile.value = data.profile;
  } catch (e) {
    console.log('画像获取失败，先和 AI 聊聊来构建吧');
  } finally {
    loading.value = false;
  }
});

const styleLabel = computed(() => {
  const map = { visual: '视觉型 — 喜欢图表和视频', auditory: '听觉型 — 喜欢听课和讲解', kinesthetic: '动手型 — 喜欢实践和编码' };
  return map[profile.value.cognitive_style] || '未知';
});
const goalLabel = computed(() => {
  const map = { exam: '应试备考 📝', deep_understanding: '深入理解 🧠', practical: '项目实战 💪' };
  return map[profile.value.learning_goal] || '未知';
});
const paceLabel = computed(() => {
  const map = { fast: '快速推进 🚀', medium: '稳步前进 🚶', slow: '扎实慢学 🐢' };
  return map[profile.value.learning_pace] || '未知';
});

async function resetProfile() {
  try {
    await apiRequest('/api/profile/reset', { method: 'POST' });
    profile.value = {};
  } catch (e) { console.log('重置失败'); }
}
</script>

<style scoped>
.profile-view {
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
.reset-btn {
  position: absolute; right: 20px; top: 14px;
  padding: 4px 14px; border-radius: 6px; font-size: 12px;
  background: transparent; border: 1px solid rgba(255,255,255,0.15); color: rgba(255,255,255,0.50);
  cursor: pointer; transition: all 0.15s;
}
.reset-btn:hover { border-color: #e04040; color: #e04040; }
.view-header { position: relative; }

.profile-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
  align-content: start;
}
.profile-card {
  padding: 18px;
  border: 1px solid var(--line);
}
.profile-card h3 { font-size: 15px; font-weight: 600; margin: 0 0 2px; color: var(--ink); }
.dim-desc { font-size: 11px; color: var(--ink-dim); margin: 0 0 12px; }
.dim-empty { font-size: 13px; color: var(--ink-dim); font-style: italic; }

.dim-tag {
  display: inline-block;
  padding: 4px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
}
.dim-tag.purple { background: #ede9fe; color: #7c3aed; }
.dim-tag.red { background: #fee2e2; color: #dc2626; }
.dim-tag.green { background: #dcfce7; color: #15803d; }
.dim-tag.blue { background: #dbeafe; color: #1d4ed8; }
.dim-tag.yellow { background: #fef9c3; color: #a16207; }

.tag-list { display: flex; flex-wrap: wrap; gap: 6px; }

.kb-list { display: flex; flex-direction: column; gap: 8px; }
.kb-item { display: flex; align-items: center; gap: 10px; }
.kb-label { width: 100px; font-size: 12px; color: var(--ink); text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kb-bar { flex: 1; height: 6px; background: var(--hover); border-radius: 3px; overflow: hidden; }
.kb-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.3s; }
.kb-pct { width: 36px; font-size: 11px; color: var(--ink-dim); text-align: left; }

.stats-card { grid-column: 1 / -1; }
.stats-grid { display: flex; gap: 32px; margin-top: 12px; }
.stat { text-align: center; }
.stat-val { font-size: 28px; font-weight: 700; color: var(--accent); }
.stat-label { font-size: 12px; color: var(--ink-dim); margin-top: 2px; }
</style>
