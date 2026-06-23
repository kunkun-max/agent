"""数据模型定义 — 学生画像、学习资源、对话消息等核心数据结构"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ========== 对话相关 ==========

class Message(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    student_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    message: str
    agent_name: str  # 当前由哪个Agent处理
    streaming: bool = True


# ========== 学生画像（6个维度） ==========

class CognitiveStyle(str, Enum):
    VISUAL = "visual"       # 视觉型：喜欢看图、视频
    AUDITORY = "auditory"   # 听觉型：喜欢听讲解
    KINESTHETIC = "kinesthetic"  # 动手型：喜欢做实验、写代码


class LearningPace(str, Enum):
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"


class LearningGoal(str, Enum):
    EXAM = "exam"           # 应试型
    DEEP_UNDERSTANDING = "deep_understanding"  # 深入理解型
    PRACTICAL = "practical"  # 实践应用型


class StudentProfile(BaseModel):
    """6维学生画像"""
    student_id: str
    name: str = ""

    # 维度1：知识基础 — 已掌握的知识点 + 掌握程度(0-1)
    knowledge_base: dict[str, float] = Field(default_factory=dict)
    # 例：{"Python基础语法": 0.9, "机器学习": 0.3, "神经网络": 0.1}

    # 维度2：认知风格 — 视觉/听觉/动手
    cognitive_style: CognitiveStyle = CognitiveStyle.VISUAL

    # 维度3：易错点偏好 — 哪些知识点/题型容易出错
    weak_points: list[str] = Field(default_factory=list)
    # 例：["反向传播推导", "SVM数学原理"]

    # 维度4：学习目标
    learning_goal: LearningGoal = LearningGoal.DEEP_UNDERSTANDING

    # 维度5：学习节奏
    learning_pace: LearningPace = LearningPace.MEDIUM

    # 维度6：兴趣方向 — 对哪些子领域感兴趣
    interests: list[str] = Field(default_factory=list)
    # 例：["计算机视觉", "强化学习"]

    # 学习历史
    completed_topics: list[str] = Field(default_factory=list)
    quiz_history: list[dict] = Field(default_factory=list)
    # 例：[{"topic": "决策树", "score": 0.8, "wrong_types": ["计算题"]}]

    total_study_time_minutes: int = 0
    created_at: str = ""
    updated_at: str = ""


# ========== 学习资源 ==========

class ResourceType(str, Enum):
    DOC = "doc"           # 课程讲义/文档
    MINDMAP = "mindmap"   # 思维导图
    QUIZ = "quiz"         # 练习题目
    READING = "reading"   # 拓展阅读
    CODE = "code"         # 代码实操案例
    VIDEO = "video"       # 教学视频/动画
    PPT = "ppt"           # PPT课件


class LearningResource(BaseModel):
    """统一的学习资源模型"""
    resource_id: str
    resource_type: ResourceType
    title: str
    topic: str  # 所属知识点
    content: str  # Markdown内容 或 JSON字符串
    difficulty: float = 0.5  # 难度系数 0-1
    generated_by: str  # 生成该资源的Agent名称
    references: list[str] = Field(default_factory=list)  # 参考来源
    created_at: str = ""


class QuizQuestion(BaseModel):
    """单道题目"""
    question_type: str  # "choice", "fill", "short_answer", "code"
    question: str
    options: Optional[list[str]] = None  # 选择题选项
    answer: str
    explanation: str  # 解析
    difficulty: float = 0.5
    topic: str
    tags: list[str] = Field(default_factory=list)


class QuizSet(BaseModel):
    """一套练习题"""
    quiz_id: str
    title: str
    topic: str
    questions: list[QuizQuestion]
    total_difficulty: float = 0.5
    generated_by: str = ""


# ========== 学习路径 ==========

class PathNode(BaseModel):
    """学习路径中的一个节点"""
    topic: str
    order: int
    estimated_minutes: int
    prerequisites: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)  # resource_ids
    completed: bool = False


class LearningPath(BaseModel):
    """个性化学习路径"""
    path_id: str
    student_id: str
    course: str
    nodes: list[PathNode]
    total_estimated_hours: float = 0
    created_at: str = ""


# ========== 系统状态 ==========

class SystemStatus(BaseModel):
    agents: list[str]
    knowledge_base_topics: int
    active_sessions: int
    model: str
