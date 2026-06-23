"""内容安全过滤器

输入检测：拦截用户不当消息
输出检测：拦截AI生成的不当内容
"""

import re
import json
import os

JSON_PATH = os.path.join(os.path.dirname(__file__), "sensitive_words.json")


class ContentSafetyFilter:
    """内容安全过滤器"""

    def __init__(self):
        self.words: dict[str, list[str]] = {}
        self._load_words()

    def _load_words(self):
        """加载敏感词库"""
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                self.words = json.load(f)
        except Exception:
            self.words = {}

    def _normalize(self, text: str) -> str:
        """标准化文本：去除特殊字符干扰（空格、标点等绕过手段）"""
        # 去掉常见的绕过字符
        text = re.sub(r'[\s​‌‍﻿]+', '', text)
        # 去掉标点分隔
        text = re.sub(r'[\.\s,，。、·`\'\"\\|/]+', '', text)
        return text.lower()

    def check_input(self, text: str) -> tuple[bool, str]:
        """检查用户输入

        Returns:
            (is_safe, reason) — 安全返回 (True, "")，不安全返回 (False, 原因)
        """
        if not text or not self.words:
            return True, ""

        normalized = self._normalize(text)

        # 遍历所有类别
        for category, word_list in self.words.items():
            for word in word_list:
                pattern = self._normalize(word)
                # 跳过过短的词（≤2字），避免 "av" "3p" "sm" 等双字符误伤正常内容
                if not pattern or len(pattern) < 3:
                    continue
                if pattern in normalized:
                    print(f"[SAFETY] 输入拦截: pattern='{pattern}' category={category} input='{text[:50]}'")
                    category_cn = {
                        "political": "政治敏感",
                        "porn": "低俗/色情",
                        "violence": "暴力/恐怖",
                        "illegal": "违法违规",
                        "injection": "Prompt注入",
                        "privacy": "隐私相关",
                    }.get(category, category)
                    return False, f"消息包含{category_cn}内容，已被拦截"

        # 额外检查：连续大量重复字符（刷屏攻击）
        if re.search(r'(.)\1{20,}', text):
            return False, "消息包含大量重复字符，已被拦截"

        return True, ""

    def check_output(self, text: str) -> tuple[bool, str]:
        """检查AI输出（比输入宽松：词边界匹配 + 至少2个不同词命中才拦截）"""
        if not text or not self.words:
            return True, text

        lower_text = text.lower()
        high_risk = ["political", "porn", "violence", "illegal"]
        hits = set()

        for category in high_risk:
            for word in self.words.get(category, []):
                pattern = self._normalize(word)
                if not pattern or len(pattern) < 3:
                    continue
                # 用词边界匹配，避免 "学习" 误伤包含 "学" 的正常内容
                if re.search(r'\b' + re.escape(pattern) + r'\b', lower_text):
                    hits.add(category)

        # 至少 2 个不同类别命中才拦截（降低误杀率）
        if len(hits) >= 2:
            return False, "该回复因内容安全策略已被拦截，请换个方式提问"

        return True, text

    def reload(self):
        """热重载词库（开发调试时使用）"""
        self._load_words()


# 全局单例
safety_filter = ContentSafetyFilter()
