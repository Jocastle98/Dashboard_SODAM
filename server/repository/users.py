"""대시보드 사용자 조회·생성. 비밀번호는 해시만 다룬다 (FR-AUTH-04)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def find_by_username(connection: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT user_id, store_id, username, password_hash, role FROM users WHERE username = ?",
        (username,),
    ).fetchone()


def touch_login(connection: sqlite3.Connection, user_id: int) -> None:
    connection.execute(
        "UPDATE users SET last_login_at = ? WHERE user_id = ?",
        (datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), user_id),
    )
    connection.commit()


def create(connection: sqlite3.Connection, store_id: int,
           username: str, password_hash: str, role: str = "owner") -> int:
    cursor = connection.execute(
        "INSERT INTO users (store_id, username, password_hash, role) VALUES (?,?,?,?)",
        (store_id, username, password_hash, role),
    )
    connection.commit()
    return int(cursor.lastrowid)


def update_password(connection: sqlite3.Connection, user_id: int, password_hash: str) -> None:
    connection.execute(
        "UPDATE users SET password_hash = ? WHERE user_id = ?", (password_hash, user_id)
    )
    connection.commit()
