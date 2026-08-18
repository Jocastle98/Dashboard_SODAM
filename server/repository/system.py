"""매장·수집 상태 조회."""

from __future__ import annotations

import sqlite3


def store_id_by_code(connection: sqlite3.Connection, store_code: str) -> int | None:
    row = connection.execute(
        "SELECT store_id FROM stores WHERE store_code = ?", (store_code,)
    ).fetchone()
    return int(row["store_id"]) if row else None


def store_info(connection: sqlite3.Connection, store_id: int) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT store_code, store_name, open_hour, close_hour FROM stores WHERE store_id = ?",
        (store_id,),
    ).fetchone()


def last_collection(connection: sqlite3.Connection, store_id: int) -> sqlite3.Row | None:
    """FN-203 갱신 배지 / GET /api/system/status 의 근거."""
    return connection.execute(
        """
        SELECT finished_at, target_to, status
        FROM collection_logs
        WHERE store_id = ? AND status = 'success' AND report_type = 'orders'
        ORDER BY finished_at DESC
        LIMIT 1
        """,
        (store_id,),
    ).fetchone()


def data_range(connection: sqlite3.Connection, store_id: int) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT MIN(biz_date) AS date_from, MAX(biz_date) AS date_to "
        "FROM daily_sales WHERE store_id = ?",
        (store_id,),
    ).fetchone()


def recent_logs(connection: sqlite3.Connection, store_id: int, limit: int = 30):
    """FN-501 수집 이력 조회."""
    return connection.execute(
        """
        SELECT report_type, started_at, finished_at, target_from, target_to,
               status, record_count, error_message
        FROM collection_logs
        WHERE store_id = ?
        ORDER BY started_at DESC, log_id DESC
        LIMIT ?
        """,
        (store_id, limit),
    ).fetchall()
