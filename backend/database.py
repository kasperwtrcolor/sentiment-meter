"""
Database module — SQLite for users, Solana wallet users, credits, and rebalance history.
"""
import sqlite3
import hashlib
import secrets
import time
import os
import random

DB_PATH = os.environ.get("SENTIMENT_DB_PATH", "data/sentiment.db")

ANIMAL_NAMES = [
    "CyberBull", "AlphaApe", "SolWhale", "QuantumFalcon", "NeonCheetah", 
    "VaderFox", "PythEagle", "HyperOtter", "SolanaLynx", "DeltaWolf",
    "ApexTiger", "LaserPanda", "CosmoHawk", "VortexBear", "ZenStallion"
]

TITLES = [
    "Quant", "Navigator", "Strategist", "Operator", "Sentinel",
    "Voyager", "Arbitrageur", "Tactician", "Vanguard", "Architect"
]

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
        CREATE TABLE IF NOT EXISTS wallet_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_address TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            avatar_seed TEXT NOT NULL,
            total_rebalances INTEGER NOT NULL DEFAULT 0,
            volume_usd REAL NOT NULL DEFAULT 0.0,
            joined_at REAL NOT NULL DEFAULT (strftime('%s','now')),
            last_active REAL NOT NULL DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS wallet_rebalances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_address TEXT NOT NULL,
            tx_hash TEXT NOT NULL,
            from_symbol TEXT NOT NULL,
            to_symbol TEXT NOT NULL,
            amount_usd REAL NOT NULL,
            timestamp REAL NOT NULL DEFAULT (strftime('%s','now'))
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
        CREATE INDEX IF NOT EXISTS idx_wallet_users_addr ON wallet_users(wallet_address);
        CREATE INDEX IF NOT EXISTS idx_wallet_rebalances_addr ON wallet_rebalances(wallet_address);
    """)
    conn.commit()
    conn.close()

def generate_random_trader_name(wallet_address: str) -> str:
    """Generates a memorable cyberpunk trader handle for each wallet address."""
    h = int(hashlib.md5(wallet_address.encode()).hexdigest(), 16)
    animal = ANIMAL_NAMES[h % len(ANIMAL_NAMES)]
    title = TITLES[(h // len(ANIMAL_NAMES)) % len(TITLES)]
    num = (h % 900) + 100
    return f"{animal} {title} #{num}"

def get_or_create_wallet_user(wallet_address: str):
    """Retrieves or registers a Solana wallet profile."""
    conn = get_db()
    user = conn.execute("SELECT * FROM wallet_users WHERE wallet_address = ?", (wallet_address,)).fetchone()
    if user:
        conn.execute("UPDATE wallet_users SET last_active = strftime('%s','now') WHERE wallet_address = ?", (wallet_address,))
        conn.commit()
        user = conn.execute("SELECT * FROM wallet_users WHERE wallet_address = ?", (wallet_address,)).fetchone()
        conn.close()
        return dict(user)

    display_name = generate_random_trader_name(wallet_address)
    avatar_seed = hashlib.sha256(wallet_address.encode()).hexdigest()[:12]

    try:
        conn.execute(
            "INSERT INTO wallet_users (wallet_address, display_name, avatar_seed) VALUES (?, ?, ?)",
            (wallet_address, display_name, avatar_seed)
        )
        conn.commit()
        user = conn.execute("SELECT * FROM wallet_users WHERE wallet_address = ?", (wallet_address,)).fetchone()
        return dict(user)
    except Exception:
        user = conn.execute("SELECT * FROM wallet_users WHERE wallet_address = ?", (wallet_address,)).fetchone()
        return dict(user) if user else None
    finally:
        conn.close()

def record_wallet_swap(wallet_address: str, tx_hash: str, from_sym: str, to_sym: str, amount_usd: float):
    """Records an executed rebalance swap against the user's profile."""
    conn = get_db()
    conn.execute(
        "INSERT INTO wallet_rebalances (wallet_address, tx_hash, from_symbol, to_symbol, amount_usd) VALUES (?, ?, ?, ?, ?)",
        (wallet_address, tx_hash, from_sym, to_sym, amount_usd)
    )
    conn.execute(
        "UPDATE wallet_users SET total_rebalances = total_rebalances + 1, volume_usd = volume_usd + ?, last_active = strftime('%s','now') WHERE wallet_address = ?",
        (amount_usd, wallet_address)
    )
    conn.commit()
    conn.close()

def get_wallet_profile(wallet_address: str):
    """Fetches user profile, rank, volume, and past executions."""
    user = get_or_create_wallet_user(wallet_address)
    conn = get_db()
    swaps = conn.execute(
        "SELECT tx_hash, from_symbol, to_symbol, amount_usd, timestamp FROM wallet_rebalances WHERE wallet_address = ? ORDER BY timestamp DESC LIMIT 25",
        (wallet_address,)
    ).fetchall()
    conn.close()
    return {
        "user": user,
        "history": [dict(s) for s in swaps]
    }

# Backward compatible helper
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

def create_user(email):
    conn = get_db()
    api_key = f"sm_{secrets.token_hex(24)}"
    try:
        conn.execute("INSERT INTO users (email, api_key, credits, total_scans) VALUES (?, ?, 3, 0)", (email, api_key))
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(user)
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def deduct_credit(api_key):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE api_key = ?", (api_key,)).fetchone()
    if not user or user["credits"] < 1:
        conn.close()
        return False, dict(user) if user else None
    conn.execute("UPDATE users SET credits = credits - 1, total_scans = total_scans + 1 WHERE api_key = ?", (api_key,))
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE api_key = ?", (api_key,)).fetchone()
    conn.close()
    return True, dict(user)

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
    u = get_user_by_email(email)
    return (u, False) if u else (create_user(email), True)

def add_credits(api_key, amount, description="", stripe_session_id=""):
    conn = get_db()
    conn.execute("UPDATE users SET credits = credits + ? WHERE api_key = ?", (amount, api_key))
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE api_key = ?", (api_key,)).fetchone()
    conn.close()
    return dict(user)

def get_user_by_stripe_customer(cid):
    return None