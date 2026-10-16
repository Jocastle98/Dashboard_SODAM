"""
신메뉴 성과 (FN-252) + 신메뉴 기준 설정 (FN-253 / FR-DASH-15).

「메뉴별 매출 TOP 10」은 잘 팔리는 메뉴를 보여준다. 새로 들인 메뉴는 아직 양이
적어서 그 표에 올라오지 않는다 — 정작 사장님이 가장 궁금해하는 것인데 화면에서
사라져 있다. 그래서 순위표 **위에** 따로 둔다.

─────────────────────────────────────────────────────────────
무엇을 "신메뉴"로 보는가 — 그리고 왜 그것이 근사치인가
─────────────────────────────────────────────────────────────

POS 는 "이 메뉴를 언제 등록했는지"를 알려주지 않는다. 우리가 가진 것은 판매 실적뿐이므로
**첫 판매일**(`MIN(menu_sales.biz_date)`)을 등록일의 근사치로 쓴다.

`menus.first_seen` 은 쓸 수 없다. 거기엔 수집 시각이 들어간다 —
12개월 백필을 한 번에 돌린 DB에서는 100개 메뉴가 전부 같은 값이다.

근사치이므로 두 방향으로 틀린다. 각각에 대응한다:

1. **오래된 메뉴가 신메뉴로 잡힌다.**
   드물게 팔리는 메뉴(양지, 특정 주류)는 관측 시작 직후에야 처음 팔린다.
   실제로 기준을 12개월로 늘리면 100개 중 71개가 "신규"로 잡혔다.
   → 관측 시작 후 `WARMUP_DAYS` 안에 처음 팔린 메뉴는 자동 판정에서 뺀다.

2. **등록만 하고 아직 안 팔린 메뉴는 안 잡힌다.**
   → 자동으로는 알 수 없다. 사장님이 직접 지정한다 (`menu_overrides`).

수동 지정은 **자동 판정을 이긴다.** 워밍업 제외도 분류 필터도 넘어선다 —
사장님이 "이건 신메뉴다"라고 한 것을 데이터가 뒤집을 근거가 없기 때문이다.

─────────────────────────────────────────────────────────────
분류 필터 (2026-10-16 추가)
─────────────────────────────────────────────────────────────

첫 판매일만으로 거르면 POS `기타` 분류의 옵션(`성인`·`반반`·`목심`)이 쏟아진다.
사장님이 보려는 것은 새로 들인 **요리**이므로 분류로 한 번 더 좁힌다.
기본은 `월남쌈샤브샤브` 하나다.

⚠ **분류 하나로 고정하지 않는다.** 같은 신메뉴가 용량에 따라 다른 분류로 들어간다 —
`토마토샤브` 120g 은 `월남쌈샤브샤브`, 70g 은 `점심특선` 이다. 월남쌈만 걸면 실제로
팔리고 있는 `토마토샤브(70g)`(최근 30일 5개·84,500원)가 화면에서 사라진다.
그래서 분류도 기간과 마찬가지로 사장님이 화면에서 고른다.

─────────────────────────────────────────────────────────────
기준일은 언제를 기준으로 세는가
─────────────────────────────────────────────────────────────

기준일 = **조회 기간의 종료일** − 기준 개월수.

'오늘'이 아니라 종료일인 이유: 화면에 보이는 숫자와 어긋나지 않게 하기 위해서다.
기본 조회(최근 7일/30일)에서 종료일은 어제이므로 사실상 '오늘 기준'과 같고,
과거 기간을 들여다볼 때는 "그 시점의 신메뉴"를 보여준다.

그래서 창에는 **끝이 둘 다 있다**: `기준일 ≤ 첫 판매일 ≤ 조회 종료일`.
위쪽 끝이 없으면 8월을 보는데 10월에 처음 팔린 메뉴가 목록에 끼어든다 —
그때는 아직 없던 메뉴이고 당연히 매출도 0원이라, 사장님에게는 설명되지 않는 빈 줄이다.
(실제로 프로덕션 DB 에서 드러난 문제다.)
"""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date, timedelta

from ..repository import menu as menu_repo
from ..repository import settings as settings_repo
from .menu_alias import display_name
from .period import Period
from collector.db import Session

SETTING_KEY = "new_menu"

DEFAULT_WINDOW_MONTHS = 3        # 사용자가 정한 기본값 — "3달 사이에 추가된 메뉴"
MIN_WINDOW_MONTHS = 1
MAX_WINDOW_MONTHS = 36

# 관측 시작 직후 구간. 이 안에 첫 판매가 찍힌 메뉴는 자동 판정에서 뺀다.
# 30일인 이유: 주 1회꼴로만 팔리는 메뉴도 한 달이면 한 번은 찍힌다.
# 더 늘리면 관측 시작 직후에 진짜로 들어온 신메뉴를 놓친다.
WARMUP_DAYS = 30

MODE_MONTHS = "months"
MODE_SINCE = "since"

# 기본으로 볼 분류 (사용자 지정, 2026-10-16).
#
# POS `기타` 분류에는 메뉴가 아니라 옵션(`성인`·`반반`·`목심`)이 들어 있고,
# 2026-08-18 에 그 분류가 통째로 생기면서 13개가 한꺼번에 신메뉴로 잡혔다.
# 사장님이 보려는 것은 새로 들인 **요리**다.
#
# ⚠ 하나로 고정하지 않는다. `토마토샤브`·`우유마라샤브` 는 같은 신메뉴인데
#   120g 은 `월남쌈샤브샤브`, 70g 은 `점심특선` 으로 들어간다 — 월남쌈만 걸면
#   실제로 팔리고 있는 `토마토샤브(70g)` 가 사라진다. 그래서 화면에서 고를 수 있게 한다.
DEFAULT_CATEGORIES: tuple[str, ...] = ("월남쌈샤브샤브",)


class InvalidCriteria(ValueError):
    """설정 값이 규칙에 맞지 않는다."""


@dataclass(frozen=True)
class Criteria:
    """신메뉴 판정 기준. `since` **이후**에 처음 팔린 메뉴를 신메뉴로 본다."""

    mode: str                   # 'months' — 종료일 기준 N개월 / 'since' — 날짜 고정
    months: int | None
    since: date
    # 볼 분류. `None` 이면 전체. 날짜 방식과 무관하게 따로 걸린다.
    categories: tuple[str, ...] | None = DEFAULT_CATEGORIES

    def as_json(self) -> str:
        payload: dict = ({"mode": MODE_SINCE, "since": self.since.isoformat()}
                         if self.mode == MODE_SINCE
                         else {"mode": MODE_MONTHS, "months": self.months})
        payload["categories"] = list(self.categories) if self.categories else None
        return json.dumps(payload, ensure_ascii=False)

    def as_dict(self) -> dict:
        return {"mode": self.mode, "months": self.months, "since": self.since.isoformat(),
                "categories": list(self.categories) if self.categories else None}

    def covers(self, category: str | None) -> bool:
        """이 분류를 보기로 했나. 분류를 안 걸었으면 전부 본다."""
        return self.categories is None or category in self.categories


# ── 기준 읽기·쓰기 ──────────────────────────────────────

def load_criteria(session: Session, store_id: int, anchor: date) -> Criteria:
    """
    저장된 기준을 읽는다. 없거나 깨졌으면 기본값(3개월)으로 돌아간다.

    설정이 깨졌다고 화면이 비면 안 된다 — 사장님은 고칠 방법이 없다.
    """
    raw = settings_repo.read(session, store_id, SETTING_KEY)
    if not raw:
        return months_criteria(DEFAULT_WINDOW_MONTHS, anchor)
    try:
        return criteria_from(json.loads(raw), anchor)
    except (ValueError, TypeError):
        return months_criteria(DEFAULT_WINDOW_MONTHS, anchor)


def save_criteria(session: Session, store_id: int, payload: dict, anchor: date) -> Criteria:
    """PUT /api/menu/new/settings — 검증한 뒤 저장한다."""
    criteria = criteria_from(payload, anchor)
    settings_repo.write(session, store_id, SETTING_KEY, criteria.as_json())
    return criteria


def criteria_from(payload: dict, anchor: date) -> Criteria:
    """저장 형태(JSON) ↔ `Criteria` 변환의 단일 출처. 검증도 여기서 한다."""
    if not isinstance(payload, dict):
        raise InvalidCriteria("설정 형식이 올바르지 않습니다.")

    categories = _categories_from(payload)

    mode = payload.get("mode", MODE_MONTHS)
    if mode == MODE_SINCE:
        try:
            since = date.fromisoformat(str(payload.get("since", "")))
        except ValueError as error:
            raise InvalidCriteria("기준일 형식은 YYYY-MM-DD 여야 합니다.") from error
        return Criteria(MODE_SINCE, None, since, categories)

    if mode != MODE_MONTHS:
        raise InvalidCriteria("기준 방식은 months 또는 since 여야 합니다.")

    try:
        months = int(payload.get("months", DEFAULT_WINDOW_MONTHS))
    except (TypeError, ValueError) as error:
        raise InvalidCriteria("기준 개월수는 숫자여야 합니다.") from error
    if not MIN_WINDOW_MONTHS <= months <= MAX_WINDOW_MONTHS:
        raise InvalidCriteria(
            f"기준 개월수는 {MIN_WINDOW_MONTHS}~{MAX_WINDOW_MONTHS} 사이여야 합니다.")
    return months_criteria(months, anchor, categories)


def _categories_from(payload: dict) -> tuple[str, ...] | None:
    """
    키가 **없으면** 기본 분류, `null`/`[]` 면 전체.

    둘을 구분하는 이유: 이 기능이 생기기 전에 저장된 설정(`categories` 키 없음)은
    기본값으로 읽혀야 하고, 사장님이 화면에서 "전체"를 고른 것은 그 선택대로
    남아야 한다. 같게 다루면 전체 선택이 저장 직후 기본값으로 되돌아간다.
    """
    if "categories" not in payload:
        return DEFAULT_CATEGORIES
    raw = payload["categories"]
    if raw is None:
        return None
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise InvalidCriteria("분류는 문자열 목록이어야 합니다.")
    return tuple(dict.fromkeys(raw)) or None          # 중복 제거, 빈 목록은 전체


def months_criteria(months: int, anchor: date,
                    categories: tuple[str, ...] | None = DEFAULT_CATEGORIES) -> Criteria:
    return Criteria(MODE_MONTHS, months, minus_months(anchor, months), categories)


def minus_months(day: date, months: int) -> date:
    """
    달력 기준으로 N개월 전. `30 × N일`이 아니다.

    "3달 사이"는 사장님의 달력 감각이다. 30일 곱셈으로 하면 기준일이
    분기마다 며칠씩 밀려서, 같은 메뉴가 어느 날 갑자기 신메뉴에서 빠진다.
    말일 보정을 한다 — 3월 31일의 1개월 전은 2월 28일(윤년이면 29일)이다.
    """
    index = day.month - 1 - months
    year = day.year + index // 12
    month = index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


# ── 판정 ────────────────────────────────────────────────

def evaluate(session: Session, store_id: int, period: Period) -> dict:
    """GET /api/menu/new — 위젯이 그릴 것 전부 (FN-252)."""
    criteria, rows, overrides, warmup_until = _inputs(session, store_id, period)
    total_sales = menu_repo.total_sales(session, store_id, *period.iso)

    items = [
        _item(row, overrides)
        for row in rows
        if _is_new(row, criteria, overrides, warmup_until, period.date_to)
    ]
    items.sort(key=_order)
    for item in items:
        item["share"] = round(item["sales"] / total_sales * 100, 1) if total_sales else 0.0

    return {
        "criteria": criteria.as_dict(),
        "baseline": {
            "dataFrom": _first_data_date(rows),
            "warmupUntil": warmup_until.isoformat() if warmup_until else None,
            "warmupDays": WARMUP_DAYS,
        },
        "totals": _totals(items, total_sales),
        "data": items,
    }


def _totals(items: list[dict], total_sales: int) -> dict:
    """
    합계는 **매출이 발생한 신메뉴만** 더한다.

    섞으면 숫자가 거짓말을 한다. 2026-08-18 에 POS 에 `기타` 분류가 통째로 생기면서
    `성인`·`반반`·`목심` 같은 기존 옵션이 새 메뉴코드로 다시 등록됐다. 규칙상으로는
    "3개월 안에 추가된 메뉴"가 맞지만 전부 0원이고 수량만 수천 개다 —
    그대로 더하면 "신메뉴 4,272개 팔림"이 되는데 실제 판매 메뉴는 144개였다.

    목록에서 빼지는 않는다(사용자 결정). 0원 항목은 정렬상 아래로 내려가고,
    `count` 와 `soldCount` 의 차이가 "잡히긴 했지만 매출이 없는 것들"을 드러낸다.
    """
    sold = [item for item in items if item["sales"] > 0]
    sales = sum(item["sales"] for item in sold)
    return {
        "count": len(items),
        "soldCount": len(sold),
        "quantity": sum(item["quantity"] for item in sold),
        "sales": sales,
        "share": round(sales / total_sales * 100, 1) if total_sales else 0.0,
    }


def catalog(session: Session, store_id: int, period: Period) -> dict:
    """
    GET /api/menu/new/catalog — 수동 지정 패널이 쓰는 전체 메뉴 목록 (FN-253).

    `evaluate()` 와 같은 판정을 쓰되 **거르지 않는다.** 자동 판정 결과와
    수동 지정을 따로 돌려주어, 사장님이 "자동으로는 신메뉴가 아닌데 내가 지정했다"를
    화면에서 구분할 수 있게 한다.
    """
    criteria, rows, overrides, warmup_until = _inputs(session, store_id, period)

    items = []
    for row in rows:
        code = row["menu_code"]
        item = _item(row, overrides)
        item["auto"] = _is_auto_new(row, criteria, warmup_until, period.date_to)
        item["override"] = overrides.get(code)          # True / False / None
        item["isNew"] = _is_new(row, criteria, overrides, warmup_until, period.date_to)
        items.append(item)

    return {
        "criteria": criteria.as_dict(),
        # 분류 칩은 **실제 데이터에 있는 것**만 띄운다. 목록을 코드에 박아 두면
        # POS 에 분류가 새로 생길 때(2026-08-18 `기타`) 화면에서 고를 수 없다.
        "categories": _available_categories(rows),
        "data": items,
    }


def _available_categories(rows) -> list[str]:
    """많이 쓰이는 분류가 앞에 오도록. 같은 수면 이름순 — 순서가 흔들리지 않게."""
    counts: dict[str, int] = {}
    for row in rows:
        category = row["category"]
        if category:
            counts[category] = counts.get(category, 0) + 1
    return [name for name, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


class UnknownMenu(LookupError):
    """없는 메뉴코드를 지정하려 했다."""


def set_override(session: Session, store_id: int,
                 menu_code: str, is_new: bool | None) -> None:
    """
    `None` 이면 지정을 지운다 — 다시 자동 판정에 맡긴다.

    없는 메뉴코드는 거절한다. 받아 두면 `menu_overrides` 에 아무 데도 닿지 않는
    행이 남고, 화면에는 나타나지 않아 지울 방법도 없다.
    """
    if menu_repo.find_name(session, store_id, menu_code) is None:
        raise UnknownMenu(menu_code)
    if is_new is None:
        settings_repo.clear_override(session, store_id, menu_code)
    else:
        settings_repo.set_override(session, store_id, menu_code, bool(is_new))


# ── 내부 ────────────────────────────────────────────────

def _inputs(session: Session, store_id: int, period: Period):
    """`evaluate()` 와 `catalog()` 가 같은 입력을 보도록 한 곳에 모은다."""
    criteria = load_criteria(session, store_id, period.date_to)
    rows = menu_repo.catalog(session, store_id, *period.iso)
    overrides = settings_repo.overrides(session, store_id)
    return criteria, rows, overrides, _warmup_until(rows)


def _warmup_until(rows) -> date | None:
    first = _first_data_date(rows)
    return date.fromisoformat(first) + timedelta(days=WARMUP_DAYS) if first else None


def _first_data_date(rows) -> str | None:
    """
    관측 시작일. `catalog()` 가 첫 판매일 내림차순이므로 마지막 행이 가장 이르다.

    `menu_repo.first_data_date()` 를 또 부르지 않는다 — 같은 사실을 두 번 묻는
    쿼리가 되고, 둘이 어긋날 여지가 생긴다.
    """
    return rows[-1]["first_sold"] if rows else None


def _is_new(row, criteria: Criteria, overrides: dict[str, bool],
            warmup_until: date | None, anchor: date) -> bool:
    """
    수동 지정이 자동 판정을 이긴다 — 워밍업 제외까지 넘어선다.

    **단 하나, 조회 기간이 끝날 때까지 한 번도 안 팔린 메뉴는 예외다.**
    이것은 신메뉴냐 아니냐의 문제가 아니라 그 기간에 존재했느냐의 문제라서,
    사장님의 지정으로 뒤집을 수 있는 성질이 아니다.
    """
    if not _existed_by(row, anchor):
        return False
    override = overrides.get(row["menu_code"])
    if override is not None:
        return override
    return _is_auto_new(row, criteria, warmup_until, anchor)


def _is_auto_new(row, criteria: Criteria, warmup_until: date | None, anchor: date) -> bool:
    if not _existed_by(row, anchor):
        return False
    if not criteria.covers(row["category"]):
        return False                                    # 보기로 한 분류가 아니다
    first_sold = row["first_sold"]
    if warmup_until and first_sold <= warmup_until.isoformat():
        return False                                    # 관측 시작 구간 — 근거 없음
    return first_sold >= criteria.since.isoformat()


def _existed_by(row, anchor: date) -> bool:
    """조회 기간이 끝나는 날까지 한 번이라도 팔린 적이 있나."""
    first_sold = row["first_sold"]
    return bool(first_sold) and first_sold <= anchor.isoformat()


def _item(row, overrides: dict[str, bool]) -> dict:
    code = row["menu_code"]
    return {
        "menuCode": code,
        # POS 원본 대신 표시명 (FN-251). 이름은 한 곳에서만 정한다.
        "menuName": display_name(code, row["menu_name"]),
        "category": row["category"],
        "firstSoldAt": row["first_sold"],
        "lastSoldAt": row["last_sold"],
        "quantity": int(row["quantity"] or 0),
        "sales": int(row["sales"] or 0),
        "share": 0.0,
        "source": "manual" if overrides.get(code) is not None else "auto",
    }


def _order(item: dict) -> tuple:
    """
    매출 큰 순. **매출 0원 옵션 항목(육수·반반 등)은 자연히 아래로 내려간다.**

    `menu_repo.ranking()` 처럼 0원을 빼지는 않는다. 신메뉴는 애초에 몇 개 안 되고,
    새로 생긴 선택 옵션이 얼마나 선택됐는지는 수량으로 읽을 수 있기 때문이다.
    동점이 많으므로 `menu_code` 로 순서를 못박는다 (`ranking()` 과 같은 이유).
    """
    first = item["firstSoldAt"]
    recency = date.fromisoformat(first).toordinal() if first else 0
    return (-item["sales"], -item["quantity"], -recency, item["menuCode"])
