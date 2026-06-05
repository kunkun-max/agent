"""Profile Agent — 通过自然语言对话构建6维学生画像。

核心能力：
- 引导式对话：首次使用时主动提问，了解学生情况
- 特征提取：从对话中自动提取6个维度的画像信息
- 动态更新：随学随新，每次学习后更新画像
"""

import json
from backend.agents.base import BaseAgent

PROFILE_SYSTEM_PROMPT = """# 角色定位
你是科大讯飞"智学"系统的首席学习分析师，拥有10年高等教育心理学研究经验。
你的任务是：通过自然对话了解学生，构建并持续更新一份精准的学习画像。

# 六维画像体系

## 1. 知识基础 (knowledge_base)
- 记录每个知识点的掌握程度：0.0（完全不懂）→ 1.0（精通）
- 命名要具体，如"线性回归推导"而非"机器学习"
- 示例：{"Python基础语法": 0.85, "梯度下降原理": 0.3, "CNN架构": 0.15}

## 2. 认知风格 (cognitive_style)
- "visual"：偏好图表、动画、视频讲解 → 生成资源时优先用图
- "auditory"：偏好听课、语音讲解 → 资源中多加入讲述性描述
- "kinesthetic"：偏好动手、写代码、做实验 → 资源中多加入实操环节

## 3. 易错点/薄弱项 (weak_points)
- 列出学生反复出错的概念或题型
- 示例：["反向传播链式求导", "SVM对偶问题推导", "选择题粗心"]

## 4. 学习目标 (learning_goal)
- "exam"：应试导向，要快速覆盖考点
- "deep_understanding"：理论导向，追求深入理解原理
- "practical"：实战导向，看重项目实践能力

## 5. 学习节奏 (learning_pace)
- "fast"：接受能力强，可以快速推进
- "medium"：稳健学习，需要适当巩固
- "slow"：需要慢节奏、多重复

## 6. 兴趣方向 (interests)
- 学生对哪些子领域表现出浓厚兴趣
- 示例：["计算机视觉", "自然语言处理", "强化学习"]

# 对话策略

## 首次对话（画像为空时）
1. 先简单问候，营造轻松的聊天氛围
2. 自然引导了解：专业年级 → 已有基础 → 学习目标 → 学习习惯 → 兴趣方向
3. 每次只问1-2个问题，不要连续追问造成压力
4. 从学生的回答中提取关键信息

## 进行中的对话
1. 观察学生的提问深度来判断其知识水平
2. 注意学生反复出现的错误类型来更新 weak_points
3. 根据学生感兴趣的话题更新 interests
4. 如果从对话中发现了新的画像信息，用自然的语言在回复中告知学生（如"我注意到你对CV特别感兴趣"），系统会自动提取结构化数据

# 输出规范
- 语气：温暖专业，像一位经验丰富的导师，而不是冷冰冰的问卷
- 用自然语言描述学生的画像情况，**绝对不要输出JSON、代码块、或任何格式标记**
- 禁止使用 ---PROFILE---、---END---、```json 等任何技术标记
- 禁止：不要一次性列出所有问题，不要用表格询问，不要像填表一样生硬

# 防幻觉约束
- 只基于学生实际表达的对话内容来推断画像
- 不确定的维度不要强行填写，等获取到充足信息后再更新
- 不要在画像中加入学生没有提及的知识点或兴趣
- **重要**：上下文中可能包含"教材参考"或课程章节列表，这些是可供学习的课程内容，并非学生已掌握或正在学习的知识。不要将教材目录章节自动填入学生的 knowledge_base（即使填0%）——只有当学生明确提及某个知识点时，才将其加入画像。"""


class ProfileAgent(BaseAgent):
    """学生画像构建Agent"""

    def __init__(self, llm_client, **kwargs):
        super().__init__(
            name="ProfileAgent",
            system_prompt=PROFILE_SYSTEM_PROMPT,
            llm_client=llm_client,
            **kwargs,
        )
        self.current_profile: dict = {}

    def get_onboarding_questions(self) -> list[str]:
        """获取引导性问题列表"""
        return [
            "你好！我是你的专属学习助手。为了更好地帮你规划学习，我想先了解一下你的情况～\n\n首先，你目前是什么专业、大几的学生呀？",
            "了解了！那你这次想主要学习哪门课程呢？之前有没有接触过相关的知识？",
            "你平时的学习习惯是怎样的？比如喜欢看视频教程、读文档，还是更爱动手写代码？",
            "你有什么特别感兴趣的方向，或者觉得比较难啃的知识点吗？",
            "你的学习目标是什么呀？是为了准备考试、深入理解原理，还是想做项目实践？",
        ]

    def extract_profile_from_text(self, text: str) -> dict | None:
        """从对话文本中提取画像JSON"""
        if "---PROFILE---" not in text:
            return None
        try:
            start = text.index("---PROFILE---") + len("---PROFILE---")
            end = text.index("---END---", start)
            json_str = text[start:end].strip()
            return json.loads(json_str)
        except (ValueError, json.JSONDecodeError):
            return None

    async def update_profile_from_behavior(
        self, behavior_data: dict
    ) -> dict:
        """根据学习行为更新画像

        behavior_data 示例：
        {
            "topic": "反向传播",
            "quiz_score": 0.6,
            "wrong_types": ["计算题"],
            "study_time_minutes": 45,
            "interested_topics": ["CNN架构"]
        }
        """
        # 更新知识基础
        topic = behavior_data.get("topic", "")
        score = behavior_data.get("quiz_score", 0.5)
        if topic:
            old_score = self.current_profile.get("knowledge_base", {}).get(topic, 0)
            # 指数移动平均更新
            new_score = old_score * 0.7 + score * 0.3
            self.current_profile.setdefault("knowledge_base", {})[topic] = round(new_score, 2)

        # 更新易错点
        wrong_types = behavior_data.get("wrong_types", [])
        if wrong_types:
            existing = set(self.current_profile.get("weak_points", []))
            existing.update(wrong_types)
            self.current_profile["weak_points"] = list(existing)

        # 更新学习时间
        minutes = behavior_data.get("study_time_minutes", 0)
        self.current_profile["total_study_time_minutes"] = (
            self.current_profile.get("total_study_time_minutes", 0) + minutes
        )

        # 更新兴趣
        interests = behavior_data.get("interested_topics", [])
        if interests:
            existing = set(self.current_profile.get("interests", []))
            existing.update(interests)
            self.current_profile["interests"] = list(existing)

        return self.current_profile

    def get_profile_summary(self) -> str:
        """生成画像的可读摘要"""
        p = self.current_profile
        if not p:
            return "尚未构建画像"

        kb = p.get("knowledge_base", {})
        strong = [k for k, v in kb.items() if v >= 0.7]
        weak = [k for k, v in kb.items() if v < 0.4]

        return f"""📋 学习画像摘要：

**已掌握**：{', '.join(strong) if strong else '暂无'}
**需加强**：{', '.join(weak) if weak else '暂无'}
**认知风格**：{p.get('cognitive_style', '未知')}
**学习目标**：{p.get('learning_goal', '未知')}
**学习节奏**：{p.get('learning_pace', '未知')}
**兴趣方向**：{', '.join(p.get('interests', [])) if p.get('interests') else '暂无'}
**易错领域**：{', '.join(p.get('weak_points', [])) if p.get('weak_points') else '暂无'}"""
