<template>
  <div class="learn-view">
    <header class="view-header">
      <h2 class="view-title">AI 学习助手</h2>
      <p class="view-desc">多智能体协同 · 个性化资源生成</p>
      <label class="wallpaper-btn" title="更换壁纸">
        🖼️ 壁纸
        <input type="file" accept="image/*" @change="onWallpaperChange" hidden />
      </label>
    </header>

    <div class="msg-list" ref="msgListRef">
      <div v-if="historyLoading" class="history-loading">加载更多消息中...</div>
      <div v-else-if="historyFullyLoaded && messages.length > 1" class="history-loaded">已加载全部消息</div>
      <div v-if="messages.length <= 1" class="empty-chat">
        发送消息，开始你的个性化学习之旅～
      </div>
      <div
        v-for="(msg, idx) in messages"
        :key="msg.id"
        :class="['msg-row', msg.isUser ? 'user' : 'assistant']"
      >
        <div :class="['msg-bubble', msg.isUser ? 'user' : 'assistant']">
          <template v-if="!msg.isUser">
            <div v-if="isWaiting(msg)" class="thinking-dots">
              <span></span><span></span><span></span>
            </div>
            <div v-else :class="['msg-html', { collapsed: getCollapsed(msg) && !streaming }]" v-html="renderMarkdown(msg.text)"></div>
            <div v-if="!msg.isUser && isLongMsg(msg) && !streaming" class="collapse-bar" @click="toggleCollapse(msg)">
              {{ (msg._collapsed === undefined ? true : msg._collapsed) ? '展开全文 ▼' : '收起 ▲' }}
            </div>
          </template>
          <div v-else class="msg-text">{{ msg.text }}</div>
        </div>
      </div>
      <div ref="msgEndRef"></div>
      <button :class="['scroll-bottom-btn', { visible: showScrollBtn }]" @click="scrollBottom()" title="回到底部">↓</button>
    </div>

    <div class="quick-actions">
      <button v-for="act in quickActions" :key="act.label" class="quick-btn" @click="input = act.msg; focusInput()">
        {{ act.label }}
      </button>
    </div>

    <div class="composer">
      <textarea ref="inputRef" v-model="input" class="composer-input" :placeholder="placeholder"
        rows="1" @keydown="onKeydown" @input="autoResize"></textarea>
      <button class="send-btn" :disabled="!input.trim() || streaming" @click="send">
        {{ streaming ? '···' : '发送' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onBeforeUnmount } from 'vue';
import { apiStreamReader, apiRequest, isLoggedIn } from '../services/api';
import { useAppStore } from '../composables/useAppStore';
import { marked } from 'marked';
import katex from 'katex';
import 'katex/dist/katex.min.css';

marked.setOptions({ breaks: true, gfm: true });

const store = useAppStore();
const SESSION_ID = 'sess_' + Date.now();

const DEFAULT_WELCOME = { id: 'welcome', text: '你好！我是你的专属学习助手 🎓\n\n我可以帮你：\n- 📝 生成个性化课程讲义\n- 🧠 绘制知识思维导图\n- ✍️ 出练习题巩固知识\n- 📖 推荐拓展阅读材料\n- 💻 提供代码实操案例\n- 🗺️ 规划科学学习路径\n\n先和我聊聊，让我了解一下你的学习情况吧～', isUser: false };

const messages = ref([DEFAULT_WELCOME]);

// ===== 分页加载聊天记录 =====
const historyTotal = ref(0);
const historyOffset = ref(0);
const historyLoading = ref(false);
const historyFullyLoaded = ref(false);
const PAGE_SIZE = 30;

async function loadHistory() {
  if (!isLoggedIn()) return;
  try {
    const data = await apiRequest(`/api/chat/history?limit=${PAGE_SIZE}&offset=0`);
    if (data.messages && data.messages.length > 0) {
      messages.value = data.messages.map(m => ({
        id: m.id, text: m.text, isUser: m.role === 'user',
      }));
      historyTotal.value = data.total || 0;
      historyOffset.value = data.messages.length;
      if (historyOffset.value >= historyTotal.value) historyFullyLoaded.value = true;
    }
  } catch {}
}

async function loadMoreHistory() {
  if (historyLoading.value || historyFullyLoaded.value || !isLoggedIn()) return;
  historyLoading.value = true;
  try {
    const el = msgListRef.value;
    const prevHeight = el ? el.scrollHeight : 0;
    const data = await apiRequest(`/api/chat/history?limit=${PAGE_SIZE}&offset=${historyOffset.value}`);
    if (data.messages && data.messages.length > 0) {
      const older = data.messages.map(m => ({
        id: m.id, text: m.text, isUser: m.role === 'user',
      }));
      messages.value = [...older, ...messages.value];
      historyOffset.value += data.messages.length;
      // 保持滚动位置不跳动
      nextTick(() => {
        if (el) el.scrollTop = el.scrollHeight - prevHeight;
      });
      if (historyOffset.value >= (data.total || 0)) historyFullyLoaded.value = true;
    } else {
      historyFullyLoaded.value = true;
    }
  } catch {}
  historyLoading.value = false;
}

// 保存单条消息到后端（带重试）
async function saveToServer(role, text, retries = 2) {
  if (!isLoggedIn() || !text) return;
  for (let i = 0; i <= retries; i++) {
    try {
      await apiRequest('/api/chat/history', { method: 'POST', body: { role, text } });
      return; // 成功
    } catch (e) {
      console.error(`[HISTORY] 保存失败 (${role}, 第${i+1}次):`, e.message);
      if (i < retries) await new Promise(r => setTimeout(r, 500));
    }
  }
}

const input = ref('');
const streaming = ref(false);
const msgListRef = ref(null);
const msgEndRef = ref(null);
const showScrollBtn = ref(false);
const inputRef = ref(null);
const placeholder = ref('输入你的问题或学习需求...');
// 缓存已渲染的 Mermaid SVG，避免 Vue 重渲染时丢失
let _mmReady = null;
function getMermaid() {
  if (!_mmReady) {
    _mmReady = import('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs').then(function(m) {
      m.default.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'loose', suppressErrorRendering: true });
      return m.default;
    }).catch(function() { _mmReady = null; return null; });
  }
  return _mmReady;
}
const mermaidCache = ref({});
window.__mermaidCache = mermaidCache.value;

// 流结束后自动渲染所有未渲染的 mermaid 块
function autoRenderMermaid() {
  const blocks = document.querySelectorAll('.mermaid-block:not(.rendered):not(.rendering)');
  if (!blocks.length) return;
  const mm = getMermaid();
  if (!mm) return;
  mm.then(function(mermaid) {
    blocks.forEach(function(block) {
      if (block.classList.contains('rendered') || block.classList.contains('rendering')) return;
      const btn = block.querySelector('.mermaid-render-btn');
      if (!btn) return;
      const rawCode = btn.dataset.mermaidCode;
      if (!rawCode) return;
      block.classList.add('rendering');
      const blockId = block.id;
      mermaid.render(blockId + '_svg', rawCode).then(function(r) {
        if (r.svg.indexOf('Syntax error') >= 0) { block.classList.remove('rendering'); return; }
        block.innerHTML = r.svg;
        block.classList.add('rendered');
        block.classList.remove('rendering');
        block.style.cursor = 'zoom-in';
        if (window.__mermaidCache) window.__mermaidCache[rawCode.trim()] = r.svg;
        block.onclick = function() {
          var o = document.getElementById('_zoom_overlay');
          if (!o) { o = document.createElement('div'); o.id = '_zoom_overlay'; o.style = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.88);display:flex;align-items:center;justify-content:center;cursor:zoom-out'; o.onclick = function() { o.remove(); }; document.body.appendChild(o); }
          o.innerHTML = '';
          var b = document.createElement('div'); b.style = 'padding:32px;background:#151515;border-radius:12px;max-width:95vw;max-height:90vh;overflow:auto';
          b.innerHTML = this.outerHTML; b.querySelector('svg').style = 'min-width:70vw;min-height:60vh;max-width:100%;height:auto';
          o.appendChild(b);
        };
      }).catch(function() { block.classList.remove('rendering'); });
    });
  });
}

const quickActions = [
  { label: '📝 生成讲义', intent: 'generate_doc', msg: '[INTENT:generate_doc]帮我生成一份关于[知识点]的课程讲义' },
  { label: '🧠 思维导图', intent: 'generate_mindmap', msg: '[INTENT:generate_mindmap]帮我画一张[知识点]的思维导图' },
  { label: '✍️ 练习题', intent: 'generate_quiz', msg: '[INTENT:generate_quiz]给我出几道关于[知识点]的练习题' },
  { label: '💻 代码案例', intent: 'generate_code', msg: '[INTENT:generate_code]给我一个[知识点]的代码实操案例' },
  { label: '📊 PPT课件', intent: 'generate_ppt', msg: '[INTENT:generate_ppt]帮我做一份关于[知识点]的PPT课件' },
  { label: '🎓 全套资源', intent: 'generate_all', msg: '[INTENT:generate_all]帮我全面学习[知识点]，生成全套资料' },
  { label: '🗺️ 学习路径', intent: 'plan_path', msg: '[INTENT:plan_path]帮我规划学习路径' },
];

// ---------- 打字机状态 ----------
let typingTimer = null;           // setInterval 句柄
let currentTypingMsgObj = null;   // 当前正在打字的消息对象
let currentFullText = '';         // 完整文本（持续增长）
let currentCharIdx = 0;           // 已打出字符数
const isTypingActive = ref(false);
const activeTypingMsgId = ref(null);

// ---------- 打字机核心 ----------
function startTyping(msgObj) {
  stopTyping(true);
  currentTypingMsgObj = msgObj;
  currentCharIdx = 0;
  isTypingActive.value = true;
  activeTypingMsgId.value = msgObj.id;

  // 用 Array.from 正确处理中文等多字节字符
  const chars = Array.from(msgObj._raw || '');

  typingTimer = setInterval(() => {
    const latest = Array.from(currentTypingMsgObj._raw || '');
    currentFullText = latest.join('');
    if (currentCharIdx < latest.length) {
      // 每次输出4-6个字符，加速显示
      const step = Math.min(5, latest.length - currentCharIdx);
      currentTypingMsgObj.text = latest.slice(0, currentCharIdx + step).join('');
      currentCharIdx += step;
    }
    if (!streaming.value && currentCharIdx >= latest.length) {
      finishTyping();
    }
  }, 10);
}

function stopTyping(complete) {
  if (typingTimer) { clearInterval(typingTimer); typingTimer = null; }
  if (currentTypingMsgObj && complete && currentFullText) {
    currentTypingMsgObj.text = currentFullText;
    scrollBottom();
  }
  currentTypingMsgObj = null;
  currentFullText = '';
  currentCharIdx = 0;
  isTypingActive.value = false;
  activeTypingMsgId.value = null;
}

function finishTyping() {
  if (typingTimer) { clearInterval(typingTimer); typingTimer = null; }
  if (currentTypingMsgObj) {
    currentTypingMsgObj.text = currentTypingMsgObj._raw || '';
    currentTypingMsgObj._raw = '';
    currentTypingMsgObj = null;
  }
  currentFullText = '';
  currentCharIdx = 0;
  isTypingActive.value = false;
  activeTypingMsgId.value = null;
  scrollBottom();
}

function isWaiting(msg) {
  if (!streaming.value) return false;
  return msg.id === activeTypingMsgId.value
    && (!msg._raw || msg._raw.length === 0 || (msg.text || '').length === 0);
}

function isLongMsg(msg) {
  const text = msg._raw || msg.text || '';
  return text.length > 800;
}

function toggleCollapse(msg) {
  if (msg._collapsed === undefined) msg._collapsed = false;
  else msg._collapsed = !msg._collapsed;
}

function getCollapsed(msg) {
  // 长文本默认折叠，用户可展开
  if (msg._collapsed !== undefined) return msg._collapsed;
  return isLongMsg(msg); // 默认折叠
}

// ---------- 发送消息 ----------
async function send() {
  const msg = input.value.trim();
  if (!msg || streaming.value) return;
  input.value = '';
  streaming.value = true;

  // 用户消息（显示时去掉意图标签）
  const displayMsg = msg.replace(/^\[INTENT:\w+\]\s*/, '');
  messages.value.push({ id: 'u' + Date.now(), text: displayMsg, isUser: true });
  await saveToServer('user', msg);

  // 优先从前端快捷按钮提取意图标签
  let detectedIntent = 'chat';
  let detectedTopic = '';
  const tagMatch = msg.match(/^\[INTENT:(\w+)\]/);
  if (tagMatch) {
    detectedIntent = tagMatch[1];
    // 保留 [INTENT:xxx] 标签发给后端，让Layer1正则直接命中
  }

  const assistantMsg = { id: 'a' + Date.now(), text: '', isUser: false, _raw: '' };
  messages.value.push(assistantMsg);
  const msgObj = messages.value[messages.value.length - 1];
  startTyping(msgObj);
  scrollBottom();

  try {
    const reader = await apiStreamReader('/api/chat/stream', {
      session_id: SESSION_ID,
      message: msg,
    });
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
            // 流结束，获取意图
            if (detectedIntent === 'chat') detectedIntent = parsed.intent || 'chat';
            if (!detectedTopic) detectedTopic = parsed.topic || '';
            continue;
          }
          if (parsed.__replace__) {
            // 后端发来去掉标记的干净版本，同步更新打字机
            if (msgObj._raw !== undefined) msgObj._raw = parsed.content;
            currentFullText = parsed.content;
            if (currentCharIdx > parsed.content.length) {
              currentCharIdx = parsed.content.length;
              msgObj.text = parsed.content;
            }
            continue;
          }
          // 过滤意图元数据（正则 + includes双保险）
          if (parsed.content && typeof parsed.content === 'string') {
            const s = parsed.content;
            if (/___INTENT_META___/.test(s) || /INTENT_?_?:/.test(s) || s.includes('INTENT:')) {
              const m = s.match(/INTENT_?_?:(\w+):([\s\S]*?)__/);
              if (m) {
                if (detectedIntent === 'chat') detectedIntent = m[1];
                if (!detectedTopic) detectedTopic = (m[2] || '').trim();
              }
              continue;
            }
          }
          if (parsed.content && msgObj._raw !== undefined) {
            // 过滤内部元数据（后端已过滤，前端兜底）
            const cleanChunk = parsed.content.replace(/___INTENT_META___\{[^}]*\}/g, '');
            if (cleanChunk) msgObj._raw += cleanChunk;
          }
        } catch {}
      }
    }
  } catch (err) {
    msgObj._raw = `出错了：${err.message}`;
  } finally {
    streaming.value = false;
    // 流结束后自动渲染所有未渲染的 mermaid 块（流式分块可能导致正则匹配不到）
    nextTick(() => { autoRenderMermaid(); });
    // AI回复存到后端（去除画像标记）
    const cleanText = (msgObj._raw || '').replace(/---PROFILE---[\s\S]*?---END---/g, '').replace(/___INTENT_META___\{[^}]*\}/g, '').trim();
    console.log('[SAVE-DEBUG] raw_len=%d clean_len=%d intent=%s', msgObj._raw?.length, cleanText.length, detectedIntent);
    if (cleanText) {
      await saveToServer('assistant', cleanText);
      console.log('[SAVE-DEBUG] assistant 保存完成');
    } else {
      console.warn('[SAVE-DEBUG] cleanText 为空，跳过保存！');
    }
    // 保存学习资源：Orchestrator判断意图 → 对应Agent生成 → 按类型保存
    if (['generate_doc','generate_mindmap','generate_quiz','generate_code','generate_reading','generate_ppt','generate_all'].includes(detectedIntent)) {
      if (detectedIntent === 'generate_all') {
        // 全套资源：保存完整原始内容（含所有Agent的输出段）
        if (msgObj._raw && msgObj._raw.length > 120) {
          try {
            await apiRequest('/api/resources/save', { method: 'POST', body: {
              resource_type: 'full', topic: detectedTopic, title: (detectedTopic || '学习资料') + ' - 全套资源',
              content: msgObj._raw, agent: '多Agent协同',
            }});
            console.log('[RESOURCE] 全套资源已保存');
          } catch (e) { console.error('[RESOURCE] 全套资源保存失败:', e.message); }
        }
      } else {
        // 单类型资源：按意图对应的类型保存
        const type = { generate_doc:'doc', generate_mindmap:'mindmap', generate_quiz:'quiz', generate_code:'code', generate_reading:'reading', generate_ppt:'ppt' }[detectedIntent];
        if (type && cleanText && cleanText.length > 120) {
          const agent = { generate_doc:'DocAgent', generate_mindmap:'MindmapAgent', generate_quiz:'QuizAgent', generate_code:'CodeAgent', generate_reading:'ReadingAgent', generate_ppt:'PPTAgent' }[detectedIntent] || 'AI助手';
          try {
            await apiRequest('/api/resources/save', { method: 'POST', body: {
              resource_type: type, topic: detectedTopic, agent,
              title: detectedTopic + ' - ' + typeLabel(type), content: cleanText,
            }});
            console.log('[RESOURCE] %s 已保存 (intent=%s)', type, detectedIntent);
          } catch (e) { console.error('[RESOURCE] %s 保存失败:', type, e.message); }
        }
      }
    }
    // 学习路径：提取JSON并保存到 /api/path
    if (detectedIntent === 'plan_path' && msgObj._raw) {
      try {
        const raw = msgObj._raw;
        let jsonStr = raw;
        const m = raw.match(/```json\s*([\s\S]*?)```/);
        if (m) jsonStr = m[1];
        else {
          const m2 = raw.match(/\{[\s\S]*"nodes"[\s\S]*\}/);
          if (m2) jsonStr = m2[0];
        }
        const pathData = JSON.parse(jsonStr.trim());
        if (pathData.nodes && Array.isArray(pathData.nodes)) {
          try {
            await apiRequest('/api/path/save', { method: 'POST', body: pathData });
            console.log('[PATH] 学习路径已保存，节点数:', pathData.nodes.length);
          } catch (e) { console.error('[PATH] 保存失败:', e.message); }
        }
      } catch (e) { console.log('[PATH] 解析失败:', e.message); }
    }
  }
}

function typeLabel(type) {
  return { doc: '课程讲义', mindmap: '思维导图', quiz: '练习题目', reading: '拓展阅读', code: '代码案例', ppt: 'PPT课件' }[type] || type;
}

// 自定义壁纸（仅当前会话生效，刷新恢复默认）
function onWallpaperChange(e) {
  const file = e.target.files[0];
  if (!file) return;
  const url = URL.createObjectURL(file);
  applyWallpaper(url);
}
function applyWallpaper(url) {
  const el = document.querySelector('.wallpaper');
  if (el) el.style.backgroundImage = `url(${url})`;
}

// ---------- 辅助 ----------
function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
}
function autoResize() {
  const el = inputRef.value; if (!el) return;
  el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}
function focusInput() { nextTick(() => inputRef.value?.focus()); }
function scrollBottom() {
  showScrollBtn.value = false;
  nextTick(() => {
    msgEndRef.value?.scrollIntoView({ block: 'end' });
  });
}

function renderMarkdown(text) {
  if (!text) return '';
  try {
    // 先渲染 LaTeX，避免被 marked 转义
    let html = text;
    // 【关键】先提取 mermaid 代码块，防止 LaTeX $...$ 误匹配
    const mermaidPlaceholders = [];
    html = html.replace(/```mermaid\s*\n([\s\S]*?)```/g, (_, code) => {
      const key = '__MERMAID_' + mermaidPlaceholders.length + '__';
      mermaidPlaceholders.push(code);
      return key;
    });
    // 块级公式 $$...$$
    html = html.replace(/\$\$([\s\S]*?)\$\$/g, (_, formula) => {
      try { return katex.renderToString(formula.trim(), { displayMode: true, throwOnError: false, strict: false }); }
      catch { return `<code>${formula}</code>`; }
    });
    // 行内公式 $...$（严格匹配：排除中文和金额符号，要求含字母或运算符）
    html = html.replace(/\$([^\s$][^$\n]*?[a-zA-Z\\\/\+\-\=\(\)\[\]\{\}][^$\n]*?)\$/g, (_, formula) => {
      try { return katex.renderToString(formula.trim(), { displayMode: false, throwOnError: false, strict: false }); }
      catch { return `<code>${formula}</code>`; }
    });
    // 还原 mermaid 占位符
    mermaidPlaceholders.forEach((code, i) => {
      html = html.replace('__MERMAID_' + i + '__', '```mermaid\n' + code + '```');
    });
    // 先在marked.parse前提取路径JSON（避免引号被转义导致解析失败）
    let pathNodes = null;
    html = html.replace(/```json\s*([\s\S]*?)```/g, (_, code) => {
      try {
        const data = JSON.parse(code.trim());
        if (data.nodes && Array.isArray(data.nodes)) {
          pathNodes = data.nodes;
          return '';
        }
      } catch {}
      return _;
    });
    html = marked.parse(html);
    if (pathNodes) {
      html += renderPathChart(pathNodes);
    }
    // 其他JSON数据块 → 隐藏
    html = html.replace(/<pre><code class="language-json">[\s\S]*?<\/code><\/pre>/g, '');
    // Mermaid 图 — 点击按钮渲染为SVG，缓存避免滚动丢失
    html = html.replace(/<pre><code class="language-mermaid">([\s\S]*?)<\/code><\/pre>/g, (_, code) => {
      // 流程图块由路径JSON渲染，跳过不显示按钮
      if (/^\s*(flowchart|graph)\s/.test(code)) {
        return '';
      }
      var key = code.trim();
      var cached = window.__mermaidCache ? window.__mermaidCache[key] : null;
      var id = "mermaid_" + Math.random().toString(36).slice(2, 8);
      var escCode = code.replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/\n/g, "\\n");
      var htmlCode = code.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      if (cached) {
        nextTick(function() {
          var el = document.getElementById(id);
          if (el) { el.innerHTML = cached; el.classList.add("rendered"); el.style.cursor = "zoom-in"; }
        });
        return '<div class="mermaid-block rendered" id="' + id + '" style="cursor:zoom-in" onclick="var o=document.getElementById(\'_zoom_overlay\');if(!o){o=document.createElement(\'div\');o.id=\'_zoom_overlay\';o.style=\'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.88);display:flex;align-items:center;justify-content:center;cursor:zoom-out\';o.onclick=function(){o.remove()};document.body.appendChild(o)}o.innerHTML=\'\';var b=document.createElement(\'div\');b.style=\'padding:32px;background:#151515;border-radius:12px;max-width:95vw;max-height:90vh;overflow:auto\';b.innerHTML=this.querySelector(\'svg\').outerHTML.replace(\'<svg\',\'<svg style=min-width:70vw;min-height:60vh;max-width:100%;height:auto\');o.appendChild(b)"></div>';
      }
      return '<div class="mermaid-block" id="' + id + '">' +
        '<pre><code>' + htmlCode + '</code></pre>' +
        '<button class="mermaid-render-btn" data-mermaid-id="' + id + '" data-mermaid-code="' + htmlCode + '">🖼 渲染图表</button>' +
        '</div>';
    });
    return html;
  } catch { return text; }
}

// ===== 路径图：从JSON nodes数组直接渲染CSS盒子 =====
function renderPathChart(nodes) {
  if (!nodes || nodes.length === 0) return '';
  let html = '<div class="learning-path">';
  html += '<div class="lp-header"><span class="lp-title">🗺️ 学习路径</span><span class="lp-badge">● 共' + nodes.length + '个单元</span></div>';
  html += '<div class="lp-units">';
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    html += '<div class="lp-card">';
    html += '<div class="lp-card-num">' + (i + 1) + '</div>';
    html += '<div class="lp-card-title">' + n.topic + '</div>';
    html += '<div class="lp-card-meta"><span>⏱ ' + (n.estimated_minutes || '?') + '分钟</span></div>';
    html += '<div class="lp-card-goal">' + (n.goal || '') + '</div>';
    html += '</div>';
    // SVG 箭头
    if (i < nodes.length - 1) {
      html += '<div class="lp-arrow"><svg viewBox="0 0 48 20"><line x1="4" y1="10" x2="34" y2="10" class="lp-arrow-line"/><polygon points="34,4 44,10 34,16" class="lp-arrow-head"/></svg></div>';
    }
  }
  html += '</div>';
  html += '</div>';
  return html;
}

// ===== 路径图专用：纯CSS盒子+箭头 =====
function renderFlowchart(code) {
  // 流程图（flowchart/graph）→ 盒子+箭头
  const lines = code.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('flowchart') && !l.startsWith('graph'));
  const nodes = {};  // { id: { label, children: [] } }
  const roots = new Set();
  const children = new Set();

  for (const line of lines) {
    // 解析 "1[标签] --> 2[标签]" 或 "1 --> 2"
    const parts = line.split(/-->|---|->/);
    if (parts.length < 2) continue;

    const parseNode = (s) => {
      s = s.trim();
      const m = s.match(/^(\w+)\[(.+)\]$/);
      if (m) return { id: m[1], label: m[2].replace(/<br\s*\/?>/g, '\n') };
      return { id: s, label: s };
    };

    const from = parseNode(parts[0]);
    const to = parseNode(parts[1]);

    if (!nodes[from.id]) nodes[from.id] = { label: from.label, children: [] };
    else if (from.label !== from.id) nodes[from.id].label = from.label;
    if (!nodes[to.id]) nodes[to.id] = { label: to.label, children: [] };
    else if (to.label !== to.id) nodes[to.id].label = to.label;

    nodes[from.id].children.push(to.id);
    roots.add(from.id);
    children.add(to.id);
  }

  // 找出根节点（没有父节点的）
  const rootIds = [...roots].filter(id => !children.has(id));
  if (rootIds.length === 0 && Object.keys(nodes).length > 0) rootIds.push(Object.keys(nodes)[0]);

  // BFS 分层布局
  const visited = new Set();
  const layers = [];
  let current = rootIds;
  while (current.length > 0) {
    layers.push(current);
    const next = [];
    for (const id of current) {
      if (visited.has(id)) continue;
      visited.add(id);
      for (const child of (nodes[id]?.children || [])) {
        if (!visited.has(child)) next.push(child);
      }
    }
    current = [...new Set(next)];
  }

  // 渲染为 HTML
  let html = '<div class="flowchart">';
  for (let i = 0; i < layers.length; i++) {
    html += '<div class="flowchart-layer">';
    for (const id of layers[i]) {
      const node = nodes[id];
      if (!node) continue;
      const labelLines = node.label.split('\n');
      html += `<div class="flowchart-node">
        <div class="flowchart-node-label">${labelLines[0]}</div>
        ${labelLines[1] ? `<div class="flowchart-node-time">${labelLines[1]}</div>` : ''}
      </div>`;
    }
    html += '</div>';
    // 层间箭头
    if (i < layers.length - 1) {
      html += '<div class="flowchart-arrow">↓</div>';
    }
  }
  html += '</div>';
  return html;
}

onMounted(async () => {
  await loadHistory();
  scrollBottom();
  // 监听滚动：距离底部超过200px时显示"回到底部"按钮
  nextTick(() => {
    const el = msgListRef.value;
    if (el) {
      el.addEventListener('scroll', () => {
        showScrollBtn.value = (el.scrollHeight - el.scrollTop - el.clientHeight) > 200;
        // 滚动到顶部附近 → 加载更多历史
        if (el.scrollTop < 80 && !historyLoading.value && !historyFullyLoaded.value) {
          loadMoreHistory();
        }
      }, { passive: true });
      // 委托：Mermaid 渲染按钮
      el.addEventListener('click', (e) => {
        const btn = e.target.closest('.mermaid-render-btn');
        if (!btn) return;
        e.preventDefault();
        const blockId = btn.dataset.mermaidId;
        const block = document.getElementById(blockId);
        if (!block || block.classList.contains('rendered') || block.classList.contains('rendering')) return;
        block.classList.add('rendering');
        const rawCode = btn.dataset.mermaidCode;
        const mm = getMermaid();
        if (!mm) return;
        mm.then(function(mermaid) {
          return mermaid.render(blockId + '_svg', rawCode);
        }).then(function(r) {
          if (r.svg.indexOf('Syntax error') >= 0) { block.classList.remove('rendering'); return; }
          block.innerHTML = r.svg;
          block.classList.add('rendered');
          block.classList.remove('rendering');
          block.style.cursor = 'zoom-in';
          block.scrollIntoView({ block: 'nearest', behavior: 'instant' });
          if (window.__mermaidCache) window.__mermaidCache[rawCode.trim()] = r.svg;
          block.onclick = function() {
            var o = document.getElementById('_zoom_overlay');
            if (!o) { o = document.createElement('div'); o.id = '_zoom_overlay'; o.style = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.88);display:flex;align-items:center;justify-content:center;cursor:zoom-out'; o.onclick = function() { o.remove(); }; document.body.appendChild(o); }
            o.innerHTML = '';
            var b = document.createElement('div'); b.style = 'padding:32px;background:#151515;border-radius:12px;max-width:95vw;max-height:90vh;overflow:auto';
            b.innerHTML = this.outerHTML; b.querySelector('svg').style = 'min-width:70vw;min-height:60vh;max-width:100%;height:auto';
            o.appendChild(b);
          };
        }).catch(function() { block.classList.remove('rendering'); });
      });
      }
  });
});
onBeforeUnmount(() => { stopTyping(true); });
</script>

<style scoped>
.learn-view { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.msg-list { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 16px 24px; display: flex; flex-direction: column; gap: 10px; }
.view-header {
  background: #1a1a1a;
  padding: 10px 24px; border-bottom: 1px solid #2a2a2a;
  display: flex; align-items: center; gap: 16px;
  background: #1a1a1a;
}
.view-title { font-size: 16px; font-weight: 500; color: rgba(255,255,255,0.92); margin: 0; }
.view-desc { font-size: 11px; color: rgba(255,255,255,0.50); margin: 2px 0 0; }
.wallpaper-btn {
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); color: rgba(255,255,255,0.50);
  padding: 4px 14px; border-radius: 20px; font-size: 12px; cursor: pointer;
  transition: all 0.15s; margin-left: auto;
}
.wallpaper-btn:hover { border-color: var(--accent); color: rgba(255,255,255,0.92); }

.empty-chat { text-align: center; color: rgba(255,255,255,0.50); padding: 60px 20px; font-size: 14px; }
.history-loading, .history-loaded {
  text-align: center; padding: 10px; font-size: 12px; color: rgba(255,255,255,0.40);
}

.msg-list { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 16px 24px; display: flex; flex-direction: column; gap: 10px; }
.msg-list::-webkit-scrollbar { width: 6px; }
.msg-list::-webkit-scrollbar-track { background: transparent; }
.msg-list::-webkit-scrollbar-thumb { background: #444; border-radius: 3px; }
/* 滚动到底部按钮 */
.scroll-bottom-btn {
  position: sticky; bottom: 12px; left: calc(100% - 52px);
  width: 36px; height: 36px; border-radius: 50%;
  background: var(--accent); color: #fff; border: none;
  font-size: 18px; cursor: pointer; z-index: 10;
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  opacity: 0; transform: scale(0.8) translateY(8px);
  transition: opacity 0.25s ease, transform 0.25s ease;
  pointer-events: none;
}
.scroll-bottom-btn.visible {
  opacity: 1; transform: scale(1) translateY(0); pointer-events: auto;
}
.scroll-bottom-btn.visible:hover { opacity: 0.85; transform: scale(1.05) translateY(0); }

.msg-row { display: flex; max-width: 84%; }
.msg-row.user { align-self: flex-end; }
.msg-row.assistant { align-self: flex-start; }

.msg-bubble { padding: 12px 18px; border-radius: 12px; font-size: 15px; line-height: 1.75; font-weight: 380; overflow-wrap: break-word; word-break: break-word; }
.msg-bubble.user { background: var(--accent); color: #fff; border-bottom-right-radius: 4px; }
.msg-bubble.assistant { background: #0d0d2b; color: rgba(255,255,255,0.92); border: 1px solid rgba(255,255,255,0.10); border-bottom-left-radius: 4px; }
.msg-text { white-space: pre-wrap; color: rgba(255,255,255,0.92); }
.msg-html { color: rgba(255,255,255,0.92); word-break: break-word; }
.msg-html :deep(h1) { font-size: 20px; font-weight: 600; margin: 14px 0 8px; color: #fff; border-bottom: 1px solid #333; padding-bottom: 6px; }
.msg-html :deep(h2) { font-size: 17px; font-weight: 600; margin: 12px 0 6px; color: rgba(255,255,255,0.92); }
.msg-html :deep(h3) { font-size: 15px; font-weight: 600; margin: 10px 0 5px; color: rgba(255,255,255,0.92); }
.msg-html :deep(p) { margin: 6px 0; line-height: 1.75; }
.msg-html :deep(ul), .msg-html :deep(ol) { padding-left: 20px; margin: 6px 0; }
.msg-html :deep(li) { margin: 3px 0; line-height: 1.7; }
.msg-html :deep(code) { background: rgba(255,255,255,0.10); padding: 2px 6px; border-radius: 4px; font-size: 13px; color: var(--accent); font-family: "JetBrains Mono", monospace; }
.msg-html :deep(pre) { background: #010120; color: rgba(255,255,255,0.92); padding: 14px 16px; border-radius: 8px; overflow-x: auto; margin: 10px 0; font-size: 13px; border: 1px solid rgba(255,255,255,0.10); }
.msg-html :deep(pre code) { background: none; padding: 0; color: rgba(255,255,255,0.92); font-size: 13px; }
/* 流程图 */
.msg-html :deep(.flowchart) {
  display: flex; flex-direction: column; align-items: center;
  padding: 20px 0; margin: 12px 0;
  background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px;
}
.msg-html :deep(.flowchart-layer) {
  display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;
}
.msg-html :deep(.flowchart-node) {
  background: #222; border: 1px solid #3a3a3a; border-radius: 8px;
  padding: 10px 18px; min-width: 120px; text-align: center;
}
.msg-html :deep(.flowchart-node-label) {
  font-size: 13px; font-weight: 600; color: #e0e0e0;
}
.msg-html :deep(.flowchart-node-time) {
  font-size: 11px; color: #888; margin-top: 4px;
}
.msg-html :deep(.flowchart-node-goal) {
  font-size: 11px; color: #666; margin-top: 4px; max-width: 200px;
  line-height: 1.4;
}
.msg-html :deep(.flowchart-arrow) {
  text-align: center; font-size: 20px; color: #555; padding: 4px 0;
}
/* Mermaid 图（思维导图等） */
.msg-html :deep(.mermaid-block) { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); border-radius: 8px; padding: 12px; margin: 10px 0; overflow-x: auto; }
.msg-html :deep(.mermaid-block .mermaid-render-btn) {
  display: block; margin: 8px auto 0; padding: 5px 16px;
  background: var(--accent); color: #fff; border: none; border-radius: 6px;
  font-size: 12px; cursor: pointer;
}
.msg-html :deep(.mermaid-block.rendering .mermaid-render-btn) { display: none; }
.msg-html :deep(.mermaid-block.rendered) { background: rgba(255,255,255,0.06); padding: 16px; }
.msg-html :deep(.mermaid-block.rendered pre) { display: none; }
.msg-html :deep(.mermaid-block.rendered .mermaid-render-btn) { display: none; }
.msg-html :deep(.mermaid-block svg) { max-width: 100%; display: block; }
/* 学习路径卡片 */
.msg-html :deep(.learning-path) { border: 1px solid rgba(255,255,255,0.10); border-radius: 12px; padding: 20px; margin: 12px 0; }
.msg-html :deep(.lp-header) { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.msg-html :deep(.lp-title) { font-size: 15px; font-weight: 600; color: rgba(255,255,255,0.92); }
.msg-html :deep(.lp-badge) { font-size: 11px; color: rgba(255,255,255,0.50); background: var(--accent-soft); padding: 2px 8px; border-radius: 10px; }
.msg-html :deep(.lp-units) { display: flex; align-items: center; gap: 0; overflow-x: auto; padding-bottom: 8px; }
.msg-html :deep(.lp-card) { width: 170px; padding: 14px; border-radius: 12px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); text-align: center; flex-shrink: 0; }
.msg-html :deep(.lp-card-num) { font-size: 20px; font-weight: 700; color: rgba(255,255,255,0.50); margin-bottom: 6px; }
.msg-html :deep(.lp-card-title) { font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.92); margin-bottom: 6px; }
.msg-html :deep(.lp-card-meta) { font-size: 11px; color: rgba(255,255,255,0.50); margin-bottom: 4px; }
.msg-html :deep(.lp-card-goal) { font-size: 10px; color: rgba(255,255,255,0.50); margin-bottom: 0; line-height: 1.4; }
.msg-html :deep(.lp-arrow) { width: 44px; flex-shrink: 0; display: flex; align-items: center; }
.msg-html :deep(.lp-arrow svg) { width: 100%; height: 20px; }
.msg-html :deep(.lp-arrow-line) { stroke: var(--ink-dim); stroke-width: 2; }
.msg-html :deep(.lp-arrow-head) { fill: var(--ink-dim); }
.msg-html :deep(.lp-tip) { font-size: 11px; color: rgba(255,255,255,0.50); margin-top: 14px; text-align: center; }
@media (max-width: 640px) { .msg-html :deep(.lp-units) { flex-direction: column; } .msg-html :deep(.lp-arrow) { transform: rotate(90deg); width: 24px; height: 32px; margin: -2px 0; } }
/* 流程图 */
.msg-html :deep(.flowchart) { display: flex; flex-direction: column; align-items: center; padding: 20px 0; margin: 12px 0; background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px; cursor: zoom-in; }
.msg-html :deep(blockquote) { border-left: 3px solid var(--accent); margin: 8px 0; padding: 6px 14px; background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.50); border-radius: 0 6px 6px 0; }
.msg-html :deep(table) { border-collapse: collapse; margin: 10px 0; width: 100%; }
.msg-html :deep(th) { background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.10); padding: 8px 12px; text-align: left; font-weight: 600; color: rgba(255,255,255,0.92); }
.msg-html :deep(td) { border: 1px solid #2a2a2a; padding: 6px 12px; }
.msg-html :deep(tr:nth-child(even)) { background: #141414; }
.msg-html :deep(strong) { font-weight: 600; color: rgba(255,255,255,0.92); }
.msg-html :deep(hr) { border: none; border-top: 1px solid #333; margin: 14px 0; }
.msg-html.collapsed { max-height: 320px; overflow: hidden; position: relative; }
.msg-html.collapsed::after {
  content: ''; position: absolute; bottom: 0; left: 0; right: 0;
  height: 50px; background: linear-gradient(transparent, #1e1e1e);
  pointer-events: none;
}
.collapse-bar {
  text-align: center; color: rgba(255,255,255,0.50); font-size: 12px; cursor: pointer;
  padding: 4px 0; border-top: 1px solid #2a2a2a; margin-top: 8px;
  transition: color 0.15s;
}
.collapse-bar:hover { color: rgba(255,255,255,0.92); }
.msg-html :deep(a) { color: var(--accent); text-decoration: underline; }
.msg-html :deep(img) { max-width: 100%; border-radius: 6px; }
.msg-html :deep(em) { color: rgba(255,255,255,0.50); }

.thinking-dots { display: flex; gap: 4px; padding: 6px 0; }
.thinking-dots span { width: 6px; height: 6px; border-radius: 50%; background: #666; animation: dot-bounce 1.2s infinite ease-in-out; }
.thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes dot-bounce { 0%, 80%, 100% { transform: translateY(0); opacity: 0.4; } 40% { transform: translateY(-6px); opacity: 1; } }

.quick-actions { display: flex; gap: 8px; padding: 8px 24px; overflow-x: auto; border-top: 1px solid rgba(255,255,255,0.10); background: #010120; }
.quick-btn { white-space: nowrap; padding: 5px 14px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.10); background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.50); font-size: 12px; cursor: pointer; transition: all 0.15s; font-weight: 400; }
.quick-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }

.composer { display: flex; gap: 10px; padding: 12px 24px; align-items: flex-end; border-top: 1px solid #2a2a2a; background: #1a1a1a; }
.composer-input { flex: 1; resize: none; border: 1px solid rgba(255,255,255,0.12); border-radius: 10px; padding: 9px 14px; font-size: 14px; font-family: inherit; background: #010120; color: rgba(255,255,255,0.95); outline: none; max-height: 120px; font-weight: 400; }
.composer-input:focus { border-color: var(--accent); }
.composer-input::placeholder { color: rgba(255,255,255,0.50); }
.send-btn { padding: 9px 20px; border-radius: 10px; border: none; background: var(--accent); color: #fff; font-size: 14px; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.send-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.send-btn:not(:disabled):hover { opacity: 0.85; }
</style>
