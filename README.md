# 智学 — 基于大模型的个性化资源生成与学习多智能体系统

第十五届"中国软件杯"大学生软件设计大赛 — A3赛题参赛作品

## 技术架构

```
前端(React+TS) ←→ 后端(FastAPI+SSE) ←→ 多智能体系统 ←→ 星火大模型
                                         ↓
                                    ChromaDB知识库(RAG)
```

## 快速启动

### 1. 后端

```bash
cd backend
pip install -r requirements.txt

# 配置星火API密钥
cp .env.example .env
# 编辑.env填入真实密钥

# 加载课程知识库
python -c "
from backend.rag.knowledge_base import KnowledgeBase
kb = KnowledgeBase(persist_dir='./data/chroma_db')
kb.add_markdown_file('../data/ai_intro_course/01_人工智能概述.md', topic='人工智能概述')
kb.add_markdown_file('../data/ai_intro_course/02_机器学习基础.md', topic='机器学习基础')
kb.add_markdown_file('../data/ai_intro_course/03_深度学习与神经网络.md', topic='深度学习')
print(kb.get_stats())
"

# 启动服务 (端口8000)
python -m backend.main
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev   # 端口3000，自动代理API到后端
```

### 3. 打开浏览器

访问 http://localhost:3000

## 项目结构

```
├── backend/
│   ├── main.py                  # FastAPI主服务 + 所有API端点
│   ├── agents/
│   │   ├── base.py              # Agent基类
│   │   ├── orchestrator.py      # 中央调度器
│   │   ├── profile.py           # 学生画像Agent
│   │   ├── resources.py         # 资源生成Agent(Doc/Quiz/Mindmap/Reading/Code)
│   │   └── path_tutor_eval.py   # 路径规划/辅导/评估Agent
│   ├── rag/
│   │   └── knowledge_base.py    # ChromaDB知识库
│   ├── models/
│   │   └── schemas.py           # 数据模型
│   └── utils/
│       └── llm_client.py        # 星火大模型客户端
├── frontend/
│   └── src/
│       ├── App.tsx              # 主应用
│       ├── components/
│       │   ├── ChatArea.tsx     # 流式聊天界面
│       │   ├── ResourceView.tsx # 资源展示(多Tab切换)
│       │   ├── ProfilePanel.tsx # 6维学生画像面板
│       │   └── Sidebar.tsx      # 侧边导航栏
│       └── index.css            # Tailwind + 自定义样式
└── data/
    └── ai_intro_course/         # 「人工智能导论」课程知识库
        ├── 01_人工智能概述.md
        ├── 02_机器学习基础.md
        └── 03_深度学习与神经网络.md
```

## 智能体架构

本项目实现了9个专职Agent：

| Agent | 角色 | 核心能力 |
|-------|------|---------|
| Orchestrator | 中央调度器 | 意图识别 → 路由分发 → 结果聚合 |
| ProfileAgent | 学习分析师 | 对话式6维学生画像构建 |
| DocAgent | 课程讲师 | 个性化Markdown讲义生成 |
| MindmapAgent | 知识架构师 | Mermaid思维导图生成 |
| QuizAgent | 出题老师 | 多类型练习题生成(含解析) |
| ReadingAgent | 研究馆员 | 拓展阅读推荐 |
| CodeAgent | 编程导师 | 代码实操案例生成 |
| PathAgent | 教育规划师 | 知识图谱驱动学习路径规划 |
| TutorAgent | 助教 | 多模态答疑辅导 |
| EvalAgent | 评估专家 | 学习效果动态评估 |

## 防幻觉机制

1. RAG检索增强生成：所有内容生成前从ChromaDB知识库检索相关材料
2. 溯源引用：生成内容标注参考来源
3. 内容安全过滤：输入/输出双向审查

## 开源协议

本项目仅供学习和参赛使用。
使用了以下开源项目：
- FastAPI (MIT)
- React (MIT)
- Tailwind CSS (MIT)
- ChromaDB (Apache 2.0)
- react-markdown (MIT)
