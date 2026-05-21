"""
db.py — SQLite Database Layer for NOMAD SecureChat

All messages stored as encrypted ciphertext. Even DB admin can't read them.
"""
import sqlite3
import os
import time
import json
from typing import Optional, List, Dict

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "securechat.db")


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables on first run."""
    conn = get_connection()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            avatar_color TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            public_key TEXT,
            bio TEXT DEFAULT '',
            language TEXT DEFAULT 'en',
            private_mode INTEGER DEFAULT 0,
            is_public INTEGER DEFAULT 0,
            status_text TEXT DEFAULT 'Available',
            custom_theme TEXT DEFAULT 'default',
            online INTEGER DEFAULT 0,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            encrypted_content TEXT NOT NULL,
            message_type TEXT DEFAULT 'text',
            is_private INTEGER DEFAULT 0,
            is_read INTEGER DEFAULT 0,
            timestamp REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            user_a TEXT NOT NULL,
            user_b TEXT NOT NULL,
            created_at REAL NOT NULL,
            UNIQUE(user_a, user_b)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS friends (
            user_id TEXT NOT NULL,
            friend_id TEXT NOT NULL,
            status TEXT DEFAULT 'pending', 
            UNIQUE(user_id, friend_id)
        );

        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            media_url TEXT,
            timestamp REAL NOT NULL
        );
    """)
    conn.commit()
    conn.close()


# ─── User CRUD ────────────────────────────────────

def create_user(user_id: str, username: str, display_name: str,
                password_hash: str, language: str = 'en') -> bool:
    import random
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD',
              '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E8']
    color = random.choice(colors)
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO users (id, username, display_name, avatar_color, password_hash, language, created_at) VALUES (?,?,?,?,?,?,?)",
            (user_id, username.lower(), display_name, color, password_hash, language, time.time())
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def get_user_by_username(username: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username.lower(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_user_pubkey(user_id: str, public_key: str):
    conn = get_connection()
    conn.execute("UPDATE users SET public_key=? WHERE id=?", (public_key, user_id))
    conn.commit()
    conn.close()


def set_online_status(user_id: str, online: bool):
    conn = get_connection()
    conn.execute("UPDATE users SET online=? WHERE id=?", (1 if online else 0, user_id))
    conn.commit()
    conn.close()


def search_users(query: str, exclude_id: str) -> List[Dict]:
    conn = get_connection()
    # Also fetch public users for discovery if query is empty
    if not query.strip():
        rows = conn.execute(
            "SELECT id, username, display_name, avatar_color, bio, status_text, online FROM users WHERE is_public=1 AND id != ? ORDER BY online DESC LIMIT 20",
            (exclude_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, username, display_name, avatar_color, bio, status_text, online FROM users WHERE username LIKE ? AND id != ? LIMIT 10",
            (f'%{query.lower()}%', exclude_id)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_profile(user_id: str, bio: str, is_public: bool, status_text: str, custom_theme: str):
    conn = get_connection()
    conn.execute(
        "UPDATE users SET bio=?, is_public=?, status_text=?, custom_theme=? WHERE id=?",
        (bio, 1 if is_public else 0, status_text, custom_theme, user_id)
    )
    conn.commit()
    conn.close()

def get_friends(user_id: str) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT u.id, u.username, u.display_name, u.avatar_color, u.status_text, u.online, f.status "
        "FROM friends f JOIN users u ON f.friend_id = u.id "
        "WHERE f.user_id=?", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_friend(user_id: str, friend_id: str):
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO friends (user_id, friend_id, status) VALUES (?,?,?)", (user_id, friend_id, 'accepted'))
    conn.execute("INSERT OR REPLACE INTO friends (user_id, friend_id, status) VALUES (?,?,?)", (friend_id, user_id, 'accepted'))
    conn.commit()
    conn.close()


# ─── Posts / Global Feed ───────────────────────────

def add_post(post_id: str, user_id: str, content: str, media_url: str = None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO posts (id, user_id, content, media_url, timestamp) VALUES (?,?,?,?,?)",
        (post_id, user_id, content, media_url, time.time())
    )
    conn.commit()
    conn.close()

def get_global_feed(limit: int = 50) -> List[Dict]:
    conn = get_connection()
    # Join with users to get avatar, name, etc.
    rows = conn.execute(
        "SELECT p.*, u.username, u.display_name, u.avatar_color "
        "FROM posts p JOIN users u ON p.user_id = u.id "
        "ORDER BY p.timestamp DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── Session / Auth ────────────────────────────────

def create_session(token: str, user_id: str):
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO sessions (token, user_id, created_at) VALUES (?,?,?)",
                 (token, user_id, time.time()))
    conn.commit()
    conn.close()


def get_session_user(token: str) -> Optional[str]:
    conn = get_connection()
    row = conn.execute("SELECT user_id FROM sessions WHERE token=?", (token,)).fetchone()
    conn.close()
    return row['user_id'] if row else None


def delete_session(token: str):
    conn = get_connection()
    conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    conn.commit()
    conn.close()


# ─── Rooms + Messages ──────────────────────────────

def get_or_create_room(user_a: str, user_b: str) -> str:
    sorted_ids = sorted([user_a, user_b])
    room_id = f"room_{sorted_ids[0]}_{sorted_ids[1]}"
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO rooms (id, user_a, user_b, created_at) VALUES (?,?,?,?)",
        (room_id, sorted_ids[0], sorted_ids[1], time.time())
    )
    conn.commit()
    conn.close()
    return room_id


def store_message(msg_id: str, room_id: str, sender_id: str,
                  encrypted_content: str, msg_type: str = 'text',
                  is_private: bool = False):
    conn = get_connection()
    conn.execute(
        "INSERT INTO messages (id, room_id, sender_id, encrypted_content, message_type, is_private, is_read, timestamp) VALUES (?,?,?,?,?,?,?,?)",
        (msg_id, room_id, sender_id, encrypted_content, msg_type, 1 if is_private else 0, 0, time.time())
    )
    conn.commit()
    conn.close()

def mark_messages_read(room_id: str, recipient_id: str):
    conn = get_connection()
    conn.execute(
        "UPDATE messages SET is_read=1 WHERE room_id=? AND sender_id!=?",
        (room_id, recipient_id)
    )
    conn.commit()
    conn.close()

def get_room_messages(room_id: str, limit: int = 50) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM messages WHERE room_id=? ORDER BY timestamp DESC LIMIT ?",
        (room_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]

def get_user_rooms(user_id: str) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT r.*, u.username, u.display_name, u.avatar_color, u.online, u.status_text "
        "FROM rooms r "
        "JOIN users u ON (CASE WHEN r.user_a=? THEN r.user_b ELSE r.user_a END) = u.id "
        "WHERE r.user_a=? OR r.user_b=?",
        (user_id, user_id, user_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
