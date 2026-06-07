import aiosqlite
import datetime

DB_PATH = "data/bot_db.sqlite3"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                free_messages_used_today INTEGER DEFAULT 0,
                last_free_date TEXT,
                messages_bought INTEGER DEFAULT 0,
                unlimited_until TEXT,
                ad_messages_remaining INTEGER DEFAULT 0
            )
        """
        )

        # Check if users has ad_messages_remaining column
        async with db.execute("PRAGMA table_info(users)") as cursor:
            columns = await cursor.fetchall()
            if columns:
                column_names = [col[1] for col in columns]
                if "ad_messages_remaining" not in column_names:
                    await db.execute(
                        "ALTER TABLE users ADD COLUMN ad_messages_remaining INTEGER DEFAULT 0"
                    )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """
        )

        # Check if chat_history has old user_id column and rename it to chat_id
        async with db.execute("PRAGMA table_info(chat_history)") as cursor:
            columns = await cursor.fetchall()
            if columns:
                column_names = [col[1] for col in columns]
                if "user_id" in column_names and "chat_id" not in column_names:
                    await db.execute(
                        "ALTER TABLE chat_history RENAME COLUMN user_id TO chat_id"
                    )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                role TEXT,
                content TEXT
            )
        """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_history_chat_id ON chat_history (chat_id)"
        )
        await db.commit()


async def get_history(chat_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = (
            "SELECT role, content FROM chat_history WHERE chat_id = ? ORDER BY id ASC"
        )
        async with db.execute(query, (chat_id,)) as cursor:
            rows = await cursor.fetchall()
            return [{"role": row["role"], "content": row["content"]} for row in rows]


async def add_message(chat_id: int, role: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO chat_history (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        await db.commit()


async def clear_history(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM chat_history WHERE chat_id = ?", (chat_id,))
        await db.commit()


async def get_user(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                await db.execute(
                    "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
                )
                await db.commit()
                async with db.execute(
                    "SELECT * FROM users WHERE user_id = ?", (user_id,)
                ) as new_cursor:
                    row = await new_cursor.fetchone()
            return dict(row)


async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM admins WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def check_and_consume_quota(user_id: int) -> bool:
    if await is_admin(user_id):
        return True

    user = await get_user(user_id)

    # Check unlimited month
    if user["unlimited_until"]:
        unlimited_until_date = datetime.date.fromisoformat(user["unlimited_until"])
        if datetime.date.today() <= unlimited_until_date:
            return True

    # Atomic decrement for bought messages first
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            UPDATE users
            SET messages_bought = messages_bought - 1
            WHERE user_id = ? AND messages_bought > 0
        """,
            (user_id,),
        ) as cursor:
            if cursor.rowcount > 0:
                await db.commit()
                return True

    # Atomic decrement for ad messages next
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            UPDATE users
            SET ad_messages_remaining = ad_messages_remaining - 1
            WHERE user_id = ? AND ad_messages_remaining > 0
        """,
            (user_id,),
        ) as cursor:
            if cursor.rowcount > 0:
                await db.commit()
                return True

    return False


async def add_reward_quota(user_id: int, count: int = 5):
    await get_user(user_id)  # Ensure user exists
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE users
            SET ad_messages_remaining = ad_messages_remaining + ?
            WHERE user_id = ?
        """,
            (count, user_id),
        )
        await db.commit()


async def claim_free_daily_quota(user_id: int) -> bool:
    today_str = datetime.date.today().isoformat()
    await get_user(user_id)  # Ensure user row exists first

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            UPDATE users
            SET last_free_date = ?, ad_messages_remaining = ad_messages_remaining + 5
            WHERE user_id = ? AND (last_free_date IS NULL OR last_free_date != ?)
        """,
            (today_str, user_id, today_str),
        ) as cursor:
            if cursor.rowcount > 0:
                await db.commit()
                return True
    return False


async def grant_package(user_id: int, package_type: str):
    await get_user(user_id)  # Ensure user exists
    async with aiosqlite.connect(DB_PATH) as db:
        if package_type == "50_messages":
            await db.execute(
                """
                UPDATE users
                SET messages_bought = messages_bought + 50
                WHERE user_id = ?
            """,
                (user_id,),
            )
        elif package_type == "200_messages":
            await db.execute(
                """
                UPDATE users
                SET messages_bought = messages_bought + 200
                WHERE user_id = ?
            """,
                (user_id,),
            )
        elif package_type == "unlimited_month":
            # Add 30 days to unlimited_until
            user = await get_user(user_id)
            current_date = datetime.date.today()
            if user["unlimited_until"]:
                current_unlimited = datetime.date.fromisoformat(user["unlimited_until"])
                if current_unlimited > current_date:
                    current_date = current_unlimited
            new_unlimited = current_date + datetime.timedelta(days=30)
            await db.execute(
                """
                UPDATE users
                SET unlimited_until = ?
                WHERE user_id = ?
            """,
                (new_unlimited.isoformat(), user_id),
            )

        await db.commit()


# Admin CLI helpers
async def add_admin(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,)
        )
        await db.commit()


async def remove_admin(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.commit()


async def list_admins() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM admins") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
