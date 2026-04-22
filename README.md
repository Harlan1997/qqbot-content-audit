# QQ 群聊内容审核机器人

基于 **NoneBot2 + NapCat + SiliconFlow (Qwen2.5-VL)** 的群聊内容审核系统，自动检测并撤回违规消息。

## ✨ 功能特性

- 🔍 **关键词审核** — 检测"永雏塔菲"及其所有变体（谐音、拼音、拆字等，支持识别转发的图文卡片）
- 🖼️ **AI 图片审核** — 使用 Qwen2.5-VL 多模态大模型智能识别违规图片/表情包
- 🗑️ **自动撤回** — 违规消息自动撤回并发送警告
- 📊 **违规记录** — SQLite 存储完整违规历史
- 🛡️ **白名单** — 管理员可设置免审核用户
- 🤖 **管理命令** — 完整的群内管理指令

## 🏗️ 架构

```
QQ 服务器 ←→ NapCat (协议端) ←→ NoneBot2 (业务端) ←→ 硅基流动 AI
                                       ↓
                                   SQLite 数据库
```

## 🚀 部署指南

### 前置要求

- Docker & Docker Compose
- 一个 QQ 小号（**⚠️ 不要使用主号**）
- SiliconFlow API Key (硅基流动)

### 步骤 1: 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入：
```env
GEMINI_API_KEY=你的Gemini-API-Key
MOD_ADMIN_QQ=你的管理员QQ号
MOD_GROUP_IDS=要审核的群号(逗号分隔，留空审核所有群)
```

### 步骤 2: 配置 NapCat

1. 将 `napcat/config/onebot11_QQNUMBER.json` 重命名为你的 QQ 号，例如：
   ```
   napcat/config/onebot11_123456789.json
   ```

2. 如果 NoneBot2 不是用 Docker 部署，需要修改 WebSocket URL：
   ```json
   "url": "ws://127.0.0.1:8080/onebot/v11/ws"
   ```

### 步骤 3: 启动服务

```bash
docker-compose up -d
```

### 步骤 4: 登录 QQ

打开浏览器访问 `http://localhost:6099`，在 NapCat WebUI 中扫码登录 QQ。

### 步骤 5: 确保机器人账号是目标群的管理员

机器人需要群管理员权限才能撤回他人消息。

## 📋 管理命令

| 命令 | 说明 |
|------|------|
| `/mod help` | 查看帮助 |
| `/mod status` | 查看审核状态 |
| `/mod log [数量]` | 查看违规记录 |
| `/mod keywords` | 查看关键词列表 |
| `/mod whitelist` | 查看白名单 |
| `/mod whitelist add @用户` | 加入白名单 |
| `/mod whitelist remove @用户` | 移出白名单 |

## 🔧 本地开发（不使用 Docker）

```bash
# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows

# 安装依赖
pip install -e .

# 运行
python bot.py
```

需要单独部署 NapCat 并配置反向 WebSocket 连接到 `ws://127.0.0.1:8080/onebot/v11/ws`。

## ⚠️ 注意事项

1. **账号风险** — 使用第三方协议存在封号风险，请勿使用重要账号
2. **撤回时限** — QQ 限制机器人管理员只能撤回 2 分钟内的消息
3. **API 用量** — 图片审核会消耗 Gemini API 额度，请注意用量
4. **误判处理** — AI 审核可能存在误判，建议设置白名单
