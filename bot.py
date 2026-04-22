"""
QQ 群聊内容审核机器人 - 入口文件
基于 NoneBot2 + OneBot v11 + Google Gemini
"""

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

# 初始化 NoneBot
nonebot.init()

# 注册适配器
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

# 加载插件（从 src/plugins 目录自动加载）
nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()
