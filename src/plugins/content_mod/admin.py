"""
管理命令 - 群管理员操作审核系统
"""

from nonebot import on_command, logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageSegment,
)
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import Message

from .database import (
    get_recent_violations,
    get_user_violation_count,
    add_whitelist,
    remove_whitelist,
    get_whitelist,
)
from .config import ModConfig

# 全局配置引用（在 __init__.py 中设置）
_config: ModConfig | None = None


def set_admin_config(config: ModConfig):
    """设置管理命令使用的配置"""
    global _config
    _config = config


def _is_admin(user_id: int) -> bool:
    """检查是否是管理员"""
    if _config is None:
        return False
    return user_id in _config.mod_admin_qq


# ========================================
# /mod status - 查看审核状态
# ========================================
mod_status = on_command("mod status", aliases={"审核状态"}, priority=5, block=True)


@mod_status.handle()
async def handle_status(bot: Bot, event: GroupMessageEvent):
    if not _is_admin(event.user_id):
        await mod_status.finish("❌ 无权限，仅管理员可用。")

    if _config is None:
        await mod_status.finish("❌ 配置未加载。")
        return

    groups = "所有群" if not _config.mod_group_ids else str(_config.mod_group_ids)
    whitelist = await get_whitelist()

    status_msg = (
        "📋 内容审核系统状态\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📌 审核模式: {_config.mod_policy}\n"
        f"📝 文本审核: {'✅ 启用' if _config.enable_text_moderation else '❌ 禁用'}\n"
        f"🖼️ 图片审核: {'✅ 启用' if _config.enable_image_moderation else '❌ 禁用'}\n"
        f"🎯 审核群组: {groups}\n"
        f"📏 关键词数量: {len(_config.blocked_keywords)}\n"
        f"🔍 正则模式数量: {len(_config.blocked_patterns)}\n"
        f"👤 白名单人数: {len(whitelist)}\n"
        f"🎚️ 图片置信度阈值: {_config.image_confidence_threshold}\n"
        f"💬 AI模型: Gemini 2.0 Flash"
    )

    await mod_status.finish(status_msg)


# ========================================
# /mod log - 查看违规记录
# ========================================
mod_log = on_command("mod log", aliases={"违规记录"}, priority=5, block=True)


@mod_log.handle()
async def handle_log(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not _is_admin(event.user_id):
        await mod_log.finish("❌ 无权限，仅管理员可用。")

    # 解析数量参数
    count = 5
    arg_text = args.extract_plain_text().strip()
    if arg_text.isdigit():
        count = min(int(arg_text), 20)

    records = await get_recent_violations(event.group_id, limit=count)

    if not records:
        await mod_log.finish("📋 暂无违规记录。")
        return

    lines = ["📋 最近违规记录\n━━━━━━━━━━━━━━━━━━"]
    for i, r in enumerate(records, 1):
        time_str = r.created_at[:16].replace("T", " ")
        lines.append(
            f"\n{i}. 🕐 {time_str}\n"
            f"   👤 {r.nickname} ({r.user_id})\n"
            f"   📌 类型: {r.violation_type}\n"
            f"   💬 原因: {r.reason[:50]}\n"
            f"   🔧 操作: {r.action_taken}"
        )

    await mod_log.finish("\n".join(lines))


# ========================================
# /mod whitelist - 白名单管理
# ========================================
mod_whitelist = on_command("mod whitelist", aliases={"白名单"}, priority=5, block=True)


@mod_whitelist.handle()
async def handle_whitelist(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not _is_admin(event.user_id):
        await mod_whitelist.finish("❌ 无权限，仅管理员可用。")

    arg_text = args.extract_plain_text().strip()
    parts = arg_text.split()

    if len(parts) < 1:
        # 显示白名单
        wl = await get_whitelist()
        if not wl:
            await mod_whitelist.finish("📋 白名单为空。")
        else:
            lines = ["📋 白名单用户:"]
            for uid in wl:
                lines.append(f"  • {uid}")
            await mod_whitelist.finish("\n".join(lines))
        return

    action = parts[0].lower()

    # 提取被 @ 的用户或直接输入的 QQ 号
    target_ids = []
    for seg in args:
        if seg.type == "at":
            target_ids.append(int(seg.data["qq"]))
    if not target_ids and len(parts) >= 2 and parts[1].isdigit():
        target_ids.append(int(parts[1]))

    if not target_ids:
        await mod_whitelist.finish("❌ 请指定用户（@某人 或 QQ号）。")
        return

    if action == "add":
        for uid in target_ids:
            await add_whitelist(uid, event.user_id)
        names = ", ".join(str(uid) for uid in target_ids)
        await mod_whitelist.finish(f"✅ 已将 {names} 加入白名单。")

    elif action in ("remove", "del", "rm"):
        for uid in target_ids:
            await remove_whitelist(uid)
        names = ", ".join(str(uid) for uid in target_ids)
        await mod_whitelist.finish(f"✅ 已将 {names} 移出白名单。")

    else:
        await mod_whitelist.finish("❌ 用法: /mod whitelist add/remove @用户 或 QQ号")


# ========================================
# /mod keywords - 查看关键词列表
# ========================================
mod_keywords = on_command("mod keywords", aliases={"关键词列表"}, priority=5, block=True)


@mod_keywords.handle()
async def handle_keywords(bot: Bot, event: GroupMessageEvent):
    if not _is_admin(event.user_id):
        await mod_keywords.finish("❌ 无权限，仅管理员可用。")

    if _config is None:
        await mod_keywords.finish("❌ 配置未加载。")
        return

    lines = ["🔒 屏蔽关键词列表\n━━━━━━━━━━━━━━━━━━"]
    for kw in _config.blocked_keywords:
        lines.append(f"  • {kw}")

    lines.append(f"\n🔍 正则模式 ({len(_config.blocked_patterns)} 条)")
    for p in _config.blocked_patterns:
        lines.append(f"  • {p}")

    await mod_keywords.finish("\n".join(lines))


# ========================================
# 动态关键字管理
# ========================================
import json
from pathlib import Path

EXTRA_KW_FILE = Path("data") / "extra_keywords.json"

def get_extra_keywords() -> list[str]:
    if EXTRA_KW_FILE.exists():
        try:
            return json.loads(EXTRA_KW_FILE.read_text("utf-8"))
        except:
            return []
    return []

def save_extra_keywords(kws: list[str]):
    EXTRA_KW_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXTRA_KW_FILE.write_text(json.dumps(kws, ensure_ascii=False), "utf-8")

mod_addkw = on_command("mod addkw", aliases={"添加关键词", "加词"}, priority=5, block=True)

@mod_addkw.handle()
async def handle_addkw(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not _is_admin(event.user_id):
        await mod_addkw.finish("❌ 无权限，仅管理员可用。")

    kw = args.extract_plain_text().strip()
    if not kw:
        await mod_addkw.finish("❌ 请输入要添加的关键词。用法: /mod addkw 关键词")
        return

    if kw in _config.blocked_keywords:
        await mod_addkw.finish(f"⚠️ 关键词 '{kw}' 已经存在。")
        return

    # 添加到内存
    _config.blocked_keywords.append(kw)
    
    # 保存到文件
    extra_kws = get_extra_keywords()
    if kw not in extra_kws:
        extra_kws.append(kw)
        save_extra_keywords(extra_kws)

    await mod_addkw.finish(f"✅ 成功添加关键词: {kw}")

mod_rmkw = on_command("mod rmkw", aliases={"删除关键词", "删词"}, priority=5, block=True)

@mod_rmkw.handle()
async def handle_rmkw(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not _is_admin(event.user_id):
        await mod_rmkw.finish("❌ 无权限，仅管理员可用。")

    kw = args.extract_plain_text().strip()
    if not kw:
        await mod_rmkw.finish("❌ 请输入要删除的关键词。用法: /mod rmkw 关键词")
        return

    if kw not in _config.blocked_keywords:
        await mod_rmkw.finish(f"⚠️ 找不到关键词 '{kw}'。")
        return

    # 从内存删除
    _config.blocked_keywords.remove(kw)
    
    # 从文件删除
    extra_kws = get_extra_keywords()
    if kw in extra_kws:
        extra_kws.remove(kw)
        save_extra_keywords(extra_kws)

    await mod_rmkw.finish(f"✅ 成功删除关键词: {kw}")


# ========================================
# 置信度修改
# ========================================
SETTINGS_FILE = Path("data") / "settings.json"

def get_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text("utf-8"))
        except:
            return {}
    return {}

def save_settings(settings: dict):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False), "utf-8")

mod_setthresh = on_command("mod setthresh", aliases={"设置阈值"}, priority=5, block=True)

@mod_setthresh.handle()
async def handle_setthresh(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    if not _is_admin(event.user_id):
        await mod_setthresh.finish("❌ 无权限，仅管理员可用。")

    arg_str = args.extract_plain_text().strip()
    try:
        val = float(arg_str)
        if val < 0.0 or val > 1.0:
            raise ValueError
    except ValueError:
        await mod_setthresh.finish("❌ 请输入 0.0 到 1.0 之间的数字。用法: /mod setthresh 0.5")
        return

    # 内存修改
    _config.image_confidence_threshold = val
    
    # 存入文件
    settings = get_settings()
    settings["image_confidence_threshold"] = val
    save_settings(settings)

    await mod_setthresh.finish(f"✅ 图片置信度阈值已更新为: {val}")


# ========================================
# /mod help - 帮助信息
# ========================================
mod_help = on_command("mod help", aliases={"审核帮助"}, priority=5, block=True)


@mod_help.handle()
async def handle_help(bot: Bot, event: GroupMessageEvent):
    help_msg = (
        "🤖 内容审核机器人 - 命令帮助\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📋 /mod status - 查看审核状态\n"
        "📜 /mod log [数量] - 查看违规记录\n"
        "📝 /mod keywords - 查看关键词列表\n"
        "➕ /mod addkw [词] - 动态添加关键词\n"
        "➖ /mod rmkw [词] - 动态删除关键词\n"
        "🎚️ /mod setthresh [数字] - 设置图片拦截阈值(0-1)\n"
        "👤 /mod whitelist - 查看白名单\n"
        "➕ /mod whitelist add @用户 - 加入白名单\n"
        "➖ /mod whitelist remove @用户 - 移出白名单\n"
        "❓ /mod help - 查看帮助"
    )
    await mod_help.finish(help_msg)
