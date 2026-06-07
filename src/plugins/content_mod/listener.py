"""
消息监听器 - 监听群聊消息并进行审核
"""

import asyncio
import time
from collections import defaultdict, deque
from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageSegment,
)

from .config import ModConfig
from .moderator import ContentModerator
from .executor import ActionExecutor
from .database import is_whitelisted


# ========================================
# 跨消息上下文缓冲区（防拆字逃逸）
# key: (group_id, user_id)
# value: deque of (timestamp, message_id, text)
# ========================================
_MSG_WINDOW_SECONDS = 30   # 时间窗口：30 秒内
_MSG_WINDOW_MAX = 2         # 只保留最近 2 条（上一条 + 当前条）

_msg_buffer: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=_MSG_WINDOW_MAX))


async def process_group_message(
    bot: Bot,
    event: GroupMessageEvent,
    config: ModConfig,
    moderator: ContentModerator,
    executor: ActionExecutor,
):
    """
    处理群消息 - 核心审核流程

    流程:
    1. 检查是否需要审核（群号、白名单）
    2. 提取消息内容（文本、图片、表情）
    3. 文本关键词检查
    4. 图片/表情 AI 审核
    5. 违规则撤回+警告
    """
    group_id = event.group_id
    user_id = event.user_id

    # ========================================
    # 前置过滤
    # ========================================

    # 检查群号是否在审核范围内
    if config.mod_group_ids and group_id not in config.mod_group_ids:
        return

    # 检查用户是否在白名单中
    if user_id in config.whitelist_qq:
        return
    if await is_whitelisted(user_id):
        return

    # 不审核管理员（除非开启了 audit_admin 测试模式）
    if user_id in config.mod_admin_qq and not config.audit_admin:
        return

    # 不审核机器人自己
    if user_id == int(bot.self_id):
        return

    message = event.get_message()

    # ========================================
    # 文本审核
    # ========================================
    text_content = _extract_text(message)

    # 更新用户消息缓冲区
    buf_key = (group_id, user_id)
    now = time.time()
    if text_content:
        _msg_buffer[buf_key].append((now, event.message_id, text_content))

    if text_content:
        # 1. 先检查单条消息
        text_result = moderator.check_text(text_content)
        if text_result.is_violation:
            logger.info(
                f"[审核] 文本违规 | 群 {group_id} | 用户 {user_id} | "
                f"内容: {text_content[:100]} | 原因: {text_result.reason}"
            )
            await executor.handle_violation(bot, event, text_result)
            _msg_buffer[buf_key].clear()  # 违规后清空缓冲区
            return

        # 2. 跨消息拼接检测（只看上一条 + 当前条）
        if len(_msg_buffer[buf_key]) == 2:
            prev_ts, _, prev_txt = _msg_buffer[buf_key][0]
            if now - prev_ts <= _MSG_WINDOW_SECONDS:
                combined_text = prev_txt + text_content
                combined_result = moderator.check_text(combined_text)
                if combined_result.is_violation:
                    logger.info(
                        f"[审核] 跨消息拼接违规 | 群 {group_id} | 用户 {user_id} | "
                        f"拼合内容: {combined_text[:100]} | 原因: {combined_result.reason}"
                    )
                    await executor.handle_violation(bot, event, combined_result)
                    _msg_buffer[buf_key].clear()
                    return

    # ========================================
    # 图片/表情审核
    # ========================================
    image_urls = _extract_image_urls(message)
    if image_urls and config.enable_image_moderation:
        # 并发审核所有图片，但限制并发数
        semaphore = asyncio.Semaphore(3)

        async def check_with_limit(url: str):
            async with semaphore:
                return await moderator.check_image(url)

        tasks = [check_with_limit(url) for url in image_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"图片审核异常: {result}")
                continue
            if result.is_violation:
                logger.info(
                    f"[审核] 图片违规 | 群 {group_id} | 用户 {user_id} | "
                    f"原因: {result.reason}"
                )
                await executor.handle_violation(bot, event, result)
                return  # 已撤回

    # ========================================
    # 表情包审核（mface / marketface）
    # ========================================
    sticker_urls = _extract_sticker_urls(message)
    if sticker_urls and config.enable_image_moderation:
        for url in sticker_urls:
            result = await moderator.check_sticker(url)
            if result.is_violation:
                logger.info(
                    f"[审核] 表情包违规 | 群 {group_id} | 用户 {user_id} | "
                    f"原因: {result.reason}"
                )
                await executor.handle_violation(bot, event, result)
                return


def _extract_text(message: Message) -> str:
    """提取消息中的所有文本内容，包括卡片消息"""
    texts = []
    for seg in message:
        if seg.type == "text":
            texts.append(str(seg.data.get("text", "")))
        elif seg.type == "json":
            texts.append(str(seg.data.get("data", "")))
        elif seg.type == "xml":
            texts.append(str(seg.data.get("data", "")))
        elif seg.type == "forward" or seg.type == "node":
            # 某些合并转发消息的简单文本
            content = seg.data.get("content", "")
            if isinstance(content, str):
                texts.append(content)
    return " ".join(texts).strip()


def _extract_image_urls(message: Message) -> list[str]:
    """提取消息中的图片 URL"""
    urls = []
    for seg in message:
        if seg.type == "image":
            url = seg.data.get("url", "")
            if url:
                urls.append(url)
    return urls


def _extract_sticker_urls(message: Message) -> list[str]:
    """
    提取表情包/贴纸的 URL
    支持: mface (商城表情), marketface, image 类型中的表情
    """
    urls = []
    for seg in message:
        # 商城表情 / 自定义表情
        if seg.type in ("mface", "marketface"):
            url = seg.data.get("url", "")
            if url:
                urls.append(url)

        # 某些表情会以图片形式发送
        elif seg.type == "image":
            # 检查是否是表情包类型的图片
            subtype = seg.data.get("subType", 0)
            # subType=1 通常表示表情包
            if subtype == 1:
                url = seg.data.get("url", "")
                if url:
                    urls.append(url)

    return urls
