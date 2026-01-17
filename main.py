from fastmcp import FastMCP
import os
import aiosqlite
from pathlib import Path

# -----------------------------
# Persistent storage directory
# -----------------------------
DATA_DIR = os.getenv("DATA_DIR", os.path.dirname(__file__))
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

print(f"[REMOTE] Database path: {DB_PATH}")

mcp = FastMCP("ExpenseTracker")

# -----------------------------
# Database initialization
# -----------------------------
def init_db():
    import sqlite3
    with sqlite3.connect(DB_PATH) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""
            CREATE TABLE IF NOT EXISTS expenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
        """)
        c.commit()
        count = c.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        print(f"[REMOTE] DB ready. Rows: {count}")

init_db()

# -----------------------------
# TOOLS
# -----------------------------
@mcp.tool()
async def add_expense(
    date: str,
    amount: float,
    category: str,
    subcategory: str = "",
    note: str = ""
):
    async with aiosqlite.connect(DB_PATH) as c:
        cur = await c.execute(
            "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
            (date, amount, category, subcategory, note)
        )
        await c.commit()
        return {
            "status": "success",
            "id": cur.lastrowid,
            "message": "Expense added successfully"
        }

@mcp.tool()
async def list_expenses(start_date: str, end_date: str):
    async with aiosqlite.connect(DB_PATH) as c:
        cur = await c.execute("""
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE date BETWEEN ? AND ?
            ORDER BY date DESC, id DESC
        """, (start_date, end_date))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in await cur.fetchall()]

@mcp.tool()
async def summarize(start_date: str, end_date: str, category: str = None):
    async with aiosqlite.connect(DB_PATH) as c:
        query = """
            SELECT category, SUM(amount) AS total_amount, COUNT(*) as count
            FROM expenses
            WHERE date BETWEEN ? AND ?
        """
        params = [start_date, end_date]

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " GROUP BY category ORDER BY total_amount DESC"

        cur = await c.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in await cur.fetchall()]

@mcp.tool()
async def debug_db_info():
    async with aiosqlite.connect(DB_PATH) as c:
        count = (await (await c.execute("SELECT COUNT(*) FROM expenses")).fetchone())[0]
        return {
            "db_path": DB_PATH,
            "total_rows": count,
            "exists": os.path.exists(DB_PATH)
        }

# -----------------------------
# Resource
# -----------------------------
@mcp.resource("expense:///categories", mime_type="application/json")
def categories():
    import json
    if os.path.exists(CATEGORIES_PATH):
        return open(CATEGORIES_PATH, "r", encoding="utf-8").read()

    return json.dumps({
        "categories": [
            "Food & Dining", "Transportation", "Shopping",
            "Entertainment", "Bills & Utilities",
            "Healthcare", "Travel", "Education",
            "Business", "Other"
        ]
    }, indent=2)

# -----------------------------
# Start server
# -----------------------------
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
