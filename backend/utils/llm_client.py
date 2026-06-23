"""大模型客户端 — 讯飞星火大模型 HTTP API（Bearer Token 鉴权）。

接口地址：https://spark-api-open.xf-yun.com/v1/chat/completions
鉴权方式：Authorization: Bearer {APIPassword}
模型可选：lite / generalv3 / generalv3.5 / 4.0Ultra
"""

import os
import json
import asyncio
from typing import AsyncGenerator

import httpx


# 不同模型的API地址映射
MODEL_URL_MAP = {
    "spark-x": "https://spark-api-open.xf-yun.com/x2/chat/completions",
    "x2": "https://spark-api-open.xf-yun.com/x2/chat/completions",
}
DEFAULT_URL = "https://spark-api-open.xf-yun.com/x2/chat/completions"
DEFAULT_MODEL = "spark-x"


class SparkLLMClient:
    """讯飞星火大模型客户端（HTTP Bearer Token 方式）

    使用方式：
        client = SparkLLMClient(api_password="你的APIPassword")
        reply = await client.chat([{"role": "user", "content": "你好"}])
    """

    def __init__(
        self,
        api_password: str = "",
        model: str = "",
    ):
        self.api_password = api_password or os.getenv("SPARK_API_PASSWORD", "")
        self.model = model or os.getenv("SPARK_MODEL", DEFAULT_MODEL)
        self.api_url = MODEL_URL_MAP.get(self.model, DEFAULT_URL)

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.4,
        max_tokens: int = 8192,
    ) -> str:
        """同步调用：发送消息，等待完整回复"""
        if not self.api_password:
            return await self._mock_reply(messages)

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_password}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "stream": False,
                    },
                )
                if response.status_code != 200:
                    body = response.text[:500]
                    return f"[API {response.status_code}] {body}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[API调用失败] {e}"

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.4,
        max_tokens: int = 8192,
    ) -> AsyncGenerator[str, None]:
        """流式调用：逐token返回回复内容"""
        if not self.api_password:
            async for chunk in self._mock_stream(messages):
                yield chunk
            return

        try:
            # 先尝试真实流式（X2原生支持 SSE 流式）
            async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10)) as client:
                async with client.stream(
                    "POST",
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_password}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "stream": True,
                    },
                ) as response:
                    if response.status_code != 200:
                        raise Exception(f"HTTP {response.status_code}")
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            # X2 思考过程：不展示，但知道它在想
                            reasoning = delta.get("reasoning_content", "")
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except Exception:
            # 流式失败 → 降级为模拟流式（非流式请求 + 逐字输出）
            try:
                reply = await self.chat(messages, temperature, max_tokens)
                if reply.startswith("[API调用失败]") or reply.startswith("[开发模式]"):
                    yield reply
                    return
                for char in reply:
                    yield char
                    await asyncio.sleep(0.005)
            except Exception as e2:
                yield f"[流式调用失败] {e2}"

    async def _mock_reply(self, messages: list[dict]) -> str:
        result = ""
        async for chunk in self._mock_stream(messages):
            result += chunk
        return result

    async def _mock_stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """开发阶段的模拟回复（未配置API密钥时使用）"""
        last_msg = messages[-1]["content"] if messages else ""
        mock_reply = (
            f'[开发模式] 收到你的消息：「{last_msg[:100]}」。\n\n'
            f'这是模拟回复。当前消息历史共 {len(messages)} 条。\n\n'
            '请在 .env 文件中配置 SPARK_API_PASSWORD=你的APIPassword '
            '以连接星火大模型获取真实回复。'
        )
        for i, char in enumerate(mock_reply):
            yield char
            if i % 3 == 0:
                await asyncio.sleep(0.01)
