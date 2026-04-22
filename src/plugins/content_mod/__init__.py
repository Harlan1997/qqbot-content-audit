"""
内容审核插件 - 主入口

插件功能：
- 监听群聊消息（文本 + 图片 + 表情包）
- 关键词匹配（永雏塔菲 及变体）
- Gemini AI 图片/表情包识别
- 违规消息自动撤回 + 警告
"""

import os
from nonebot import get_driver, on_message, logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent

from .config import ModConfig
from .moderator import ContentModerator
from .executor import ActionExecutor
from .listener import process_group_message
from .database import init_db
from .admin import set_admin_config

# ========================================
# 插件元数据
# ========================================
__plugin_meta__ = {
    "name": "内容审核",
    "description": "QQ群聊内容审核机器人 - 关键词 + AI图片识别 + 自动撤回",
    "usage": "自动运行，管理员可用 /mod help 查看命令",
}

# ========================================
# 初始化配置
# ========================================
driver = get_driver()


def _load_config() -> ModConfig:
    """从环境变量加载配置"""
    from dotenv import load_dotenv
    load_dotenv()
    config = ModConfig()

    # Gemini API Key
    config.gemini_api_key = os.getenv("GEMINI_API_KEY", "")

    # 审核群号
    group_ids_str = os.getenv("MOD_GROUP_IDS", "")
    if group_ids_str.strip():
        config.mod_group_ids = [
            int(x.strip()) for x in group_ids_str.split(",") if x.strip().isdigit()
        ]

    # 审核模式
    config.mod_policy = os.getenv("MOD_POLICY", "strict")

    # 管理员
    admin_str = os.getenv("MOD_ADMIN_QQ", "")
    if admin_str.strip():
        config.mod_admin_qq = [
            int(x.strip()) for x in admin_str.split(",") if x.strip().isdigit()
        ]

    return config


# 加载配置并创建核心组件
plugin_config = _load_config()
moderator = ContentModerator(plugin_config)
executor = ActionExecutor(plugin_config)

# 设置管理命令的配置
set_admin_config(plugin_config)


# ========================================
# 启动时初始化
# ========================================
@driver.on_startup
async def on_startup():
    """启动时初始化数据库"""
    await init_db()

    # 检查 Gemini API Key
    if not plugin_config.gemini_api_key or plugin_config.gemini_api_key == "your-gemini-api-key-here":
        logger.warning(
            "⚠️ GEMINI_API_KEY 未配置！图片审核功能将不可用。\n"
            "请在 .env 文件中设置 GEMINI_API_KEY=your-key"
        )
        plugin_config.enable_image_moderation = False
    else:
        logger.info("✅ Gemini API Key 已配置，图片审核已启用")

    logger.info(
        f"✅ 内容审核插件已加载\n"
        f"   📝 关键词数量: {len(plugin_config.blocked_keywords)}\n"
        f"   🔍 正则模式数量: {len(plugin_config.blocked_patterns)}\n"
        f"   📌 审核模式: {plugin_config.mod_policy}\n"
        f"   🖼️ 图片审核: {'启用' if plugin_config.enable_image_moderation else '禁用'}\n"
        f"   🎯 审核群组: {'所有群' if not plugin_config.mod_group_ids else plugin_config.mod_group_ids}"
    )


# ========================================
# 消息监听器 - 核心入口
# ========================================
group_msg_handler = on_message(priority=1, block=False)


@group_msg_handler.handle()
async def handle_group_message(bot: Bot, event: GroupMessageEvent):
    """拦截所有群消息进行审核"""
    try:
        await process_group_message(
            bot=bot,
            event=event,
            config=plugin_config,
            moderator=moderator,
            executor=executor,
        )
    except Exception as e:
        logger.error(f"[审核] 消息处理异常: {e}", exc_info=True)
