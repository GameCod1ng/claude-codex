import sqlite3
from datetime import datetime
from pathlib import Path

DB = Path(__file__).parent / "history.db"


def init():
    with sqlite3.connect(DB) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS history (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            url      TEXT,
            summary  TEXT,
            keywords TEXT,
            channel  TEXT,
            sent_at  TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS scheduled (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            url          TEXT,
            message      TEXT,
            channel_id   TEXT,
            channel_name TEXT,
            send_at      TEXT,
            status       TEXT DEFAULT 'pending'
        )""")


def is_duplicate(url: str) -> bool:
    with sqlite3.connect(DB) as c:
        return c.execute("SELECT 1 FROM history WHERE url=?", (url,)).fetchone() is not None


def add_history(url, summary, keywords, channel):
    with sqlite3.connect(DB) as c:
        c.execute(
            "INSERT INTO history VALUES (NULL,?,?,?,?,?)",
            (url, summary, keywords, channel, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )


def get_history():
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM history ORDER BY sent_at DESC")]


def delete_history(row_id: int):
    with sqlite3.connect(DB) as c:
        c.execute("DELETE FROM history WHERE id=?", (row_id,))


def add_scheduled(url, message, channel_id, channel_name, send_at):
    with sqlite3.connect(DB) as c:
        c.execute(
            "INSERT INTO scheduled VALUES (NULL,?,?,?,?,?,?)",
            (url, message, channel_id, channel_name, send_at, "pending"),
        )


def get_scheduled():
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM scheduled ORDER BY send_at DESC")]


def get_pending():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(
            "SELECT * FROM scheduled WHERE status='pending' AND send_at<=?", (now,)
        )]


def mark_sent(row_id: int):
    with sqlite3.connect(DB) as c:
        c.execute("UPDATE scheduled SET status='sent' WHERE id=?", (row_id,))


def cancel_scheduled(row_id: int):
    with sqlite3.connect(DB) as c:
        c.execute("UPDATE scheduled SET status='cancelled' WHERE id=?", (row_id,))
