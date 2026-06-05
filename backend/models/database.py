"""SQLite 数据库层 — 用户、画像、资源、路径的持久化存储。

数据库文件：./data/a3_learning.db
"""

import sqlite3
import os
import json
import hashlib
import secrets
from datetime import datetime

DB_DIR = "./data"
DB_PATH = os.path.join(DB_DIR, "a3_learning.db")

os.makedirs(DB_DIR, exist_ok=True)


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 让结果可以用 dict 方式访问
    conn.execute("PRAGMA journal_mode=WAL")  # 读写并发更好
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化所有表"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nickname TEXT DEFAULT '',
            token TEXT UNIQUE,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS student_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            profile_json TEXT DEFAULT '{}',
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS learning_resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            topic TEXT DEFAULT '',
            title TEXT DEFAULT '',
            content TEXT DEFAULT '',
            agent TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS learning_paths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course TEXT NOT NULL DEFAULT '默认路径',
            path_json TEXT DEFAULT '{}',
            status_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, course)
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            text TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_resources_user ON learning_resources(user_id);
        CREATE INDEX IF NOT EXISTS idx_profiles_user ON student_profiles(user_id);
        CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id);
    """)
    conn.commit()
    conn.close()


# ===== 用户操作 =====

def hash_password(password: str) -> str:
    """密码哈希（SHA256 + salt，比 bcrypt 轻，比赛够用）"""
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"


def verify_password(password: str, hashed: str) -> bool:
    """验证密码"""
    salt, h = hashed.split("$", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == h


def create_user(username: str, password: str, nickname: str = "") -> dict | None:
    """注册新用户，返回用户信息（不含密码）"""
    conn = get_db()
    try:
        token = secrets.token_hex(32)
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, nickname, token) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), nickname or username, token),
        )
        conn.commit()
        user = conn.execute("SELECT id, username, nickname, token FROM users WHERE id = ?",
                            (cursor.lastrowid,)).fetchone()
        # 初始化空画像
        conn.execute("INSERT INTO student_profiles (user_id, profile_json) VALUES (?, '{}')",
                     (cursor.lastrowid,))
        conn.commit()
        return dict(user) if user else None
    except sqlite3.IntegrityError:
        return None  # 用户名已存在
    finally:
        conn.close()


def authenticate(username: str, password: str) -> dict | None:
    """登录验证，成功返回用户信息+token，失败返回None"""
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, username, nickname, password_hash, token FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if user and verify_password(password, user["password_hash"]):
            return {"id": user["id"], "username": user["username"],
                    "nickname": user["nickname"], "token": user["token"]}
        return None
    finally:
        conn.close()


def get_user_by_token(token: str) -> dict | None:
    """通过 token 获取用户信息"""
    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, username, nickname FROM users WHERE token = ?", (token,)
        ).fetchone()
        return dict(user) if user else None
    finally:
        conn.close()


# ===== 画像操作 =====

def get_profile(user_id: int) -> dict:
    """获取学生画像"""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT profile_json FROM student_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            return json.loads(row["profile_json"])
        return {}
    finally:
        conn.close()


def update_profile(user_id: int, profile: dict) -> dict:
    """更新学生画像"""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE student_profiles SET profile_json = ?, updated_at = datetime('now') WHERE user_id = ?",
            (json.dumps(profile, ensure_ascii=False), user_id),
        )
        conn.commit()
        return profile
    finally:
        conn.close()


# ===== 资源操作 =====

def add_resource(user_id: int, resource_type: str, topic: str, title: str, content: str, agent: str = "") -> dict:
    """添加学习资源"""
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO learning_resources (user_id, resource_type, topic, title, content, agent) VALUES (?,?,?,?,?,?)",
            (user_id, resource_type, topic, title, content, agent),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM learning_resources WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def get_resources(user_id: int) -> list[dict]:
    """获取用户的所有资源，最新的在前"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM learning_resources WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ===== 路径操作 =====

def list_paths(user_id: int) -> list[dict]:
    """获取用户的所有学习路径"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, course, path_json, status_json, created_at, updated_at FROM learning_paths WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_path(user_id: int, course: str = None) -> dict | None:
    """获取用户某门课的学习路径"""
    conn = get_db()
    try:
        if course:
            row = conn.execute(
                "SELECT path_json FROM learning_paths WHERE user_id = ? AND course = ?", (user_id, course)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT path_json FROM learning_paths WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1", (user_id,)
            ).fetchone()
        return json.loads(row["path_json"]) if row else None
    finally:
        conn.close()


def update_path(user_id: int, path_data: dict) -> dict:
    """创建或更新学习路径（按 user_id + course 去重）"""
    course = path_data.get("course", "默认路径")
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO learning_paths (user_id, course, path_json, updated_at) VALUES (?, ?, ?, datetime('now')) "
            "ON CONFLICT(user_id, course) DO UPDATE SET path_json = ?, updated_at = datetime('now')",
            (user_id, course, json.dumps(path_data, ensure_ascii=False), json.dumps(path_data, ensure_ascii=False)),
        )
        conn.commit()
        return path_data
    finally:
        conn.close()


def delete_path(user_id: int, course: str) -> bool:
    """删除用户某门课的学习路径"""
    conn = get_db()
    try:
        conn.execute("DELETE FROM learning_paths WHERE user_id = ? AND course = ?", (user_id, course))
        conn.commit()
        return True
    finally:
        conn.close()


# ===== 聊天记录操作 =====

def save_chat_message(user_id: int, role: str, text: str) -> dict:
    """保存一条聊天消息"""
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO chat_messages (user_id, role, text) VALUES (?, ?, ?)",
            (user_id, role, text),
        )
        conn.commit()
        return {"id": cursor.lastrowid}
    finally:
        conn.close()


def get_chat_history(user_id: int, limit: int = 50) -> list[dict]:
    """获取用户最近N条聊天记录"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, role, text, created_at FROM chat_messages WHERE user_id = ? ORDER BY id ASC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [{"id": str(r["id"]), "text": r["text"], "role": r["role"]} for r in rows]
    finally:
        conn.close()


def clear_chat_history(user_id: int):
    """清空用户聊天记录"""
    conn = get_db()
    try:
        conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
