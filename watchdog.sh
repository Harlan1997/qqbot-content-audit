#!/bin/bash
# qqbot-watchdog.sh — 检测 NapCat 离线状态，自动重启并推送二维码到 Telegram
# 部署位置: /home/admin/qqbot/watchdog.sh
# Cron: */1 * * * * /home/admin/qqbot/watchdog.sh

LOG_FILE="/home/admin/qqbot/logs/watchdog.log"
CONTAINER="napcat"
COOLDOWN_FILE="/tmp/qqbot-watchdog-cooldown"
COOLDOWN_SECONDS=300  # 5分钟冷却，防止反复重启
QRCODE_LOCAL="/home/admin/qqbot/qrcode.png"

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

# 发送 Telegram 文本消息
tg_send_message() {
    local text="$1"
    curl -s -X POST "${TG_API}/sendMessage" \
        -d "chat_id=${TG_CHAT_ID}" \
        -d "text=${text}" \
        -d "parse_mode=HTML" \
        --max-time 10 > /dev/null 2>&1
}

# 发送 Telegram 图片（附带文字说明）
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

# 从日志中提取二维码信息并推送到 Telegram
push_qrcode_to_telegram() {
    local logs="$1"
    local reason="$2"

    # 提取二维码解码 URL
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
📋 原因: ${reason}
🤖 容器: ${CONTAINER}"

    if [ -n "$qr_url" ]; then
        msg="${msg}

🔗 <b>扫码链接:</b>
${qr_url}

📱 用手机 QQ 扫码或点击上方链接"
    fi

    # 推送：优先发图片（图片附带说明），否则发纯文本
    if [ "$has_photo" = true ]; then
        tg_send_photo "$QRCODE_LOCAL" "$msg"
        local tg_result=$?
        if [ $tg_result -ne 0 ]; then
            # 图片发送失败，降级为纯文本
            tg_send_message "$msg"
        fi
        log "📤 已推送二维码图片到 Telegram"
    else
        tg_send_message "$msg"
        log "📤 已推送二维码链接到 Telegram（图片不可用）"
    fi

    # 如果没有 URL 也没有图片，发送纯告警
    if [ -z "$qr_url" ] && [ "$has_photo" = false ]; then
        tg_send_message "🚨 QQ Bot 离线，但未能获取二维码，请手动检查！
时间: ${timestamp}
原因: ${reason}"
        log "📤 已推送离线告警到 Telegram（无二维码信息）"
    fi
}

# ===== 主逻辑 =====

# 检查容器是否在运行
if ! podman ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    # 容器未运行，检查是否存在但已退出（如二维码超时导致进程退出）
    if podman ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
        log "⚠️ 容器 ${CONTAINER} 已退出，检查是否因登录失败"

        # 检查冷却时间
        if [ -f "$COOLDOWN_FILE" ]; then
            LAST_RESTART=$(cat "$COOLDOWN_FILE")
            NOW=$(date +%s)
            ELAPSED=$((NOW - LAST_RESTART))
            if [ "$ELAPSED" -lt "$COOLDOWN_SECONDS" ]; then
                REMAINING=$((COOLDOWN_SECONDS - ELAPSED))
                log "⏳ 冷却中（还需 ${REMAINING}s），跳过重启"
                exit 0
            fi
        fi

        # 查看退出前的日志，判断是否因扫码超时退出
        EXIT_LOGS=$(podman logs --tail 50 "$CONTAINER" 2>&1)
        if echo "$EXIT_LOGS" | grep -q "请扫描下面的二维码\|Login Error\|登录态已失效"; then
            log "🔴 容器已退出，原因：登录态失效/二维码超时"
            log "🔄 正在重启 ${CONTAINER}..."
            date +%s > "$COOLDOWN_FILE"

            podman start "$CONTAINER" 2>&1 | while read -r line; do
                log "   $line"
            done

            # 等待 20 秒让 NapCat 启动并生成二维码
            sleep 20
            CHECK_LOGS=$(podman logs --since "20s" "$CONTAINER" 2>&1)

            if echo "$CHECK_LOGS" | grep -q "接收 <-\|WebSocket.*connected\|登录成功\|ServerTime"; then
                log "✅ 重启成功，NapCat 已恢复"
                tg_send_message "✅ QQ Bot 已自动恢复上线
⏰ $(date '+%Y-%m-%d %H:%M:%S')"
            elif echo "$CHECK_LOGS" | grep -q "请扫描下面的二维码"; then
                log "⚠️ 重启后仍需扫码，推送二维码到 Telegram"
                push_qrcode_to_telegram "$CHECK_LOGS" "容器退出后重启，仍需扫码登录"
            else
                log "⚠️ 重启完成，状态不确定"
                tg_send_message "⚠️ QQ Bot 从退出状态重启，状态不确定
⏰ $(date '+%Y-%m-%d %H:%M:%S')
请手动检查"
            fi
        else
            log "❌ 容器 ${CONTAINER} 已退出，但非登录相关，跳过"
        fi
    else
        log "❌ 容器 ${CONTAINER} 不存在，跳过检查"
    fi
    exit 0
fi

# 获取最近 5 分钟的日志
RECENT_LOGS=$(podman logs --since "5m" "$CONTAINER" 2>&1)

# 检查是否有离线信号
OFFLINE_COUNT=$(echo "$RECENT_LOGS" | grep -c "账号状态变更为离线")
# 检查是否有活跃的消息收发（说明在线）
ACTIVE_COUNT=$(echo "$RECENT_LOGS" | grep -c "接收 <-")
# 检查是否在等待扫码（说明登录态丢失）
QRCODE_WAITING=$(echo "$RECENT_LOGS" | grep -c "请扫描下面的二维码")
# 检查是否有 Login Error
LOGIN_ERROR=$(echo "$RECENT_LOGS" | grep -c "Login Error")

# 判断是否需要重启
NEED_RESTART=false
REASON=""

if [ "$QRCODE_WAITING" -gt 0 ]; then
    NEED_RESTART=true
    REASON="检测到等待扫码登录（登录态已失效）"
elif [ "$LOGIN_ERROR" -gt 0 ]; then
    NEED_RESTART=true
    REASON="检测到登录错误"
elif [ "$OFFLINE_COUNT" -ge 2 ] && [ "$ACTIVE_COUNT" -eq 0 ]; then
    NEED_RESTART=true
    REASON="检测到多次离线且无活跃消息"
fi

if [ "$NEED_RESTART" = true ]; then
    # 检查冷却时间
    if [ -f "$COOLDOWN_FILE" ]; then
        LAST_RESTART=$(cat "$COOLDOWN_FILE")
        NOW=$(date +%s)
        ELAPSED=$((NOW - LAST_RESTART))
        if [ "$ELAPSED" -lt "$COOLDOWN_SECONDS" ]; then
            REMAINING=$((COOLDOWN_SECONDS - ELAPSED))
            log "⏳ 冷却中（还需 ${REMAINING}s），跳过重启。原因: $REASON"
            exit 0
        fi
    fi

    log "🔴 $REASON"
    log "🔄 正在重启 ${CONTAINER}..."

    # 记录冷却时间
    date +%s > "$COOLDOWN_FILE"

    # 重启容器
    podman restart "$CONTAINER" 2>&1 | while read -r line; do
        log "   $line"
    done

    # 等待 20 秒让 NapCat 完全启动并生成二维码
    sleep 20
    CHECK_LOGS=$(podman logs --since "20s" "$CONTAINER" 2>&1)

    if echo "$CHECK_LOGS" | grep -q "接收 <-\|WebSocket.*connected\|登录成功\|ServerTime"; then
        log "✅ 重启成功，NapCat 已恢复"
        tg_send_message "✅ QQ Bot 已自动恢复上线
⏰ $(date '+%Y-%m-%d %H:%M:%S')"
    elif echo "$CHECK_LOGS" | grep -q "请扫描下面的二维码"; then
        log "⚠️ 重启后仍需扫码登录（快速登录失败），推送二维码到 Telegram"
        push_qrcode_to_telegram "$CHECK_LOGS" "$REASON"
    else
        log "⚠️ 重启完成，但状态不确定，继续监控"
        tg_send_message "⚠️ QQ Bot 重启完成但状态不确定
⏰ $(date '+%Y-%m-%d %H:%M:%S')
📋 原因: $REASON
请手动检查"
    fi
else
    # 一切正常，静默通过（不写日志，避免日志膨胀）
    :
fi
