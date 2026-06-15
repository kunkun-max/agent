<template>
  <div class="resources-view">
    <header class="view-header glass-panel">
      <h2 class="view-title">学习资源</h2>
      <p class="view-desc">多智能体协同生成 · {{ resources.length }} 份资源</p>
    </header>

    <div v-if="resources.length === 0" class="empty-state">
      <div class="empty-icon">📚</div>
      <p class="empty-title">还没有生成学习资源</p>
      <p class="empty-desc">去 AI 对话中说"帮我生成[知识点]的学习资料"</p>
      <router-link to="/learn" class="empty-link">去对话 →</router-link>
    </div>

    <div v-else class="resource-grid">
      <article
        v-for="(res, idx) in resources"
        :key="idx"
        :class="['resource-card', 'glass-panel', { active: selectedIdx === idx }]"
        @click="openCard(idx)"
      >
        <div class="card-badge" :class="res.type">{{ typeLabel(res.type).icon }} {{ typeLabel(res.type).label }}</div>
        <h3 class="card-title">{{ res.topic || res.title || '未命名资源' }}</h3>
        <p class="card-agent">由 {{ res.generated_by || res.agent }} 生成</p>
        <div class="card-preview" v-html="renderPreview(res.content)"></div>
      </article>
    </div>

    <!-- 详情面板 -->
    <Transition name="fade-slide">
      <div v-if="selectedResource && showDetail" class="detail-overlay" @click.self="showDetail = false">
        <div class="detail-panel glass-panel">
          <button class="detail-close" @click="showDetail = false">✕</button>
          <div class="detail-header">
            <span class="detail-badge" :class="selectedResource.type">
              {{ typeLabel(selectedResource.type).icon }} {{ typeLabel(selectedResource.type).label }}
            </span>
            <span class="detail-agent">生成者：{{ selectedResource.generated_by || selectedResource.agent }}</span>
          </div>
          <div class="detail-content markdown-body" v-html="renderMarkdown(selectedResource.content || '')"></div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue';
import { apiRequest } from '../services/api';
import { marked } from 'marked';
import katex from 'katex';

marked.setOptions({ breaks: true, gfm: true });

const resources = ref([]);
const selectedIdx = ref(-1);
const showDetail = ref(false);

// 页面加载时预加载 mermaid 库
if (!window._resMermaidReady) {
  window._resMermaidReady = import('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs').then((m) => {
    m.default.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'loose', suppressErrorRendering: true });
    return m.default;
  });
}

// 存储 mermaid 原始代码（key = 元素ID）
const mermaidCodeMap = {};

onMounted(async () => {
  try {
    const data = await apiRequest('/api/resources');
    resources.value = (data.resources || []).map(r => ({
      ...r,
      id: r.id,
      type: r.resource_type,
      agent: r.agent,
      generated_by: r.agent,
    }));
  } catch (e) { console.log('资源加载失败'); }
});

const selectedResource = computed(() => {
  if (selectedIdx.value < 0 || !resources.value.length) return null;
  return resources.value[selectedIdx.value];
});

const typeLabel = (type) => {
  const map = {
    doc: { label: '课程讲义', icon: '📝' },
    mindmap: { label: '思维导图', icon: '🧠' },
    quiz: { label: '练习题目', icon: '✍️' },
    reading: { label: '拓展阅读', icon: '📖' },
    code: { label: '代码案例', icon: '💻' },
    ppt: { label: 'PPT课件', icon: '📊' },
    full: { label: '全套资源', icon: '🎓' },
  };
  return map[type] || { label: type, icon: '📄' };
};

function renderPreview(content) {
  if (!content) return '';
  return content.slice(0, 200).replace(/[#*`\n]/g, ' ') + (content.length > 200 ? '...' : '');
}

function renderMarkdown(text) {
  if (!text) return '';
  try {
    let html = text;

    // 【关键】先提取 mermaid 代码块，防止 LaTeX $...$ 误匹配
    const mermaidBlocks = [];
    html = html.replace(/```mermaid\s*\n([\s\S]*?)```/g, (_, code) => {
      const id = 'res_mm_' + Math.random().toString(36).slice(2, 8);
      mermaidBlocks.push({ id, code: code.trim() });
      return `<!--MERMAID_${id}-->`;
    });

    // 块级公式
    html = html.replace(/\$\$([\s\S]*?)\$\$/g, (_, f) => {
      try { return katex.renderToString(f.trim(), { displayMode: true, throwOnError: false, strict: false }); }
      catch { return `<code>${f}</code>`; }
    });
    // 行内公式
    html = html.replace(/\$([^\s$][^$\n]*?[a-zA-Z\\\/\+\-\=\(\)\[\]\{\}][^$\n]*?)\$/g, (_, f) => {
      try { return katex.renderToString(f.trim(), { displayMode: false, throwOnError: false, strict: false }); }
      catch { return `<code>${f}</code>`; }
    });

    html = marked.parse(html);

    // 路径JSON → 渲染流程图
    html = html.replace(/<pre><code class="language-json">([\s\S]*?)<\/code><\/pre>/g, (_, code) => {
      try {
        const data = JSON.parse(code);
        if (data.nodes && Array.isArray(data.nodes)) {
          let fhtml = '<div class="flowchart">';
          for (let i = 0; i < data.nodes.length; i++) {
            const n = data.nodes[i];
            fhtml += `<div class="flowchart-layer"><div class="flowchart-node">
              <div class="flowchart-node-label">${i+1}. ${n.topic}</div>
              <div class="flowchart-node-time">~${n.estimated_minutes || '?'} 分钟</div>
            </div></div>`;
            if (i < data.nodes.length - 1) fhtml += '<div class="flowchart-arrow">↓</div>';
          }
          return fhtml + '</div>';
        }
      } catch {}
      return '';
    });

    // 把提取的 mermaid 块还原为占位 div，代码存入 JS Map
    for (const { id, code } of mermaidBlocks) {
      mermaidCodeMap[id] = code;
      html = html.replace(
        `<!--MERMAID_${id}-->`,
        `<div class="mermaid-block" id="${id}"><div class="mermaid-loading">图表生成中...</div></div>`
      );
    }

    return html;
  } catch { return text; }
}

watch(selectedIdx, (v) => {
  if (v >= 0) showDetail.value = true;
});

// 详情面板打开后，持续轮询渲染 mermaid 块，直到全部完成
watch(showDetail, (visible) => {
  if (!visible) return;
  let attempts = 0;
  const poll = () => {
    attempts++;
    const rendered = renderAllMermaid();
    if (!rendered && attempts < 30) setTimeout(poll, 100);  // 最多等3秒
  };
  setTimeout(poll, 50);
});

// 渲染所有 mermaid 块，返回 true 表示全部完成或无需渲染
function renderAllMermaid() {
  const blocks = document.querySelectorAll('.mermaid-block:not(.rendered):not(.rendering)');
  if (!blocks.length) return true;
  window._resMermaidReady?.then((mermaid) => {
    blocks.forEach((el) => {
      if (el.classList.contains('rendered') || el.classList.contains('rendering')) return;
      const code = mermaidCodeMap[el.id];
      if (!code) return;
      el.classList.add('rendering');
      mermaid.render(el.id + '_svg', code).then(({ svg }) => {
        if (svg.includes('Syntax error')) { el.classList.remove('rendering'); return; }
        el.innerHTML = svg;
        el.classList.add('rendered');
        el.classList.remove('rendering');
      }).catch(() => { el.classList.remove('rendering'); });
    });
  });
  return false;
}

function openCard(idx) {
  // 点同一张卡 → 强制关闭再打开，解决 watch 不触发的问题
  if (selectedIdx.value === idx) {
    showDetail.value = false;
    nextTick(() => { selectedIdx.value = -1; nextTick(() => { selectedIdx.value = idx; }); });
  } else {
    selectedIdx.value = idx;
  }
}

</script>

<style scoped>
.resources-view {
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

.resource-grid {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
  align-content: start;
}
.resource-card {
  padding: 16px;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid var(--line);
}
.resource-card:hover { border-color: var(--accent); transform: translateY(-2px); }
.resource-card.active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }

.card-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 8px;
}
.card-badge.doc { background: #dbeafe; color: #1d4ed8; }
.card-badge.mindmap { background: #ede9fe; color: #7c3aed; }
.card-badge.quiz { background: #ffedd5; color: #c2410c; }
.card-badge.reading { background: #dcfce7; color: #15803d; }
.card-badge.code { background: #cffafe; color: #0e7490; }
.card-badge.ppt { background: #f3e8ff; color: #7c3aed; }
.card-badge.full { background: #fef3c7; color: #d97706; }

.card-title { font-size: 15px; font-weight: 600; margin: 0 0 4px; color: var(--ink); }
.card-agent { font-size: 11px; color: var(--ink-dim); margin: 0 0 8px; }
.card-preview {
  font-size: 12px;
  color: var(--ink-dim);
  line-height: 1.5;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

/* 详情浮层 */
.detail-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  backdrop-filter: blur(4px);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.detail-panel {
  width: 100%;
  max-width: 800px;
  max-height: 80vh;
  overflow-y: auto;
  padding: 28px 32px;
  position: relative;
}
.detail-close {
  position: absolute;
  top: 16px;
  right: 16px;
  background: none;
  border: none;
  font-size: 18px;
  color: var(--ink-dim);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}
.detail-close:hover { background: var(--hover); color: var(--ink); }
.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}
.detail-badge {
  padding: 3px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}
.detail-agent { font-size: 12px; color: var(--ink-dim); }
.detail-content { font-size: 14px; line-height: 1.8; color: var(--ink); }
.detail-content :deep(h1) { font-size: 20px; font-weight: 600; margin: 16px 0 8px; color: var(--ink); border-bottom: 1px solid var(--line); padding-bottom: 6px; }
.detail-content :deep(h2) { font-size: 17px; font-weight: 600; margin: 14px 0 6px; color: var(--ink); }
.detail-content :deep(h3) { font-size: 15px; font-weight: 600; margin: 10px 0 5px; color: var(--ink); }
.detail-content :deep(p) { margin: 6px 0; }
.detail-content :deep(ul), .detail-content :deep(ol) { padding-left: 20px; margin: 6px 0; }
.detail-content :deep(li) { margin: 3px 0; }
.detail-content :deep(code) { background: var(--surface-strong); padding: 2px 6px; border-radius: 4px; font-size: 13px; color: var(--accent); }
.detail-content :deep(pre) { background: var(--hero); color: var(--ink); padding: 14px 16px; border-radius: 8px; overflow-x: auto; margin: 10px 0; font-size: 13px; border: 1px solid var(--line); }
.detail-content :deep(pre code) { background: none; padding: 0; color: var(--ink); }
.detail-content :deep(table) { border-collapse: collapse; margin: 10px 0; width: 100%; }
.detail-content :deep(th) { background: var(--surface-strong); border: 1px solid var(--line); padding: 8px 12px; text-align: left; font-weight: 600; color: var(--ink); }
.detail-content :deep(td) { border: 1px solid var(--line); padding: 6px 12px; }
.detail-content :deep(blockquote) { border-left: 3px solid var(--accent); margin: 8px 0; padding: 6px 14px; background: #1a1a1a; color: #ccc; border-radius: 0 6px 6px 0; }
.detail-content :deep(strong) { font-weight: 600; color: #fff; }
.detail-content :deep(hr) { border: none; border-top: 1px solid #333; margin: 14px 0; }
/* 流程图 */
.detail-content :deep(.flowchart) { display: flex; flex-direction: column; align-items: center; padding: 20px 0; margin: 12px 0; background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px; }
.detail-content :deep(.flowchart-layer) { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
.detail-content :deep(.flowchart-node) { background: #222; border: 1px solid #3a3a3a; border-radius: 8px; padding: 10px 18px; min-width: 120px; text-align: center; }
.detail-content :deep(.flowchart-node-label) { font-size: 13px; font-weight: 600; color: var(--ink); }
.detail-content :deep(.flowchart-node-time) { font-size: 11px; color: #888; margin-top: 4px; }
.detail-content :deep(.flowchart-arrow) { text-align: center; font-size: 20px; color: #555; padding: 4px 0; }
/* 思维导图 */
.detail-content :deep(.mermaid-block) { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px; padding: 16px; margin: 10px 0; overflow-x: auto; min-height: 60px; contain: layout; }
.detail-content :deep(.mermaid-block .mermaid-loading) { font-size: 12px; color: #888; text-align: center; padding: 20px 0; }
.detail-content :deep(.mermaid-block.rendered .mermaid-loading) { display: none; }
.detail-content :deep(.mermaid-block.rendered) { background: #151515; contain: layout; }
.detail-content :deep(.mermaid-block.rendered pre) { display: none; }
.detail-content :deep(.mermaid-block svg) { max-width: 100%; display: block; }
</style>
