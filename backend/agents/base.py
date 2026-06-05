"""Agent基类 — 所有智能体继承此类。

一个Agent = system_prompt（人设） + tools（工具） + memory（记忆） + LLM调用
"""

import json
from typing import AsyncGenerator, Optional
from backend.utils.llm_client import SparkLLMClient


class BaseAgent:
    """智能体基类

    使用方法：
        class MyAgent(BaseAgent):
            def __init__(self):
                super().__init__(
                    name="MyAgent",
                    system_prompt="你是一个...",
                    llm_client=llm_client
                )
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        llm_client: SparkLLMClient,
        tools: Optional[dict] = None,
        temperature: float = 0.4,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.llm = llm_client
        self.tools = tools or {}
        self.temperature = temperature
        self.memory: list[dict] = []  # 当前会话的对话历史
        self.max_memory = 20  # 最多保留多少轮对话

    def _build_messages(self, user_message: str) -> list[dict]:
        """构建发送给LLM的消息列表"""
        messages = [{"role": "system", "content": self.system_prompt}]

        # 只保留最近的N轮对话
        recent = self.memory[-self.max_memory * 2 :]
        messages.extend(recent)
        messages.append({"role": "user", "content": user_message})

        return messages

    async def chat(self, user_message: str) -> str:
        """同步对话：发送消息，获取完整回复"""
        messages = self._build_messages(user_message)
        response = await self.llm.chat(messages, temperature=self.temperature)
        self._save_memory(user_message, response)
        return response

    async def chat_stream(self, user_message: str) -> AsyncGenerator[str, None]:
        """流式对话：逐token返回回复"""
        messages = self._build_messages(user_message)
        full_response = ""
        async for chunk in self.llm.chat_stream(messages, temperature=self.temperature):
            full_response += chunk
            yield chunk
        self._save_memory(user_message, full_response)

    def _save_memory(self, user_msg: str, assistant_msg: str):
        self.memory.append({"role": "user", "content": user_msg})
        self.memory.append({"role": "assistant", "content": assistant_msg})
        # 保持记忆不超限
        if len(self.memory) > self.max_memory * 2:
            self.memory = self.memory[-self.max_memory * 2 :]

    def clear_memory(self):
        self.memory = []

    def update_system_prompt(self, new_prompt: str):
        self.system_prompt = new_prompt

    async def extract_json(self, user_message: str, schema_description: str) -> dict:
        """让Agent输出结构化JSON数据

        用于需要Agent返回结构化数据的场景（如画像提取、题目生成等）
        """
        prompt = (
            f"{user_message}\n\n"
            f"请严格按照以下JSON格式输出，不要输出其他内容：\n"
            f"{schema_description}"
        )
        response = await self.chat(prompt)
        return self._parse_json(response)

    @staticmethod
    def _parse_json(text: str) -> dict:
        """从文本中提取JSON"""
        text = text.strip()
        # 去掉可能的markdown代码块标记
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
        if text.endswith("```"):
            text = text[:-3]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            # 尝试用正则提取{}之间的内容
            import re
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return {"error": "JSON解析失败", "raw": text[:500]}
