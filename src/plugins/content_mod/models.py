"""
数据模型定义
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ViolationType(str, Enum):
    """违规类型"""
    KEYWORD = "keyword"         # 关键词命中
    PATTERN = "pattern"         # 正则模式命中
    IMAGE = "image"             # 图片审核命中
    STICKER = "sticker"         # 表情包审核命中


class ActionType(str, Enum):
    """执行动作"""
    RECALL = "recall"           # 撤回消息
    WARN = "warn"               # 仅警告
    LOG = "log"                 # 仅记录


@dataclass
class ModerationResult:
    """审核结果"""
    is_violation: bool = False
    violation_type: ViolationType | None = None
    confidence: float = 0.0
    reason: str = ""
    matched_keyword: str = ""
    matched_pattern: str = ""


@dataclass
class ViolationRecord:
    """违规记录"""
    id: int = 0
    group_id: int = 0
    user_id: int = 0
    nickname: str = ""
    message_id: int = 0
    message_content: str = ""
    violation_type: str = ""
    reason: str = ""
    confidence: float = 0.0
    action_taken: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
