"""
Database module — SQLite for users, credits, and scan history.
"""
import sqlite3
import hashlib
import secrets
import time
import os

DB_PATH = os.environ.get("SENTIMENT_DB_PATH", "data/sentiment.db")

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            credits INTEGER NOT NULL DEFAULT 0,
            total_scans INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            stripe_customer_id TEXT
        );
        CREATE TABLE IF NOT EXISTS scan_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            person_name TEXT NOT NULL,
            sentiment_label TEXT,
            avg_compound REAL,
            articles_analyzed INTEGER,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS credit_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            amount INTEGER NOT NULL,
            description TEXT,
            stripe_session_id TEXT,
            created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
        );
        CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
        CREATE INDEX IF NOT EXISTS idx_scan_history_user ON scan_history(user_id);
        CREATE INDEX IF NOT EXISTS idx_credit_transactions_user ON credit_transactions(user_id);
    """)
    conn.commit()
    conn.close()

def generate_api_key():
    return f"sm_{secrets.token_hex(24)}"

def create_user(email):
    conn = get_db()
    api_key = generate_api_key()
    free_credits = 3  # 3 free scans to hook them
    try:
        conn.execute(
            "INSERT INTO users (email, api_key, credits, total_scans) VALUES (?, ?, ?, 0)",
            (email, api_key, free_credits)
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(user)
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_user_by_api_key(api_key):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE api_key = ?", (api_key,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_email(email):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_stripe_customer(stripe_customer_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE stripe_customer_id = ?", (stripe_customer_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

def deduct_credit(api_key):
    """Deduct one credit for a scan. Returns (success, user)."""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE api_key = ?", (api_key,)).fetchone()
    if not user:
        conn.close()
        return False, None
    if user["credits"] < 1:
        conn.close()
        return False, dict(user) if user else None
    
    conn.execute("UPDATE users SET credits = credits - 1, total_scans = total_scans + 1 WHERE api_key = ?", (api_key,))
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE api_key = ?", (api_key,)).fetchone()
    conn.close()
    return True, dict(user)

def add_credits(api_key, amount, description="", stripe_session_id=""):
    conn = get_db()
    conn.execute("UPDATE users SET credits = credits + ? WHERE api_key = ?", (amount, api_key))
    conn.execute(
        "INSERT INTO credit_transactions (user_id, amount, description, stripe_session_id) VALUES ((SELECT id FROM users WHERE api_key = ?), ?, ?, ?)",
        (api_key, amount, description, stripe_session_id)
    )
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE api_key = ?", (api_key,)).fetchone()
    conn.close()
    return dict(user)

def record_scan(api_key, person_name, sentiment_label, avg_compound, articles_analyzed):
    conn = get_db()
    user = conn.execute("SELECT id FROM users WHERE api_key = ?", (api_key,)).fetchone()
    if user:
        conn.execute(
            "INSERT INTO scan_history (user_id, person_name, sentiment_label, avg_compound, articles_analyzed) VALUES (?, ?, ?, ?, ?)",
            (user["id"], person_name, sentiment_label, avg_compound, articles_analyzed)
        )
        conn.commit()
    conn.close()

def get_scan_history(api_key, limit=20):
    conn = get_db()
    user = conn.execute("SELECT id FROM users WHERE api_key = ?", (api_key,)).fetchone()
    if not user:
        conn.close()
        return []
    rows = conn.execute(
        "SELECT person_name, sentiment_label, avg_compound, articles_analyzed, created_at FROM scan_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user["id"], limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def find_or_create_user(email):
    """Find user by email or create with 3 free credits."""
    user = get_user_by_email(email)
    if user:
        return user, False
    user = create_user(email)
    if user:
        # Set stripe customer id later
        return user, True
    return None, False