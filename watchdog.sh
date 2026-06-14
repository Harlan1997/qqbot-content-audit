#!/bin/bash
# qqbot-watchdog.sh — 通过 API 主动探测 NapCat 在线状态
# 部署位置: /home/admin/qqbot/watchdog.sh
# Cron: */1 * * * * /home/admin/qqbot/watchdog.sh

LOG_FILE="/home/admin/qqbot/logs/watchdog.log"
CONTAINER="napcat"
COOLDOWN_FILE="/tmp/qqbot-watchdog-cooldown"
COOLDOWN_SECONDS=300  # 5分钟冷却，防止反复重启
QRCODE_LOCAL="/home/admin/qqbot/qrcode.png"

# OneBot v11 HTTP API（容器内 3000 端口映射到宿主机 3000）
ONEBOT_API="http://127.0.0.1:3000"

# ===== Telegram 配置（从 .env 读取） =====
ENV_FILE="/home/admin/qqbot/.env"
if [ -f "$ENV_FILE" ]; then
    TG_BOT_TOKEN=$(grep '^TG_BOT_TOKEN=' "$ENV_FILE" | cut -d'=' -f2-)
    TG_CHAT_ID=$(grep '^TG_CHAT_ID=' "$ENV_FILE" | cut -d'=' -f2-)
fi
TG_API="https://api.telegram.org/bot${TG_BOT_TOKEN}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# ===== Telegram 推送函数 =====

tg_send_message() {
    local text="$1"
    curl -s -X POST "${TG_API}/sendMessage" \
        -d "chat_id=${TG_CHAT_ID}" \
        -d "text=${text}" \
        -d "parse_mode=HTML" \
        --max-time 10 > /dev/null 2>&1
}

tg_send_photo() {
    local photo_path="$1"
    local caption="$2"
    curl -s -X POST "${TG_API}/sendPhoto" \
        -F "chat_id=${TG_CHAT_ID}" \
        -F "photo=@${photo_path}" \
        -F "caption=${caption}" \
        -F "parse_mode=HTML" \
        --max-time 15 > /dev/null 2>&1
}

# 推送二维码到 Telegram
push_qrcode_to_telegram() {
    local reason="$1"

    # 获取最新日志，提取二维码 URL
    local logs
    logs=$(podman logs --tail 50 "$CONTAINER" 2>&1)
    local qr_url
    qr_url=$(echo "$logs" | grep -oP '二维码解码URL: \K(https://[^\s]+)' | tail -1)

    # 从容器中拷贝二维码图片
    local has_photo=false
    podman cp "${CONTAINER}:/app/napcat/cache/qrcode.png" "$QRCODE_LOCAL" 2>/dev/null
    if [ -f "$QRCODE_LOCAL" ] && [ -s "$QRCODE_LOCAL" ]; then
        has_photo=true
    fi

    # 构建通知消息
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local msg="🚨 <b>QQ Bot 离线告警</b>

⏰ 时间: ${timestamp}
📋 原因: ${reason}"

    if [ -n "$qr_url" ]; then
        msg="${msg}

🔗 <b>扫码链接:</b>
${qr_url}

📱 用手机 QQ 扫码或点击上方链接"
    fi

    if [ "$has_photo" = true ]; then
        tg_send_photo "$QRCODE_LOCAL" "$msg"
        if [ $? -ne 0 ]; then
            tg_send_message "$msg"
        fi
        log "📤 已推送二维码图片到 Telegram"
    else
        tg_send_message "$msg"
        log "📤 已推送告警到 Telegram"
    fi
}

# ===== 冷却检查 =====

check_cooldown() {
    local reason="$1"
    if [ -f "$COOLDOWN_FILE" ]; then
        local last_restart now elapsed remaining
        last_restart=$(cat "$COOLDOWN_FILE")
        now=$(date +%s)
        elapsed=$((now - last_restart))
        if [ "$elapsed" -lt "$COOLDOWN_SECONDS" ]; then
            remaining=$((COOLDOWN_SECONDS - elapsed))
            log "⏳ 冷却中（还需 ${remaining}s），跳过。原因: $reason"
            return 1
        fi
    fi
    return 0
}

# ===== 重启并检查结果 =====

do_restart() {
    local reason="$1"

    log "🔴 $reason"
    log "🔄 正在重启 ${CONTAINER}..."
    date +%s > "$COOLDOWN_FILE"

    # 根据容器当前状态决定 restart 还是 start
    if podman ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
        podman restart "$CONTAINER" 2>&1 | while read -r line; do log "   $line"; done
    else
        podman start "$CONTAINER" 2>&1 | while read -r line; do log "   $line"; done
    fi

    # 等待启动
    sleep 20

    # 检查是否需要扫码
    local check_logs
    check_logs=$(podman logs --since "20s" "$CONTAINER" 2>&1)

    if echo "$check_logs" | grep -q "请扫描下面的二维码"; then
        log "⚠️ 需要扫码登录，推送二维码到 Telegram"
        push_qrcode_to_telegram "$reason"
    elif echo "$check_logs" | grep -q "接收 <-\|WebSocket.*connected\|登录成功\|ServerTime"; then
        log "✅ 重启成功，已恢复在线"
        tg_send_message "✅ QQ Bot 已自动恢复上线
⏰ $(date '+%Y-%m-%d %H:%M:%S')
📋 触发原因: ${reason}"
    else
        log "⚠️ 重启完成，状态待确认"
        tg_send_message "⚠️ QQ Bot 已重启，状态待确认
⏰ $(date '+%Y-%m-%d %H:%M:%S')
📋 原因: ${reason}
请手动检查"
    fi
}

# ===================================================================
# 主逻辑
# ===================================================================

# —— 第一步：容器是否在运行 ——
if ! podman ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    if podman ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
        log "⚠️ 容器 ${CONTAINER} 已退出"
        check_cooldown "容器已退出" && do_restart "容器已退出，自动重启"
    else
        log "❌ 容器 ${CONTAINER} 不存在"
    fi
    exit 0
fi

# —— 第二步：调 OneBot API 探测在线状态（核心检测） ——
# 调用 get_status 接口，返回 {"online": true/false, "good": true/false}
API_RESPONSE=$(curl -s --max-time 5 "${ONEBOT_API}/get_status" 2>&1)
API_EXIT_CODE=$?

if [ "$API_EXIT_CODE" -ne 0 ]; then
    # API 完全不通：HTTP 服务可能还没启动，或者进程已假死
    log "⚠️ OneBot API 不可达 (exit=$API_EXIT_CODE)"

    # 检查最近日志是否有活跃信号（给刚启动的容器一个缓冲期）
    RECENT_LOGS=$(podman logs --since "3m" "$CONTAINER" 2>&1)
    if echo "$RECENT_LOGS" | grep -q "请扫描下面的二维码"; then
        check_cooldown "API 不可达 + 等待扫码" && do_restart "API 不可达，检测到需要扫码"
    elif echo "$RECENT_LOGS" | grep -q "NapCat Shell App Loading\|等待网络连接\|正在快速登录"; then
        log "ℹ️ 容器正在启动中，等待下次检查"
    else
        # API 不通且没有启动信号 — 可能假死
        check_cooldown "API 不可达（疑似假死）" && do_restart "API 不可达，疑似假死"
    fi
    exit 0
fi

# API 有响应，解析 online 状态
IS_ONLINE=$(echo "$API_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    # OneBot v11 get_status 响应格式: {\"data\": {\"online\": true, \"good\": true}}
    d = data.get('data', data)
    print('true' if d.get('online', False) else 'false')
except:
    print('error')
" 2>/dev/null)

case "$IS_ONLINE" in
    "true")
        # 在线，一切正常，静默通过
        ;;
    "false")
        # API 明确返回不在线
        log "🔴 OneBot API 报告: 不在线"
        check_cooldown "API 报告不在线" && do_restart "OneBot API 报告 QQ 不在线"
        ;;
    *)
        # API 返回了数据但解析失败，记录原始响应
        log "⚠️ OneBot API 响应异常: ${API_RESPONSE:0:200}"
        ;;
esac
