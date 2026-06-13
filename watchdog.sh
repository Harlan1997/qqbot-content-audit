#!/bin/bash
# qqbot-watchdog.sh — 检测 NapCat 离线状态并自动重启
# 部署位置: /home/admin/qqbot/watchdog.sh

LOG_FILE="/home/admin/qqbot/logs/watchdog.log"
CONTAINER="napcat"
COOLDOWN_FILE="/tmp/qqbot-watchdog-cooldown"
COOLDOWN_SECONDS=300  # 5分钟冷却，防止反复重启

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# 检查容器是否在运行
if ! podman ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    log "❌ 容器 ${CONTAINER} 未运行，跳过检查"
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

    # 等待 15 秒检查结果
    sleep 15
    CHECK_LOGS=$(podman logs --since "15s" "$CONTAINER" 2>&1)

    if echo "$CHECK_LOGS" | grep -q "接收 <-\|WebSocket.*connected\|登录成功\|ServerTime"; then
        log "✅ 重启成功，NapCat 已恢复"
    elif echo "$CHECK_LOGS" | grep -q "请扫描下面的二维码"; then
        log "⚠️ 重启后仍需扫码登录（快速登录失败），需要人工介入"
    else
        log "⚠️ 重启完成，但状态不确定，继续监控"
    fi
else
    # 一切正常，静默通过（不写日志，避免日志膨胀）
    :
fi
