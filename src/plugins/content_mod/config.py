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
        # 中英混写逃逸（t菲 / 塔f 等）
        "t菲", "T菲", "t 菲", "t.菲", "t-菲",
        "塔f", "塔F", "塔 f", "塔.f", "塔-f",
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
        # 匹配中英混写逃逸（t菲 / 塔f / T 菲 等）
        r"[tT]\s*菲",
        r"塔\s*[fF]",
        r"[tT]\s*[aA]?\s*菲",
        r"塔\s*[fF][eE]?[iI]?",
    ]

    # AI 图片审核的 Prompt
    image_moderation_prompt: str = """你是一个专业的内容审核助手，负责识别与"永雏塔菲"相关的一切内容。

## 永雏塔菲是谁
永雏塔菲（Yonaguni Taffy）是一位VTuber/虚拟主播角色，在中国互联网上有大量粉丝和二创内容。

## 需要识别的内容范围（以下任意一项即判定为违规）

### 外观特征
- 粉色、浅粉、玫瑰粉头发的角色（配合猫耳/兔耳）
- 白色/银白色头发 + 护目镜 的角色（这是塔菲的标志性装束，需同时具备才判违规）
- 猫耳、兔耳头饰配合少女形象
- 具有上述特征的Q版、像素风、简笔画等任何画风

### 文字内容
- 图片中出现"永雏塔菲"、"塔菲"、"taffy"、"永雏"、"tafei"、"tafi"等文字
- 相关昵称：塔菲酱、菲菲、永雏酱等

### 表情包与二创
- 以塔菲为原型的表情包（即使高度变形/卡通化）
- 带有塔菲标志性元素的截图、壁纸、贴纸
- 任何带有"塔菲"标签或水印的图片
- 塔菲直播截图、Youtube/B站截图

### 周边与标志
- 印有塔菲形象的周边商品图片
- 塔菲的Logo或频道标识

## 判断原则
- 严格按照上述特征组合判断，不随意扩大范围
- 白发角色**必须同时有护目镜**才判违规，单独白发不算
- 仅凭猫耳/兔耳无法确认是塔菲时，置信度应低于 0.7
- 纯风景、食物、与上述特征完全无关的内容，is_violation 设为 false

请严格按照以下JSON格式回复，不要包含任何其他内容：
{"is_violation": true/false, "confidence": 0.0-1.0, "reason": "简要说明原因"}"""

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

    # 是否对管理员也进行审核（用于测试）
    audit_admin: bool = False
