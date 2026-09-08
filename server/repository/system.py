"""매장·수집 상태 조회."""

from __future__ import annotations

from collector.db import Row, Session



def store_id_by_code(session: Session, store_code: str) -> int | None:
    row = session.execute(
        "SELECT store_id FROM stores WHERE store_code = ?", (store_code,)
    ).fetchone()
    return int(row["store_id"]) if row else None


def store_info(session: Session, store_id: int) -> Row | None:
    return session.execute(
        "SELECT store_code, store_name, open_hour, close_hour FROM stores WHERE store_id = ?",
        (store_id,),
    ).fetchone()


def last_collection(session: Session, store_id: int) -> Row | None:
    """FN-203 갱신 배지 / GET /api/system/status 의 근거."""
    return session.execute(
        """
        SELECT finished_at, target_to, status
        FROM collection_logs
        WHERE store_id = ? AND status = 'success' AND report_type = 'orders'
        ORDER BY finished_at DESC
        LIMIT 1
        """,
        (store_id,),
    ).fetchone()


def last_collection_attempt(session: Session, store_id: int) -> str | None:
    """
    성공·실패를 가리지 않은 마지막 수집 시도 시각 (FN-205 최소 간격 판단).

    `last_collection()`은 성공한 주문 수집만 본다. 간격 판단에 그것을 쓰면
    수집이 계속 실패할 때 버튼을 누르는 대로 POS를 두드리게 된다.
    """
    row = session.execute(
        "SELECT MAX(started_at) AS started_at FROM collection_logs WHERE store_id = ?",
        (store_id,),
    ).fetchone()
    return row["started_at"] if row and row["started_at"] else None


def data_range(session: Session, store_id: int) -> Row | None:
    return session.execute(
        "SELECT MIN(biz_date) AS date_from, MAX(biz_date) AS date_to "
        "FROM daily_sales WHERE store_id = ?",
        (store_id,),
    ).fetchone()


def recent_logs(session: Session, store_id: int, limit: int = 30):
    """FN-501 수집 이력 조회."""
    return session.execute(
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
