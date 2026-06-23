"""RAG知识库 — 基于ChromaDB的向量检索，为防幻觉提供知识支撑。

工作流程：
1. 加载文档 → 2. 切分文本块 → 3. Embedding向量化 → 4. 存入ChromaDB → 5. 检索
"""

import os
import hashlib
from typing import Optional

# 使用轻量方案：如果sentence-transformers不可用，回退到简单的TF-IDF
try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


class KnowledgeBase:
    """课程知识库 — 文档存储与检索"""

    def __init__(self, persist_dir: str = "./data/chroma_db"):
        self.persist_dir = persist_dir
        self.documents: list[dict] = []  # 内存中的文档列表（降级方案）
        self.embedding_model = None
        self.chroma_client = None
        self.collection = None

        self._init_embedding()
        self._init_chroma()

    def _init_embedding(self):
        """初始化Embedding模型（超时10秒，失败则降级为关键词检索）"""
        if not HAS_SENTENCE_TRANSFORMERS:
            return
        # 支持跳过模型下载（国内网络不通时用）
        if os.getenv("SKIP_EMBEDDING", "").lower() in ("1", "true", "yes"):
            print("[KB] SKIP_EMBEDDING=1，跳过模型下载，使用关键词检索")
            return
        try:
            import concurrent.futures
            # 在子线程中加载，10秒超时
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    SentenceTransformer,
                    "paraphrase-multilingual-MiniLM-L12-v2",
                )
                self.embedding_model = future.result(timeout=10)
            print("[KB] Embedding模型加载成功")
        except Exception as e:
            print(f"[KB] Embedding模型加载失败({type(e).__name__})，将使用关键词检索")

    def _init_chroma(self):
        """初始化ChromaDB"""
        if HAS_CHROMADB:
            try:
                os.makedirs(self.persist_dir, exist_ok=True)
                self.chroma_client = chromadb.PersistentClient(
                    path=self.persist_dir,
                    settings=Settings(anonymized_telemetry=False),
                )
                self.collection = self.chroma_client.get_or_create_collection(
                    name="course_knowledge",
                    metadata={"description": "课程知识库"},
                )
                print("[KB] ChromaDB初始化成功")
            except Exception as e:
                print(f"[KB] ChromaDB初始化失败: {e}，将使用内存检索")

    def add_document(self, content: str, metadata: dict) -> str:
        """添加文档到知识库

        Args:
            content: 文档文本内容
            metadata: 元数据 {"title": "", "topic": "", "source": "", "chapter": ""}

        Returns:
            doc_id: 文档ID
        """
        doc_id = hashlib.md5(content.encode()).hexdigest()[:16]

        # 存入内存
        self.documents.append({
            "id": doc_id,
            "content": content,
            "metadata": metadata,
        })

        # 存入ChromaDB
        if self.collection is not None:
            chunks = self._split_text(content, chunk_size=500, overlap=50)
            for i, chunk in enumerate(chunks):
                chunk_id = f"{doc_id}_{i}"
                try:
                    self.collection.add(
                        ids=[chunk_id],
                        documents=[chunk],
                        metadatas=[{
                            **metadata,
                            "chunk_index": i,
                            "total_chunks": len(chunks),
                            "doc_id": doc_id,
                        }],
                    )
                except Exception as e:
                    print(f"[KB] 添加文档块失败: {e}")

        return doc_id

    def add_markdown_file(self, filepath: str, topic: str = "") -> list[str]:
        """从Markdown文件加载文档到知识库

        解析Markdown中的 ## 标题作为文档切分依据
        """
        if not os.path.exists(filepath):
            print(f"[KB] 文件不存在: {filepath}")
            return []

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        title = os.path.basename(filepath).replace(".md", "")
        doc_ids = []

        # 按 ## 标题切分
        sections = content.split("\n## ")
        for i, section in enumerate(sections):
            if not section.strip():
                continue

            # 提取章节标题
            lines = section.split("\n")
            section_title = lines[0].strip("# ").strip()
            section_content = "\n".join(lines)

            if i == 0 and not section.startswith("#"):
                # 第一个section可能是前言，用文件名作为标题
                section_title = title

            doc_id = self.add_document(
                content=section_content,
                metadata={
                    "title": title,
                    "topic": topic or title,
                    "source": filepath,
                    "chapter": section_title,
                },
            )
            doc_ids.append(doc_id)

        print(f"[KB] 从 {filepath} 加载了 {len(doc_ids)} 个文档块")
        return doc_ids

    def search(self, query: str, top_k: int = 5, topic_filter: str = "") -> list[dict]:
        """检索与query最相关的文档片段

        Args:
            query: 查询文本
            top_k: 返回最相关的K个结果
            topic_filter: 可选的主题过滤

        Returns:
            [{"content": "...", "metadata": {...}, "score": 0.95}, ...]
        """
        results = []

        # 优先用ChromaDB检索
        if self.collection is not None and self.collection.count() > 0:
            where_filter = None
            if topic_filter:
                where_filter = {"topic": topic_filter}

            try:
                chroma_results = self.collection.query(
                    query_texts=[query],
                    n_results=top_k,
                    where=where_filter,
                )
                for i, doc_id in enumerate(chroma_results["ids"][0]):
                    results.append({
                        "content": chroma_results["documents"][0][i],
                        "metadata": chroma_results["metadatas"][0][i],
                        "score": 1.0 - chroma_results["distances"][0][i]
                        if chroma_results.get("distances") else 0.5,
                    })
                return results
            except Exception as e:
                print(f"[KB] ChromaDB检索失败: {e}，回退到关键词检索")

        # 降级方案：简单的关键词匹配
        return self._keyword_search(query, top_k)

    def _keyword_search(self, query: str, top_k: int = 5) -> list[dict]:
        """简单的关键词匹配检索（无需embedding模型）"""
        keywords = set(query.lower().split())
        scored = []
        for doc in self.documents:
            content_lower = doc["content"].lower()
            # 计算关键词命中率
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > 0:
                scored.append({
                    "content": doc["content"][:1000],
                    "metadata": doc["metadata"],
                    "score": score / len(keywords),
                })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def search_with_embedding(self, query: str, top_k: int = 5) -> list[dict]:
        """使用本地embedding模型进行语义检索"""
        if self.embedding_model is None:
            return self.search(query, top_k)

        query_vec = self.embedding_model.encode(query).tolist()
        scored = []
        for doc in self.documents:
            doc_vec = self.embedding_model.encode(doc["content"][:1000]).tolist()
            similarity = self._cosine_sim(query_vec, doc_vec)
            scored.append({
                "content": doc["content"][:1000],
                "metadata": doc["metadata"],
                "score": similarity,
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _cosine_sim(a: list, b: list) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x ** 2 for x in a) ** 0.5
        norm_b = sum(x ** 2 for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _split_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """简单的文本切分：按段落+长度切分"""
        paragraphs = text.split("\n\n")
        chunks = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) < chunk_size:
                current += para + "\n\n"
            else:
                if current:
                    chunks.append(current.strip())
                current = para + "\n\n"
        if current:
            chunks.append(current.strip())
        return chunks

    def get_stats(self) -> dict:
        """获取知识库统计信息"""
        chroma_count = self.collection.count() if self.collection else 0
        return {
            "total_documents": len(self.documents),
            "chroma_chunks": chroma_count,
            "persist_dir": self.persist_dir,
            "has_embedding": self.embedding_model is not None,
        }

    def get_context_for_query(self, query: str, top_k: int = 3) -> str:
        """获取检索上下文，用于拼接到LLM的prompt中"""
        results = self.search(query, top_k)
        if not results:
            return ""

        context_parts = []
        for i, r in enumerate(results):
            source = r["metadata"].get("chapter", r["metadata"].get("title", "未知来源"))
            context_parts.append(
                f"[参考{i+1} - {source}]\n{r['content'][:800]}"
            )
        return "\n\n---\n\n".join(context_parts)
