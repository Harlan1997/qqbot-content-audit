"""
执行器 - 消息撤回 / 警告通知 / 记录日志
"""

from datetime import datetime
from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment

from .models import ModerationResult, ViolationRecord, ViolationType
from .database import add_violation, get_user_violation_count
from .config import ModConfig


class ActionExecutor:
    """执行器：负责对违规消息采取行动"""

    def __init__(self, config: ModConfig):
        self.config = config

    async def handle_violation(
        self,
        bot: Bot,
        event: GroupMessageEvent,
        result: ModerationResult,
    ):
        """处理违规消息"""
        group_id = event.group_id
        user_id = event.user_id
        message_id = event.message_id
        nickname = event.sender.nickname or str(user_id)

        # 1. 尝试撤回消息
        recall_success, recall_reason = await self._recall_message(bot, message_id)
        action_taken = "recall" if recall_success else "recall_failed"

        # 2. 获取用户违规历史
        violation_count = await get_user_violation_count(group_id, user_id)
        violation_count += 1  # 包含当前这次

        # 3. 发送警告消息
        await self._send_warning(
            bot, event, result, nickname, violation_count, recall_success, recall_reason
        )

        # 4. 记录到数据库
        record = ViolationRecord(
            group_id=group_id,
            user_id=user_id,
            nickname=nickname,
            message_id=message_id,
            message_content=str(event.get_message())[:500],
            violation_type=result.violation_type.value if result.violation_type else "unknown",
            reason=result.reason,
            confidence=result.confidence,
            action_taken=action_taken,
            created_at=datetime.now().isoformat(),
        )
        await add_violation(record)

        logger.info(
            f"[审核] 群 {group_id} | 用户 {nickname}({user_id}) | "
            f"类型: {result.violation_type} | 原因: {result.reason} | "
            f"撤回: {'成功' if recall_success else '失败'} | "
            f"累计违规: {violation_count}次"
        )

    async def _recall_message(self, bot: Bot, message_id: int) -> tuple[bool, str]:
        """撤回消息"""
        try:
            await bot.delete_msg(message_id=message_id)
            logger.info(f"[执行] 消息 {message_id} 撤回成功")
            return True, ""
        except Exception as e:
            logger.error(f"[执行] 消息 {message_id} 撤回失败: {e}")
            reason = "未知错误"
            
            from nonebot.exception import ActionFailed
            if isinstance(e, ActionFailed):
                retcode = getattr(e, "info", {}).get("retcode", None)
                msg = getattr(e, "info", {}).get("message", "") or getattr(e, "info", {}).get("wording", "")
                
                if "decode failed" in msg and '"result": 7' in msg:
                    reason = "由于目标用户是群主/管理员，或机器人没有管理员权限（被QQ拒绝）"
                elif "result" in msg and "errMsg" in msg:
                    try:
                        import json
                        start = msg.find("{")
                        end = msg.rfind("}")
                        if start != -1 and end != -1:
                            json_str = msg[start:end+1]
                            data = json.loads(json_str)
                            err_msg = data.get("errMsg", "")
                            result = data.get("result", "")
                            if err_msg:
                                if result == 7:
                                    reason = "由于目标用户是群主/管理员，或机器人没有管理员权限"
                                else:
                                    reason = f"QQ内核错误: {err_msg} (代码 {result})"
                            else:
                                reason = f"QQ内核返回错误 (代码 {result})"
                    except:
                        pass
                elif "timeout" in msg.lower():
                    reason = "请求超时，可能消息已超过2分钟撤回时效"
                elif retcode == 100:
                    reason = "API不支持或消息不存在"
                elif retcode == 1200:
                    reason = "操作失败，可能消息已超过2分钟或已被撤回"
            else:
                reason = str(e)
                
            return False, reason

    async def _send_warning(
        self,
        bot: Bot,
        event: GroupMessageEvent,
        result: ModerationResult,
        nickname: str,
        violation_count: int,
        recall_success: bool = True,
        recall_reason: str = "",
    ):
        """发送警告消息"""
        try:
            # 根据违规类型选择提示模板
            if result.violation_type in (ViolationType.IMAGE, ViolationType.STICKER):
                base_msg = self.config.violation_reply_image
            else:
                base_msg = self.config.violation_reply

            if not recall_success:
                failure_notice = f"撤回失败（原因：{recall_reason}），请管理员手动处理"
                if "已被撤回" in base_msg:
                    base_msg = base_msg.replace("已被撤回", failure_notice)
                else:
                    base_msg += f"（{failure_notice}）"

            # 构建警告消息
            warning_parts = []

            # @ 发送者
            if self.config.mention_sender_on_recall:
                warning_parts.append(MessageSegment.at(event.user_id))
                warning_parts.append(MessageSegment.text(" "))

            warning_parts.append(MessageSegment.text(base_msg))

            # 添加违规次数
            if violation_count > 1:
                warning_parts.append(
                    MessageSegment.text(f"\n📊 你在本群已累计违规 {violation_count} 次。")
                )

            # 累计次数较多时加重警告
            if violation_count >= 5:
                warning_parts.append(
                    MessageSegment.text("\n🚨 多次违规，请注意遵守群规！")
                )

            # 发送警告
            msg = sum(warning_parts[1:], warning_parts[0])
            await bot.send_group_msg(group_id=event.group_id, message=msg)

        except Exception as e:
            logger.error(f"[执行] 发送警告失败: {e}")
