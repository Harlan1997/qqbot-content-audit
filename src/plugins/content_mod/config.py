"""
内容审核插件 - 配置模型
"""

from pydantic import BaseModel


class ModConfig(BaseModel):
    """内容审核插件配置"""

    # Google Gemini API Key
    gemini_api_key: str = ""

    # 启用审核的群号列表，空列表表示所有群
    mod_group_ids: list[int] = []

    # 审核模式: strict / normal / loose
    mod_policy: str = "strict"

    # 管理员 QQ 号列表
    mod_admin_qq: list[int] = []

    # ========================================
    # 关键词审核配置 - 永雏塔菲相关
    # ========================================

    # 主要关键词及其变体
    blocked_keywords: list[str] = [
        # 原始关键词
        "永雏塔菲",
        # 简称/缩写
        "塔菲",
        "taffy",
        "永雏",
        # 繁体变体
        "永雛塔菲",
        "永雛",
        # 拼音变体
        "yongchu",
        "yongchutafei",
        "tafei",
        # 谐音/同音变体
        "永初塔菲",
        "咏雏塔菲",
        "永雏塔非",
        "永雏他非",
        "永雏她菲",
        "永雏踏菲",
        "涌雏塔菲",
        "永雏搭菲",
        # 拆字/隐晦变体
        "永 雏 塔 菲",
        "塔 菲",
        "永雏酱",
        "塔菲酱",
        "tafi",
        "taphy",
        # 英文变体
        "eternally baby taffy",
        # 常见昵称
        "菲菲",
        "小塔菲",
        "塔肥",
        "小菲"
    ]

    # 正则表达式模式 - 用于匹配更灵活的变体
    blocked_patterns: list[str] = [
        # 匹配中间插入特殊字符的情况: 永X雏X塔X菲
        r"永.{0,2}雏.{0,2}塔.{0,2}菲",
        # 匹配中间插入特殊字符的简称
        r"塔.{0,1}菲",
        # 匹配拼音变体
        r"[tT][aA][fF]+[eEiIyY]",
        # 匹配永雏+任意后缀
        r"永雏.",
    ]

    # AI 图片审核的 Prompt
    image_moderation_prompt: str = """你是一个内容审核助手。请分析这张图片，判断是否包含与"永雏塔菲"（一个虚拟主播/VTuber角色）相关的内容。

永雏塔菲的特征包括：
- 粉色/浅紫色头发
- 猫耳或兔耳头饰
- 常见的表情包形象
- 任何包含"塔菲"、"永雏"、"taffy"等文字的图片

请严格按照以下JSON格式回复，不要包含任何其他内容：
{"is_violation": true/false, "confidence": 0.0-1.0, "reason": "简要说明原因"}

如果图片中包含永雏塔菲相关内容，is_violation 设为 true。
如果无法确定或图片与永雏塔菲无关，is_violation 设为 false。"""

    # 违规消息回复模板
    violation_reply: str = "⚠️ 检测到违规内容，消息已被撤回。"
    violation_reply_image: str = "⚠️ 检测到违规图片/表情，消息已被撤回。"

    # 是否在撤回时 @发送者
    mention_sender_on_recall: bool = True

    # 图片审核置信度阈值 (0.0 - 1.0)
    image_confidence_threshold: float = 0.7

    # 是否启用图片审核（会消耗 Gemini API 额度）
    enable_image_moderation: bool = True

    # 是否启用文本关键词审核
    enable_text_moderation: bool = True

    # 白名单用户（不审核）
    whitelist_qq: list[int] = []
