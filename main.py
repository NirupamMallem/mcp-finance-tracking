from fastmcp import FastMCP
import os
import aiosqlite
from pathlib import Path

# -------------------------------------------------
# Cloud-safe persistent directory
# -------------------------------------------------
DATA_DIR = "/data"
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

print(f"[BOOT] Server loaded. DB will be at: {DB_PATH}")

mcp = FastMCP("ExpenseTracker")

# -------------------------------------------------
# LAZY DB INITIALIZATION (CRITICAL FIX)
# -------------------------------------------------
_db_initialized = False

async def ensure_db():
    """
    Lazy, zero-cost init:
    - Runs only on first tool call
    - Never blocks server startup
    """
    global _db_initialized
    if _db_initialized:
        return

    import sqlite3
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
        """)
        conn.commit()

    _db_initialized = True
    print("[DB] Initialized successfully")

# -------------------------------------------------
# TOOLS
# -------------------------------------------------
@mcp.tool()
async def add_expense(
    date: str,
    amount: float,
    category: str,
    subcategory: str = "",
    note: str = ""
):
    await ensure_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT INTO expenses (date, amount, category, subcategory, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (date, amount, category, subcategory, note),
        )
        await db.commit()

        return {
            "status": "success",
            "id": cur.lastrowid,
            "message": "Expense added successfully",
        }

@mcp.tool()
async def list_expenses(start_date: str, end_date: str):
    await ensure_db()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE date BETWEEN ? AND ?
            ORDER BY date DESC, id DESC
            """,
            (start_date, end_date),
        )
        cols = [c[0] for c in cur.description]
        rows = await cur.fetchall()
        return [dict(zip(cols, r)) for r in rows]

@mcp.tool()
async def summarize(start_date: str, end_date: str, category: str = None):
    await ensure_db()

    async with aiosqlite.connect(DB_PATH) as db:
        query = """
            SELECT category, SUM(amount) AS total_amount, COUNT(*) AS count
            FROM expenses
            WHERE date BETWEEN ? AND ?
        """
        params = [start_date, end_date]

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " GROUP BY category ORDER BY total_amount DESC"

        cur = await db.execute(query, params)
        cols = [c[0] for c in cur.description]
        rows = await cur.fetchall()
        return [dict(zip(cols, r)) for r in rows]

@mcp.tool()
async def debug_db_info():
    await ensure_db()

    async with aiosqlite.connect(DB_PATH) as db:
        count = (
            await (await db.execute("SELECT COUNT(*) FROM expenses")).fetchone()
        )[0]

    return {
        "db_path": DB_PATH,
        "exists": os.path.exists(DB_PATH),
        "total_rows": count,
    }

# -------------------------------------------------
# RESOURCE
# -------------------------------------------------
@mcp.resource("expense:///categories", mime_type="application/json")
def categories():
    import json

    if os.path.exists(CATEGORIES_PATH):
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            return f.read()

    return json.dumps(
        {
            "categories": [
                "Food & Dining",
                "Transportation",
                "Shopping",
                "Entertainment",
                "Bills & Utilities",
                "Healthcare",
                "Travel",
                "Education",
                "Business",
                "Other",
            ]
        },
        indent=2,
    )

# -------------------------------------------------
# START SERVER
# -------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
