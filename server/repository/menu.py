"""메뉴 조회 — 순위 / 추이."""

from __future__ import annotations

from collector.db import Row, Session


# 정렬 기준 + **동점 처리**.
#
# tie-break 가 없으면 DB·실행계획에 따라 동점 메뉴의 순서가 달라진다.
# 육수·반반 같은 옵션 메뉴는 sales=0 이라 동점이 대량으로 생기므로,
# "수량순 TOP 10"이 새로고침마다 흔들리고 rankChange 도 엉뚱하게 나온다.
# menu_code 로 마지막을 못박아 어느 DB에서든 같은 순서가 나오게 한다.
SORT_ORDERS = {
    "sales":    "sales DESC, quantity DESC, m.menu_code ASC",
    "quantity": "quantity DESC, sales DESC, m.menu_code ASC",
}


def ranking(session: Session, store_id: int,
            date_from: str, date_to: str, limit: int, sort_by: str) -> list[Row]:
    """
    메뉴 순위 (FN-250).

    **매출이 0원인 항목은 제외한다.** POS 의 `menu_sales` 에는 판매 메뉴 말고도
    옵션 항목이 섞여 있다 — 인원 구분(`성인`/`초등학생`), 육수 선택(`순한맛(육수)`,
    `반반`), 고기 종류(`목심`), 추가(`(써)고기추가(...)`). 수량은 잡히지만 매출이 0원이다.

    빼지 않으면 **수량순 1위가 `성인` 1,874개(0원)** 가 되어 사장님이 메뉴 순위로
    읽을 수 없다. "메뉴별 매출" 위젯이므로 매출이 발생한 메뉴만 센다.

    옵션 자체의 비율(예: 육수 선택 분포)은 별도 분석 주제이며 이 위젯의 일이 아니다.
    `total_sales` 는 그대로 둔다 — 옵션은 0원이라 비중 분모에 영향이 없다.
    """
    order_by = SORT_ORDERS.get(sort_by, SORT_ORDERS["sales"])
    return session.execute(
        f"""
        SELECT m.menu_code, m.menu_name, m.category,
               SUM(ms.quantity)     AS quantity,
               SUM(ms.sales_amount) AS sales
        FROM menu_sales ms
        JOIN menus m ON m.menu_id = ms.menu_id
        WHERE ms.store_id = ? AND ms.biz_date BETWEEN ? AND ?
        GROUP BY m.menu_id
        HAVING SUM(ms.sales_amount) > 0
        ORDER BY {order_by}
        LIMIT ?
        """,
        (store_id, date_from, date_to, limit),
    ).fetchall()


def total_sales(session: Session, store_id: int,
                date_from: str, date_to: str) -> int:
    row = session.execute(
        """
        SELECT COALESCE(SUM(sales_amount), 0) AS total
        FROM menu_sales WHERE store_id = ? AND biz_date BETWEEN ? AND ?
        """,
        (store_id, date_from, date_to),
    ).fetchone()
    return int(row["total"])


def all_shares(session: Session, store_id: int,
               date_from: str, date_to: str) -> list[Row]:
    """
    ABC 등급은 전체 메뉴의 누적 비중으로 정한다 — TOP 10만 봐서는 계산할 수 없다.

    tie-break 를 명시한다: 누적 순서가 등급 경계를 결정하므로, 동점 메뉴의
    순서가 흔들리면 경계에 걸친 메뉴의 등급이 실행마다 A↔B 로 바뀐다.
    """
    return session.execute(
        """
        SELECT m.menu_code, SUM(ms.sales_amount) AS sales
        FROM menu_sales ms
        JOIN menus m ON m.menu_id = ms.menu_id
        WHERE ms.store_id = ? AND ms.biz_date BETWEEN ? AND ?
        GROUP BY m.menu_id
        ORDER BY sales DESC, m.menu_code ASC
        """,
        (store_id, date_from, date_to),
    ).fetchall()


def trend(session: Session, store_id: int, menu_code: str,
          date_from: str, date_to: str) -> list[Row]:
    return session.execute(
        """
        SELECT ms.biz_date, ms.quantity, ms.sales_amount
        FROM menu_sales ms
        JOIN menus m ON m.menu_id = ms.menu_id
        WHERE ms.store_id = ? AND m.menu_code = ? AND ms.biz_date BETWEEN ? AND ?
        ORDER BY ms.biz_date
        """,
        (store_id, menu_code, date_from, date_to),
    ).fetchall()


def find_name(session: Session, store_id: int, menu_code: str) -> str | None:
    row = session.execute(
        "SELECT menu_name FROM menus WHERE store_id = ? AND menu_code = ?",
        (store_id, menu_code),
    ).fetchone()
    return row["menu_name"] if row else None


# ── 신메뉴 판정의 근거 (FN-252) ─────────────────────────

def catalog(session: Session, store_id: int,
            date_from: str, date_to: str) -> list[Row]:
    """
    메뉴마다 **첫 판매일**과 **조회 기간 실적**을 한 번에 가져온다.

    ⚠ `menus.first_seen` 을 쓰지 않는다. 그 컬럼은 `collector/repository.py` 가
    `now()`(수집 시각)를 넣기 때문에, 12개월 백필을 한 번에 돌린 DB에서는
    100개 메뉴의 값이 전부 같은 날이다 — 신메뉴 판별에 쓸 수 없다.

    대신 `MIN(menu_sales.biz_date)` 를 쓴다. 이것도 POS **등록일**은 아니고
    **첫 판매일**이다. 한계는 service/new_menu.py 가 워밍업 구간 제외와
    수동 지정으로 메운다.

    기간 실적은 WHERE 가 아니라 CASE 로 거른다 — WHERE 로 거르면 그 기간에
    안 팔린 메뉴가 행째로 사라져서 첫 판매일을 알 수 없고, "신메뉴인데 이번 기간엔
    0원" 이라는 사실도 화면에서 지워진다.
    """
    return session.execute(
        """
        SELECT m.menu_code, m.menu_name, m.category,
               MIN(ms.biz_date) AS first_sold,
               MAX(ms.biz_date) AS last_sold,
               COALESCE(SUM(CASE WHEN ms.biz_date BETWEEN ? AND ?
                                 THEN ms.quantity END), 0)     AS quantity,
               COALESCE(SUM(CASE WHEN ms.biz_date BETWEEN ? AND ?
                                 THEN ms.sales_amount END), 0) AS sales
        FROM menu_sales ms
        JOIN menus m ON m.menu_id = ms.menu_id
        WHERE ms.store_id = ?
        GROUP BY m.menu_id
        ORDER BY first_sold DESC, m.menu_code ASC
        """,
        (date_from, date_to, date_from, date_to, store_id),
    ).fetchall()


def first_data_date(session: Session, store_id: int) -> str | None:
    """
    메뉴 실적을 가진 가장 이른 날. **관측 시작일**이다.

    이 날짜 언저리에 처음 팔린 메뉴는 "새로 생긴 메뉴" 가 아니라
    "관측을 그때부터 시작했을 뿐" 이다. 둘을 구분할 근거가 데이터에 없다.
    """
    row = session.execute(
        "SELECT MIN(biz_date) AS first FROM menu_sales WHERE store_id = ?",
        (store_id,),
    ).fetchone()
    return row["first"] if row and row["first"] else None
