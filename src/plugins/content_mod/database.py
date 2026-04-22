"""
SQLite 数据库操作 - 违规记录存储
"""

import aiosqlite
from pathlib import Path
from .models import ViolationRecord

DB_PATH = Path("data") / "content_mod.db"


async def init_db():
    """初始化数据库表"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                nickname TEXT DEFAULT '',
                message_id INTEGER NOT NULL,
                message_content TEXT DEFAULT '',
                violation_type TEXT NOT NULL,
                reason TEXT DEFAULT '',
                confidence REAL DEFAULT 0.0,
                action_taken TEXT DEFAULT 'recall',
                created_at TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS whitelist (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER NOT NULL,
                added_at TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_violations_group
            ON violations(group_id, created_at DESC)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_violations_user
            ON violations(user_id, created_at DESC)
        """)

        await db.commit()


async def add_violation(record: ViolationRecord):
    """添加违规记录"""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            INSERT INTO violations
            (group_id, user_id, nickname, message_id, message_content,
             violation_type, reason, confidence, action_taken, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.group_id,
                record.user_id,
                record.nickname,
                record.message_id,
                record.message_content,
                record.violation_type,
                record.reason,
                record.confidence,
                record.action_taken,
                record.created_at,
            ),
        )
        await db.commit()


async def get_recent_violations(group_id: int, limit: int = 10) -> list[ViolationRecord]:
    """获取最近的违规记录"""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM violations
            WHERE group_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (group_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                ViolationRecord(
                    id=row["id"],
                    group_id=row["group_id"],
                    user_id=row["user_id"],
                    nickname=row["nickname"],
                    message_id=row["message_id"],
                    message_content=row["message_content"],
                    violation_type=row["violation_type"],
                    reason=row["reason"],
                    confidence=row["confidence"],
                    action_taken=row["action_taken"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]


async def get_user_violation_count(group_id: int, user_id: int) -> int:
    """获取用户违规次数"""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM violations WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def add_whitelist(user_id: int, added_by: int):
    """添加白名单"""
    from datetime import datetime

    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT OR REPLACE INTO whitelist (user_id, added_by, added_at) VALUES (?, ?, ?)",
            (user_id, added_by, datetime.now().isoformat()),
        )
        await db.commit()


async def remove_whitelist(user_id: int):
    """移除白名单"""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("DELETE FROM whitelist WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_whitelist() -> list[int]:
    """获取白名单列表"""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        async with db.execute("SELECT user_id FROM whitelist") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def is_whitelisted(user_id: int) -> bool:
    """检查用户是否在白名单中"""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        async with db.execute(
            "SELECT 1 FROM whitelist WHERE user_id = ?", (user_id,)
        ) as cursor:
            return await cursor.fetchone() is not None
