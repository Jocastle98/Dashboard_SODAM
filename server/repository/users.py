"""대시보드 사용자 조회·생성. 비밀번호는 해시만 다룬다 (FR-AUTH-04)."""

from __future__ import annotations

from collector.db import Row, Session, now


def find_by_username(session: Session, username: str) -> Row | None:
    return session.execute(
        "SELECT user_id, store_id, username, password_hash, role FROM users WHERE username = ?",
        (username,),
    ).fetchone()


def touch_login(session: Session, user_id: int) -> None:
    # 시각 형식은 collector/db/now() 하나만 쓴다 — 여기서 따로 만들지 않는다
    session.execute(
        "UPDATE users SET last_login_at = ? WHERE user_id = ?", (now(), user_id)
    )
    session.commit()


def create(session: Session, store_id: int,
           username: str, password_hash: str, role: str = "owner") -> int:
    """
    `RETURNING`으로 새 user_id를 받는다.

    `cursor.lastrowid`를 쓰지 않는 이유: **psycopg에는 없다.**
    `RETURNING`은 PostgreSQL과 SQLite(3.35+) 양쪽에서 동작한다.
    """
    row = session.execute(
        "INSERT INTO users (store_id, username, password_hash, role, created_at) "
        "VALUES (?,?,?,?,?) RETURNING user_id",
        (store_id, username, password_hash, role, now()),
    ).fetchone()
    session.commit()
    return int(row["user_id"])


def update_password(session: Session, user_id: int, password_hash: str) -> None:
    session.execute(
        "UPDATE users SET password_hash = ? WHERE user_id = ?", (password_hash, user_id)
    )
    session.commit()
