"""Orchestrator — 中央调度器，负责意图识别和多Agent协作调度。

工作流程：
1. 收到用户消息
2. 用LLM判断意图（生成讲义？出题？答疑？画像更新？）
3. 路由到对应的Agent
4. 返回响应
"""

import json
import os
from typing import AsyncGenerator
from backend.utils.llm_client import SparkLLMClient
from backend.agents.base import BaseAgent


class Orchestrator(BaseAgent):
    """中央调度Agent — 理解用户意图，协调所有子Agent"""

    def __init__(self, llm_client: SparkLLMClient, **kwargs):
        super().__init__(
            name="Orchestrator",
            system_prompt=self._build_system_prompt(),
            llm_client=llm_client,
            **kwargs,
        )
        self.sub_agents: dict[str, BaseAgent] = {}

    def register_agent(self, agent: BaseAgent):
        """注册子Agent"""
        self.sub_agents[agent.name] = agent

    @staticmethod
    def _build_system_prompt() -> str:
        return """# 角色
你是智学系统的中央调度器，负责分析用户消息并路由到最合适的Agent。

# 意图类型与匹配规则

## generate_all（多Agent全套资源）— 优先级最高
**匹配关键词**：全套/全面/完整/系统学习/所有资料/同时/全部/一并/都
**匹配模式**：
- "帮我全面学习XXX"/"系统学习XXX"/"XXX的全套资料"
- 用户在一句话中同时要求2种以上资源（如"讲义和题目都给我"）
- "把XXX的所有学习资料都生成出来"

## generate_doc（课程讲义）
**匹配关键词**：讲义/文档/笔记/教程/讲解/解释/介绍一下/是什么/怎么理解
**匹配模式**：
- "帮我写一份XXX的讲义"/"生成XXX课程笔记"/"讲讲XXX"
- 用户要求系统性了解某个知识点，期望得到结构化文档
- "XXX是什么"（期望详细解释，不是简单一句话）

## generate_mindmap（思维导图）
**匹配关键词**：思维导图/脑图/知识图谱/知识框架/结构图/梳理/整理一下
**匹配模式**：
- "画XXX的思维导图"/"XXX的知识框架"/"帮我梳理XXX"

## generate_quiz（练习题）
**匹配关键词**：题/练习/考试/测验/测试/刷题/检验/巩固
**匹配模式**：
- "出几道XXX的题"/"XXX的练习题"/"我想检测一下XXX掌握程度"
- 注意区分：纯粹问"这道题怎么做"应归为tutor

## generate_code（代码案例）
**匹配关键词**：代码/编程/写一个/实现/跑一下/demo/实操/动手/案例
**匹配模式**：
- "给个XXX的代码示例"/"怎么用Python实现XXX"/"写一个XXX的程序"

## generate_ppt（PPT课件）
**匹配关键词**：PPT/课件/幻灯片/ppt/演示文稿/教学课件
**匹配模式**：
- "帮我做一份XXX的PPT"/"生成XXX的课件"/"XXX的演示文稿"
- "把XXX做成幻灯片"/"给XXX做个ppt"

## generate_reading（拓展阅读）
**匹配关键词**：推荐/阅读/书籍/论文/文献/资料/课外/拓展/进阶
**匹配模式**：
- "推荐XXX相关书籍"/"XXX有哪些好的学习资料"/"XXX的论文推荐"

## profile（画像构建/更新）— 自我介绍类，优先级高
**关键判断**：用户以"我"开头描述自身情况 → 一定是 profile
**匹配模式**：
- "我是大二学生"/"我在学Python"/"我的基础一般"
- "我喜欢动手写代码"/"我节奏比较慢"/"我稳扎稳打"
- "我是为了考试"/"我目标是找工作"/"我想考研"
- **原则**：只要是在说自己，就是profile；不是在学习资料请求

## plan_path（学习路径）
**关键判断**：用户明确请求系统为其规划学习顺序
**匹配模式**：
- "帮我规划一下学习路径"/"我应该按什么顺序学"
- "零基础从哪里开始"/"给我一条学习路线"
- **注意**："稳扎稳打""慢慢来"只是描述风格，不是路径请求

## tutor（答疑辅导）
**关键判断**：用户遇到具体问题需要即时解答
**匹配模式**：
- "XXX和YYY有什么区别"/"为什么反向传播要算梯度"
- "我不懂梯度下降是什么意思"/"能用一个例子解释CNN吗"

## evaluate（学习评估）
**匹配关键词**：评估一下/给我一个评估/检查学习效果/我的学习报告/测试一下水平/我学了多久
**匹配模式**：
- 用户明确要求系统评估其学习情况
- "帮我评估一下现在的学习进度"/"检查一下我掌握得怎么样"
- **注意**：用户陈述自身情况（如"我是来考试的"）不是评估请求，应归为 profile

## chat（普通闲聊）
**匹配模式**：
- 问候语（"你好""在吗"）
- 感谢（"谢谢"）
- 简短回应，没有任何学习相关意图
- 如果无法确定意图，默认归为chat

# 输出规则
1. 严格只返回JSON，不要任何其他文字
2. topic字段：提取用户想学的具体知识点名称，如"反向传播""CNN""支持向量机"
3. 如果用户没提具体知识点，topic留空：""
4. confidence字段：你的分类信心（0.5-1.0）

# 输出格式
{"intent": "generate_doc", "topic": "反向传播", "confidence": 0.95}"""

    async def classify_intent(self, user_message: str) -> dict:
        """意图分类：前端标签 → LLM精准匹配"""
        import re

        # 第1层：前端快捷按钮 [INTENT:xxx] → 直接命中
        tag_match = re.match(r'^\[INTENT:(\w+)\]', user_message)
        if tag_match:
            intent = tag_match.group(1)
            clean = re.sub(r'^\[INTENT:\w+\]\s*', '', user_message)
            return {"intent": intent, "topic": self._extract_topic(clean), "confidence": 1.0}

        # 第2层：LLM匹配（隔离记忆，不影响对话）
        saved_memory = self.memory
        self.memory = []
        try:
            return await self.extract_json(
                f"用户消息：{user_message}\n\n请判断意图并返回JSON。",
                '{"intent": "意图类型", "topic": "知识点", "confidence": 0.9}'
            )
        finally:
            self.memory = saved_memory

    @staticmethod
    def _extract_topic(msg: str) -> str:
        """从消息中提取知识点"""
        import re
        # 先去掉前端意图标签，避免误匹配
        clean = re.sub(r'^\[INTENT:\w+\]\s*', '', msg)
        for p in [
            r'\[(.+?)\]',                          # [深度学习] [Python] 等方括号
            r'关于[「「](.+?)[」」]',                # 关于「机器学习」
            r'学习[「「](.+?)[」」]',                # 学习「Python」
            r'全面学习[「「]?(.+?)[」」]?(?:[，,、]|生成|的|$)',  # 全面学习深度学习
            r'系统学习[「「]?(.+?)[」」]?(?:[，,、]|生成|的|$)',  # 系统学习Python
            r'知识点[：:\s]*(\S{2,30})',             # 知识点：CNN
        ]:
            m = re.search(p, clean)
            if m:
                topic = m.group(1).strip()
                if topic and len(topic) >= 2:
                    return topic
        return ""

    async def route_and_execute(
        self, user_message: str, student_profile: dict = None
    ) -> AsyncGenerator[str, None]:
        """路由消息到合适的Agent并流式返回结果"""
        intent_info = await self.classify_intent(user_message)
        intent = intent_info.get("intent", "chat")
        topic = intent_info.get("topic", "")
        # 通过实例属性传递意图，避免chunk解析问题
        self._last_intent = intent
        self._last_topic = topic

        # 意图元数据，后端解析用，键名故意避开常见词
        yield "___INTENT_META___" + json.dumps({"intent": intent, "topic": topic})

        # 构建包含画像信息和知识库参考的上下文
        context_msg = user_message
        if student_profile:
            parts = []
            if student_profile.get('knowledge_base'):
                parts.append(f"知识基础：{student_profile['knowledge_base']}")
            if student_profile.get('cognitive_style'):
                parts.append(f"认知风格：{student_profile['cognitive_style']}")
            if student_profile.get('weak_points'):
                parts.append(f"弱项：{student_profile['weak_points']}")
            if student_profile.get('_kb_hint'):
                parts.append(f"（可用课程资料，非学生已掌握知识）：{student_profile['_kb_hint']}")
            if parts:
                context_msg = f"[背景]\n" + "\n".join(parts) + f"\n\n[用户消息]\n{user_message}"

        # 路由映射
        agent = self._route_intent(intent)

        # 多Agent协同：一键生成全套资源
        if intent == "generate_all" and topic:
            yield f"🎓 多Agent协同工作中...\n\n"
            multi_agents = [
                ("DocAgent", "📝 生成课程讲义"),
                ("MindmapAgent", "🧠 绘制思维导图"),
                ("QuizAgent", "✍️ 出练习题"),
                ("CodeAgent", "💻 代码实操案例"),
                ("ReadingAgent", "📖 拓展阅读推荐"),
                ("PPTAgent", "📊 生成PPT课件"),
            ]
            for agent_name, prefix in multi_agents:
                ag = self.sub_agents.get(agent_name)
                if not ag: continue
                yield f"**{prefix}**  \n"
                prompt = f"请为知识点「{topic}」生成学习资源。学生画像：{json.dumps(student_profile or {}, ensure_ascii=False)}"
                async for chunk in ag.chat_stream(prompt):
                    yield chunk
                yield "\n\n---\n\n"
            return

        if agent is None:
            # 无匹配Agent → 切到对话模式，不暴露JSON分类结果
            old_prompt = self.system_prompt
            old_memory = self.memory.copy()
            self.memory = []
            self.system_prompt = "你是一个友好的AI学习助手。请用自然对话回复用户，不要输出JSON格式。"
            try:
                async for chunk in self.chat_stream(user_message):
                    yield chunk
            finally:
                self.system_prompt = old_prompt
                self.memory = old_memory
            return


        # 如果有指定主题，优先传递给Agent
        if topic:
            context_msg = f"重点关注知识点：{topic}\n\n{context_msg}"
        elif self.memory:
            recent = "\n".join([
                f"[{'用户' if m['role']=='user' else 'AI'}]：{m['content'][:300]}"
                for m in self.memory[-6:]
            ])
            context_msg = f"[最近对话记录，供你理解上下文]\n{recent}\n\n{context_msg}"

        # PPTAgent 特殊处理：不流式输出JSON，只显示生成状态 + 下载链接
        if intent == "generate_ppt":
            yield "📊 正在为你生成PPT课件...\n\n"
            full = ""
            context_msg = f"请为知识点「{topic}」生成一份PPT课件。必须包含2-3页可运行的代码示例（code字段），每条bullet写60-100字含具体语法/函数名。学生画像：{json.dumps(student_profile or {}, ensure_ascii=False)}\n\n{context_msg}"
            async for chunk in agent.chat_stream(context_msg):
                full += chunk
            try:
                import re
                from backend.utils.pptx_builder import build_pptx
                json_match = re.search(r'```json\s*([\s\S]*?)```', full)
                json_str = (json_match.group(1) if json_match else full).strip()
                # 修复常见 JSON 语法问题
                json_str = re.sub(r',\s*}', '}', json_str)
                json_str = re.sub(r',\s*]', ']', json_str)
                json_str = re.sub(r'\n\s*}', '\n}', json_str)
                # 多层尝试解析
                ppt_data = None
                for attempt in range(4):
                    try:
                        ppt_data = json.loads(json_str)
                        break
                    except json.JSONDecodeError:
                        if attempt == 0:
                            def _esc(m):
                                return m.group().replace('\n', '\\n').replace('\t', '\\t').replace('\r', '')
                            json_str = re.sub(r'"[^"]*"', _esc, json_str)
                        elif attempt == 1:
                            # 替换 JSON 特有语法为 Python 语法
                            json_str = re.sub(r':\s*true\b', ': True', json_str)
                            json_str = re.sub(r':\s*false\b', ': False', json_str)
                            json_str = re.sub(r':\s*null\b', ': None', json_str)
                        elif attempt == 2:
                            import ast
                            ppt_data = ast.literal_eval(json_str)
                            break
                if ppt_data is None:
                    raise Exception("JSON解析失败，请重试")
                if ppt_data.get("slides"):
                    filepath = build_pptx(ppt_data)
                    filename = os.path.basename(filepath)
                    slide_count = len(ppt_data["slides"])
                    yield f"✅ PPT课件已生成！共 **{slide_count}** 页\n\n"
                    yield f"📥 **[下载PPT课件：{ppt_data.get('title', '课件')}](/api/ppt/download/{filename})**\n"
                else:
                    yield "⚠️ PPT内容生成失败，请稍后重试\n"
            except Exception as e:
                yield f"⚠️ PPT课件生成失败：{str(e)[:100]}\n"
            return

        async for chunk in agent.chat_stream(context_msg):
            yield chunk

    def _route_intent(self, intent: str) -> BaseAgent | None:
        """根据意图路由到子Agent"""
        routing = {
            "profile": "ProfileAgent",
            "generate_doc": "DocAgent",
            "generate_mindmap": "MindmapAgent",
            "generate_quiz": "QuizAgent",
            "generate_reading": "ReadingAgent",
            "generate_code": "CodeAgent",
            "generate_ppt": "PPTAgent",
            "plan_path": "PathAgent",
            "tutor": "TutorAgent",
            "evaluate": "EvalAgent",
            "generate_all": "__MULTI__",  # 多Agent协同
        }
        agent_name = routing.get(intent)
        if agent_name == "__MULTI__":
            return None  # 特殊标记，在 route_and_execute 中处理
        return self.sub_agents.get(agent_name) if agent_name else None

    async def generate_all_resources(
        self, topic: str, student_profile: dict = None
    ) -> dict:
        """多Agent协同：为一个知识点生成全套学习资源

        多个Agent并行（或串行）工作，生成讲义、导图、题目、阅读、代码
        """
        profile_str = json.dumps(student_profile, ensure_ascii=False) if student_profile else ""

        tasks = {
            "doc": self.sub_agents.get("DocAgent"),
            "mindmap": self.sub_agents.get("MindmapAgent"),
            "quiz": self.sub_agents.get("QuizAgent"),
            "reading": self.sub_agents.get("ReadingAgent"),
            "code": self.sub_agents.get("CodeAgent"),
        }

        results = {}
        for key, agent in tasks.items():
            if agent is None:
                continue
            prompt = (
                f"请为知识点「{topic}」生成学习资源。"
                f"学生画像：{profile_str}"
            )
            try:
                results[key] = await agent.chat(prompt)
            except Exception as e:
                results[key] = f"生成失败：{e}"

        return results
