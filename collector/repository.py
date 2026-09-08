"""
DB 적재 — SQL은 이 모듈 밖으로 나가지 않는다.

모든 쓰기는 UPSERT다 (FR-COL-05 / FN-604).
같은 날짜를 다시 수집해도 중복되지 않고 갱신된다.
`ON CONFLICT ... DO UPDATE` 문법은 SQLite와 PostgreSQL이 같아 그대로 쓴다.

연결·방언은 `collector/db/`가 담당한다. 여기서는 `?` 자리표시자로 SQL을 쓰고,
방언별로 갈리는 조각만 `session.dialect`에 물어본다 (`dialect.true` 등).

시각 값은 `db.now()` 하나만 쓴다. DB의 DEFAULT를 쓰지 않는 이유는 `db/__init__.py` 참고.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .aggregate import DailySales, HourlySales
from .config import ROOT, Settings
from .db import (  # noqa: F401 — 재노출
    Session, apply_schema, connect, describe_target, now, sqlite_path,
)
from .parse.cancels import Cancel
from .parse.menu import MenuSale
from .parse.orders import Order

__all__ = [
    "Session", "connect", "apply_schema", "now", "sqlite_path", "describe_target",
    "CollectionLog", "ensure_store", "upsert_orders", "upsert_daily", "replace_hourly",
    "upsert_menu_sales", "upsert_cancels", "write_log", "save_raw_file",
    "date_range_in_db", "count_rows",
]


# ── 매장 ──────────────────────────────────────────────────

def ensure_store(session: Session, settings: Settings) -> int:
    """매장 행을 만들거나 갱신하고 store_id를 돌려준다."""
    session.execute(
        """
        INSERT INTO stores (store_code, store_name, pos_branch, pos_brandcode, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(store_code) DO UPDATE SET
            store_name    = excluded.store_name,
            pos_branch    = excluded.pos_branch,
            pos_brandcode = excluded.pos_brandcode
        """,
        (settings.store_code, settings.store_name,
         settings.pos_branch, settings.pos_brandcode, now()),
    )
    row = session.execute(
        "SELECT store_id FROM stores WHERE store_code = ?", (settings.store_code,)
    ).fetchone()
    return int(row["store_id"])


# ── 주문 ──────────────────────────────────────────────────

def upsert_orders(session: Session, store_id: int, orders: list[Order]) -> int:
    session.executemany(
        """
        INSERT INTO orders (
            store_id, order_no, biz_date, sold_at, paid_at,
            total_amt, discount_amt, net_amt, vat_amt,
            cash_amt, card_amt, gift_amt, point_amt, credit_amt, prepaid_amt,
            card_issuer, card_acquirer, table_name, collected_at
        ) VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?,?,?,?, ?,?,?,?)
        ON CONFLICT(store_id, order_no) DO UPDATE SET
            biz_date=excluded.biz_date, sold_at=excluded.sold_at, paid_at=excluded.paid_at,
            total_amt=excluded.total_amt, discount_amt=excluded.discount_amt,
            net_amt=excluded.net_amt, vat_amt=excluded.vat_amt,
            cash_amt=excluded.cash_amt, card_amt=excluded.card_amt,
            gift_amt=excluded.gift_amt, point_amt=excluded.point_amt,
            credit_amt=excluded.credit_amt, prepaid_amt=excluded.prepaid_amt,
            card_issuer=excluded.card_issuer, card_acquirer=excluded.card_acquirer,
            table_name=excluded.table_name, collected_at=excluded.collected_at
        """,
        [
            (store_id, o.order_no, o.biz_date, o.sold_at, o.paid_at,
             o.total_amt, o.discount_amt, o.net_amt, o.vat_amt,
             o.cash_amt, o.card_amt, o.gift_amt, o.point_amt, o.credit_amt, o.prepaid_amt,
             o.card_issuer, o.card_acquirer, o.table_name, now())
            for o in orders
        ],
    )
    return len(orders)


# ── 집계 ──────────────────────────────────────────────────

def upsert_daily(session: Session, store_id: int, daily: list[DailySales]) -> int:
    session.executemany(
        """
        INSERT INTO daily_sales (
            store_id, biz_date, sales_amount, order_count, discount_amt, cancel_amt,
            vat_amt, cash_amt, card_amt, etc_amt, is_closed, updated_at
        ) VALUES (?,?,?,?,?,?, ?,?,?,?,?,?)
        ON CONFLICT(store_id, biz_date) DO UPDATE SET
            sales_amount=excluded.sales_amount, order_count=excluded.order_count,
            discount_amt=excluded.discount_amt, cancel_amt=excluded.cancel_amt,
            vat_amt=excluded.vat_amt, cash_amt=excluded.cash_amt,
            card_amt=excluded.card_amt, etc_amt=excluded.etc_amt,
            is_closed=excluded.is_closed, updated_at=excluded.updated_at
        """,
        [
            # is_closed 는 bool 로 넘긴다. PostgreSQL 은 BOOLEAN 컬럼에 int 를 받지 않고,
            # SQLite 는 bool 을 0/1 로 바인딩하므로 양쪽 다 성립한다.
            (store_id, d.biz_date, d.sales_amount, d.order_count, d.discount_amt, d.cancel_amt,
             d.vat_amt, d.cash_amt, d.card_amt, d.etc_amt, bool(d.is_closed), now())
            for d in daily
        ],
    )
    return len(daily)


def replace_hourly(
    session: Session, store_id: int,
    hourly: list[HourlySales], biz_dates: list[str],
) -> int:
    """
    해당 날짜의 시간대 행을 지우고 다시 넣는다.
    주문이 취소로 사라지면 시간대 행도 없어져야 하는데 UPSERT만으로는 남는다.
    """
    session.executemany(
        "DELETE FROM hourly_sales WHERE store_id = ? AND biz_date = ?",
        [(store_id, date) for date in biz_dates],
    )
    session.executemany(
        """
        INSERT INTO hourly_sales (store_id, biz_date, hour, sales_amount, order_count)
        VALUES (?,?,?,?,?)
        """,
        [(store_id, h.biz_date, h.hour, h.sales_amount, h.order_count) for h in hourly],
    )
    return len(hourly)


# ── 메뉴 ──────────────────────────────────────────────────

def upsert_menu_sales(session: Session, store_id: int, sales: list[MenuSale]) -> int:
    """메뉴 마스터를 먼저 갱신한 뒤 판매 실적을 넣는다."""
    session.executemany(
        # is_active 는 방언마다 리터럴이 다르다 (SQLite 1 / PostgreSQL TRUE).
        f"""
        INSERT INTO menus (store_id, menu_code, menu_name, category, first_seen, last_seen)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(store_id, menu_code) DO UPDATE SET
            menu_name = excluded.menu_name,
            category  = excluded.category,
            last_seen = excluded.last_seen,
            is_active = {session.dialect.true}
        """,
        # first_seen 은 INSERT 때만 들어간다 — DO UPDATE 에서 건드리지 않는다.
        [(store_id, s.menu_code, s.menu_name, s.category, now(), s.biz_date) for s in sales],
    )

    codes = {s.menu_code for s in sales}
    if not codes:
        return 0
    placeholders = ",".join("?" * len(codes))
    id_by_code = {
        row["menu_code"]: row["menu_id"]
        for row in session.execute(
            f"SELECT menu_id, menu_code FROM menus WHERE store_id = ? "
            f"AND menu_code IN ({placeholders})",
            (store_id, *codes),
        ).fetchall()
    }

    session.executemany(
        """
        INSERT INTO menu_sales (store_id, biz_date, menu_id, quantity, sales_amount)
        VALUES (?,?,?,?,?)
        ON CONFLICT(store_id, biz_date, menu_id) DO UPDATE SET
            quantity=excluded.quantity, sales_amount=excluded.sales_amount
        """,
        [
            (store_id, s.biz_date, id_by_code[s.menu_code], s.quantity, s.sales_amount)
            for s in sales
        ],
    )
    return len(sales)


# ── 취소 ──────────────────────────────────────────────────

def upsert_cancels(session: Session, store_id: int, cancels: list[Cancel]) -> int:
    session.executemany(
        """
        INSERT INTO order_cancels (
            store_id, biz_date, order_no, seq, cancel_type,
            sold_at, canceled_at, item_name, quantity, amount, reason
        ) VALUES (?,?,?,?,?, ?,?,?,?,?,?)
        ON CONFLICT(store_id, biz_date, order_no, seq) DO UPDATE SET
            cancel_type=excluded.cancel_type, sold_at=excluded.sold_at,
            canceled_at=excluded.canceled_at, item_name=excluded.item_name,
            quantity=excluded.quantity, amount=excluded.amount, reason=excluded.reason
        """,
        [
            (store_id, c.biz_date, c.order_no, c.seq, c.cancel_type,
             c.sold_at, c.canceled_at, c.item_name, c.quantity, c.amount, c.reason)
            for c in cancels
        ],
    )
    return len(cancels)


# ── 수집 이력 / 원본 (FR-COL-06 / FN-607) ──────────────────

@dataclass
class CollectionLog:
    store_id: int
    report_type: str
    started_at: str
    target_from: str
    target_to: str


def write_log(
    session: Session, log: CollectionLog,
    status: str, record_count: int, error_message: str | None = None,
) -> None:
    session.execute(
        """
        INSERT INTO collection_logs (
            store_id, report_type, started_at, finished_at,
            target_from, target_to, status, record_count, error_message
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (log.store_id, log.report_type, log.started_at, now(),
         log.target_from, log.target_to, status, record_count, error_message),
    )


def save_raw_file(
    session: Session, store_id: int, report_type: str,
    target_from: str, target_to: str, content: bytes,
) -> Path:
    """
    원본 HTML을 파일로 남기고 경로·해시만 DB에 기록한다.

    ⚠ GitHub Actions에서 수집하면 이 파일은 런너가 사라질 때 함께 사라진다.
      기록은 남지만 파일은 없다 — 재파싱이 필요하면 POS에서 다시 받아야 한다.
    """
    directory = ROOT / "data" / "raw" / target_from[:4] / target_from[4:6]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report_type}_{target_from}_{target_to}.html"
    path.write_bytes(content)

    session.execute(
        """
        INSERT INTO raw_files (
            store_id, report_type, target_from, target_to,
            file_path, byte_size, sha256, collected_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (store_id, report_type, target_from, target_to,
         str(path.relative_to(ROOT)), len(content),
         hashlib.sha256(content).hexdigest(), now()),
    )
    return path


# ── 조회 (검증·API용) ──────────────────────────────────────

def date_range_in_db(session: Session, store_id: int) -> tuple[str | None, str | None]:
    row = session.execute(
        "SELECT MIN(biz_date) AS f, MAX(biz_date) AS t FROM daily_sales WHERE store_id = ?",
        (store_id,),
    ).fetchone()
    return (row["f"], row["t"]) if row else (None, None)


def count_rows(session: Session, table: str) -> int:
    """`table`은 호출자가 정하는 상수다 — 외부 입력을 넣지 않는다."""
    return int(session.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
