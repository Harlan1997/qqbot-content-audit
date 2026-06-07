"""
AI 审核引擎 - 基于 SiliconFlow (Qwen2-VL)
负责文本关键词匹配 + 图片/表情包 AI 识别
"""

import re
import json
import asyncio
import base64
from io import BytesIO
from typing import Optional

import aiohttp
from nonebot import logger
from openai import AsyncOpenAI
from PIL import Image

try:
    from pypinyin import lazy_pinyin as _lazy_pinyin
except ImportError:
    _lazy_pinyin = None

from .config import ModConfig
from .models import ModerationResult, ViolationType


class ContentModerator:
    """内容审核器"""

    def __init__(self, config: ModConfig):
        self.config = config
        self._client: Optional[AsyncOpenAI] = None
        self._compiled_patterns: list[re.Pattern] = []
        self._init_patterns()

    def _init_patterns(self):
        """预编译正则表达式"""
        for pattern in self.config.blocked_patterns:
            try:
                self._compiled_patterns.append(
                    re.compile(pattern, re.IGNORECASE)
                )
            except re.error as e:
                logger.warning(f"无效的正则模式 '{pattern}': {e}")

    @property
    def client(self) -> AsyncOpenAI:
        """懒加载 OpenAI 客户端"""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.config.gemini_api_key, # 重用这个字段作为 API KEY
                base_url="https://api.siliconflow.cn/v1"
            )
        return self._client

    # ========================================
    # 文本审核
    # ========================================

    def check_text(self, text: str) -> ModerationResult:
        """
        检查文本是否包含违规关键词或匹配违规模式
        这是纯本地检查，不调用 API
        """
        if not self.config.enable_text_moderation:
            return ModerationResult(is_violation=False)

        if not text or not text.strip():
            return ModerationResult(is_violation=False)

        # 预处理：移除空格和特殊字符用于匹配
        normalized_text = text.lower().strip()
        # 同时创建一个去除所有空白/特殊字符的版本
        stripped_text = re.sub(r'[\s\u200b\u200c\u200d\ufeff\u00a0]+', '', normalized_text)

        # 转换为纯拼音字符串，例如 "它飞" -> "tafei"
        if _lazy_pinyin:
            pinyin_text = "".join(_lazy_pinyin(normalized_text)).lower()
        else:
            pinyin_text = ""

        # 1. 精确关键词匹配
        for keyword in self.config.blocked_keywords:
            keyword_lower = keyword.lower()
            # 检查原始文本
            if keyword_lower in normalized_text:
                return ModerationResult(
                    is_violation=True,
                    violation_type=ViolationType.KEYWORD,
                    confidence=1.0,
                    reason=f"命中关键词: {keyword}",
                    matched_keyword=keyword,
                )
            # 检查去空白版本
            keyword_stripped = re.sub(r'\s+', '', keyword_lower)
            if keyword_stripped in stripped_text:
                return ModerationResult(
                    is_violation=True,
                    violation_type=ViolationType.KEYWORD,
                    confidence=0.95,
                    reason=f"命中关键词变体: {keyword}",
                    matched_keyword=keyword,
                )
            # 检查拼音版本 (主要用于匹配用户用各种生僻字代替拼音词)
            if pinyin_text and keyword_stripped in pinyin_text:
                # 只有当 keyword 纯由字母组成时，在 pinyin 里匹配才有意义
                # 如果 keyword 是 "塔菲"，在 pinyin "tafei" 里找 "塔菲" 是找不到的
                # 但如果 keyword 是 "tafei"，在 "tafei" 里找 "tafei" 就能命中
                if keyword_stripped.isascii() and keyword_stripped.isalpha():
                    return ModerationResult(
                        is_violation=True,
                        violation_type=ViolationType.KEYWORD,
                        confidence=0.9,
                        reason=f"命中拼音变体: {keyword_stripped}",
                        matched_keyword=keyword,
                    )

        # 2. 正则模式匹配
        for i, pattern in enumerate(self._compiled_patterns):
            match = pattern.search(normalized_text) or pattern.search(stripped_text) or (pinyin_text and pattern.search(pinyin_text))
            if match:
                return ModerationResult(
                    is_violation=True,
                    violation_type=ViolationType.PATTERN,
                    confidence=0.9,
                    reason=f"命中模式匹配: {match.group()}",
                    matched_pattern=self.config.blocked_patterns[i],
                )

        return ModerationResult(is_violation=False)

    # ========================================
    # 图片审核 (AI Vision)
    # ========================================

    async def check_image(self, image_url: str) -> ModerationResult:
        """
        使用 AI 模型审核图片内容
        检测是否包含特定相关图片/表情包
        """
        if not self.config.enable_image_moderation:
            return ModerationResult(is_violation=False)

        try:
            # 下载图片
            image_data = await self._download_image(image_url)
            if image_data is None:
                logger.warning(f"图片下载失败: {image_url}")
                return ModerationResult(is_violation=False)

            # 调用 Vision API
            result = await self._analyze_image_with_ai(image_data)
            return result

        except Exception as e:
            logger.error(f"图片审核异常: {e}")
            return ModerationResult(is_violation=False)

    async def check_sticker(self, image_url: str) -> ModerationResult:
        """
        审核表情包/贴纸
        与图片审核逻辑相同，但标记为 STICKER 类型
        """
        result = await self.check_image(image_url)
        if result.is_violation:
            result.violation_type = ViolationType.STICKER
        return result

    async def _download_image(self, url: str) -> Optional[bytes]:
        """下载图片数据"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        # 限制文件大小 (最大 10MB)
                        if len(data) > 10 * 1024 * 1024:
                            logger.warning(f"图片过大，跳过审核: {len(data)} bytes")
                            return None
                        return data
                    else:
                        logger.warning(f"图片下载失败 HTTP {resp.status}: {url}")
                        return None
        except asyncio.TimeoutError:
            logger.warning(f"图片下载超时: {url}")
            return None
        except Exception as e:
            logger.warning(f"图片下载异常: {e}")
            return None

    async def _analyze_image_with_ai(self, image_data: bytes) -> ModerationResult:
        """使用 Qwen2-VL 分析图片"""
        try:
            # 将图片转为 Base64
            mime_type = self._detect_mime_type(image_data)
            base64_image = base64.b64encode(image_data).decode('utf-8')
            image_url = f"data:{mime_type};base64,{base64_image}"

            # 调用 OpenAI 格式 API
            response = await self.client.chat.completions.create(
                model="Qwen/Qwen3-VL-8B-Instruct",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.config.image_moderation_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url
                                },
                            },
                        ],
                    }
                ],
                temperature=0.1,
                max_tokens=256,
            )

            # 解析响应
            if response.choices and response.choices[0].message.content:
                return self._parse_ai_response(response.choices[0].message.content)
            else:
                logger.warning("AI 返回空响应")
                return ModerationResult(is_violation=False)

        except Exception as e:
            logger.error(f"AI API 调用失败: {e}")
            return ModerationResult(is_violation=False)

    def _detect_mime_type(self, data: bytes) -> str:
        """根据文件头检测 MIME 类型"""
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        elif data[:2] == b'\xff\xd8':
            return "image/jpeg"
        elif data[:4] == b'GIF8':
            return "image/gif"
        elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return "image/webp"
        else:
            return "image/png"  # 默认

    def _parse_ai_response(self, response_text: str) -> ModerationResult:
        """解析 AI 的 JSON 响应"""
        try:
            logger.debug(f"[AI API 返回] {response_text}")
            # 尝试直接解析
            text = response_text.strip()

            # 去除可能的 markdown 代码块标记
            if text.startswith("```"):
                lines = text.split('\n')
                text = '\n'.join(lines[1:-1])
                text = text.strip()
                if text.startswith("json"):
                    text = text[4:].strip()

            data = json.loads(text)

            is_violation = data.get("is_violation", False)
            confidence = float(data.get("confidence", 0.0))
            reason = data.get("reason", "")
            
            logger.info(f"[AI审核结果] 违规: {is_violation}, 置信度: {confidence}, 原因: {reason}")

            # 检查是否超过置信度阈值
            if is_violation and confidence >= self.config.image_confidence_threshold:
                return ModerationResult(
                    is_violation=True,
                    violation_type=ViolationType.IMAGE,
                    confidence=confidence,
                    reason=f"AI审核: {reason}",
                )
            else:
                return ModerationResult(is_violation=False)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"AI 响应解析失败: {e}, 原文: {response_text[:200]}")
            # 尝试从文本中提取关键信息
            lower_text = response_text.lower()
            if "is_violation" in lower_text and ("true" in lower_text):
                return ModerationResult(
                    is_violation=True,
                    violation_type=ViolationType.IMAGE,
                    confidence=0.6,
                    reason="AI审核标记为违规（响应格式异常）",
                )
            return ModerationResult(is_violation=False)
