"""
화면 설정 조회·저장 (FN-253).

**이 패키지에서 유일하게 쓰기를 하는 모듈이다.** 나머지 repository 는 전부 조회다.
수집 결과가 아니라 사장님의 취향을 담으므로 수집기가 아닌 대시보드가 주인이다
(`db/schema.sql` 의 `app_settings` 주석 참고).

SQL 은 여기까지다. 값의 의미(JSON 구조·기본값·검증)는 `service/new_menu.py` 가 정한다.
"""

from __future__ import annotations

from collector.db import Session, now


# ── 설정 (key → JSON 문자열) ────────────────────────────

def read(session: Session, store_id: int, key: str) -> str | None:
    row = session.execute(
        "SELECT setting_value FROM app_settings WHERE store_id = ? AND setting_key = ?",
        (store_id, key),
    ).fetchone()
    return row["setting_value"] if row else None


def write(session: Session, store_id: int, key: str, value: str) -> None:
    session.execute(
        """
        INSERT INTO app_settings (store_id, setting_key, setting_value, updated_at)
        VALUES (?,?,?,?)
        ON CONFLICT(store_id, setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at    = excluded.updated_at
        """,
        (store_id, key, value, now()),
    )


# ── 메뉴 수동 지정/제외 ─────────────────────────────────

def overrides(session: Session, store_id: int) -> dict[str, bool]:
    """
    `{menu_code: True(지정) | False(제외)}`.

    SQLite 는 0/1, PostgreSQL 은 BOOLEAN 을 돌려준다 — `bool()` 로 양쪽을 같게 만든다.
    여기서 맞추지 않으면 `is_new is True` 비교가 SQLite 에서만 조용히 거짓이 된다.
    """
    rows = session.execute(
        "SELECT menu_code, is_new FROM menu_overrides WHERE store_id = ?",
        (store_id,),
    ).fetchall()
    return {row["menu_code"]: bool(row["is_new"]) for row in rows}


def set_override(session: Session, store_id: int, menu_code: str, is_new: bool) -> None:
    session.execute(
        """
        INSERT INTO menu_overrides (store_id, menu_code, is_new, updated_at)
        VALUES (?,?,?,?)
        ON CONFLICT(store_id, menu_code) DO UPDATE SET
            is_new     = excluded.is_new,
            updated_at = excluded.updated_at
        """,
        (store_id, menu_code, is_new, now()),
    )


def clear_override(session: Session, store_id: int, menu_code: str) -> None:
    """지정을 지운다 — 그 메뉴는 다시 자동 판정에 맡겨진다."""
    session.execute(
        "DELETE FROM menu_overrides WHERE store_id = ? AND menu_code = ?",
        (store_id, menu_code),
    )
