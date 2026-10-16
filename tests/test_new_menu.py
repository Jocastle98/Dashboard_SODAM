"""
신메뉴 판정·설정 테스트 (FN-252 / FN-253).

앞부분은 DB 없이 판정 규칙만 고정한다 — 규칙이 틀리면 화면이 조용히 엉뚱해지는데
실데이터로는 "원래 그런가 보다" 하고 넘어가기 쉽다.
뒷부분은 실제 적재된 DB로 API를 확인한다 (test_api.py 와 같은 방식).
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from collector import repository as collector_repo
from collector.config import Settings
from server.service import new_menu as service
from server.main import app

PERIOD = "from=2026-08-10&to=2026-08-16"
ANCHOR = date(2026, 8, 16)


# 기본 분류 필터에 걸리는 분류로 둔다 — 날짜 규칙을 보는 테스트가
# 분류 때문에 실패하면 무엇이 깨졌는지 읽히지 않는다.
WATCHED = service.DEFAULT_CATEGORIES[0]


def row(code: str, first_sold: str, category: str = WATCHED, **extra) -> dict:
    """Row 는 `row["컬럼"]` 으로만 읽히므로 dict 로 대신할 수 있다."""
    return {"menu_code": code, "menu_name": code, "category": category,
            "first_sold": first_sold, "last_sold": first_sold,
            "quantity": 0, "sales": 0, **extra}


# ── 기준 계산 (DB 없음) ────────────────────────────────────

@pytest.mark.parametrize("day, months, expected", [
    (date(2026, 8, 16), 3,  date(2026, 5, 16)),
    (date(2026, 1, 15), 3,  date(2025, 10, 15)),   # 해를 넘는다
    (date(2026, 8, 16), 12, date(2025, 8, 16)),
    (date(2026, 3, 31), 1,  date(2026, 2, 28)),    # 말일 보정
    (date(2024, 3, 31), 1,  date(2024, 2, 29)),    # 윤년
])
def test_minus_months_follows_the_calendar(day, months, expected):
    """'3달 사이'는 달력 감각이다 — 30×N일로 계산하면 기준일이 분기마다 밀린다."""
    assert service.minus_months(day, months) == expected


def test_default_criteria_is_three_months():
    """사용자가 정한 기본값. 바뀌면 사장님 화면의 신메뉴 목록이 통째로 달라진다."""
    assert service.DEFAULT_WINDOW_MONTHS == 3
    criteria = service.criteria_from({}, ANCHOR)
    assert criteria.months == 3
    assert criteria.since == date(2026, 5, 16)


def test_criteria_accepts_an_explicit_since_date():
    criteria = service.criteria_from({"mode": "since", "since": "2026-01-01"}, ANCHOR)
    assert criteria.mode == "since"
    assert criteria.since == date(2026, 1, 1)
    assert criteria.months is None


def test_criteria_survives_a_round_trip_through_json():
    """저장 형태와 복원이 어긋나면 설정이 저장된 다음 날 원래대로 돌아간다."""
    for payload in ({"mode": "months", "months": 6},
                    {"mode": "since", "since": "2026-01-01"},
                    {"mode": "months", "months": 6, "categories": ["점심특선", "기타"]},
                    {"mode": "since", "since": "2026-01-01", "categories": None}):
        original = service.criteria_from(payload, ANCHOR)
        import json
        restored = service.criteria_from(json.loads(original.as_json()), ANCHOR)
        assert restored == original


@pytest.mark.parametrize("payload", [
    {"mode": "months", "months": 0},
    {"mode": "months", "months": 999},
    {"mode": "months", "months": "석달"},
    {"mode": "since", "since": "2026-13-01"},
    {"mode": "weeks", "weeks": 3},
])
def test_invalid_criteria_is_rejected(payload):
    with pytest.raises(service.InvalidCriteria):
        service.criteria_from(payload, ANCHOR)


# ── 자동 판정 ──────────────────────────────────────────────

def test_menu_first_sold_inside_the_window_is_new():
    criteria = service.months_criteria(3, ANCHOR)          # since = 2026-05-16
    warmup = date(2025, 9, 20)
    assert service._is_auto_new(row("A", "2026-08-13"), criteria, warmup, ANCHOR) is True
    assert service._is_auto_new(row("B", "2026-05-16"), criteria, warmup, ANCHOR) is True
    assert service._is_auto_new(row("C", "2026-05-15"), criteria, warmup, ANCHOR) is False


def test_menu_sold_after_the_period_is_not_listed():
    """
    창에는 끝이 둘 다 있다. 8월을 보는데 10월에 처음 팔린 메뉴가 끼면,
    그 시점엔 없던 메뉴라 매출 0원짜리 설명 안 되는 줄이 생긴다.

    프로덕션 DB(10월까지 적재)로 8월 기간을 조회했을 때 실제로 드러난 문제다.
    """
    criteria = service.months_criteria(3, ANCHOR)          # 종료일 2026-08-16
    warmup = date(2025, 9, 20)
    future = row("LATER", "2026-10-06")
    assert service._is_auto_new(future, criteria, warmup, ANCHOR) is False
    # 사장님이 지정해도 마찬가지다 — 신메뉴냐가 아니라 그때 있었냐의 문제다
    assert service._is_new(future, criteria, {"LATER": True}, warmup, ANCHOR) is False
    # 기간을 10월까지 늘리면 다시 잡힌다
    later = date(2026, 10, 15)
    assert service._is_auto_new(future, service.months_criteria(3, later),
                                warmup, later) is True


def test_warmup_window_blocks_fake_new_menus():
    """
    관측 시작 직후에 처음 팔린 메뉴는 신메뉴가 아니다 — 그때부터 봤을 뿐이다.

    이 가드가 없으면 기준을 12개월로 늘렸을 때 실데이터에서 100개 중 71개가
    "신규"로 잡혔다. 사장님이 신메뉴 목록으로 읽을 수 없는 숫자다.
    """
    criteria = service.months_criteria(12, ANCHOR)         # since = 2025-08-16
    warmup = date(2025, 9, 20)                             # 관측 시작 2025-08-21 + 30일
    assert service._is_auto_new(row("A", "2025-08-22"), criteria, warmup, ANCHOR) is False
    assert service._is_auto_new(row("B", "2025-09-20"), criteria, warmup, ANCHOR) is False
    assert service._is_auto_new(row("C", "2025-09-21"), criteria, warmup, ANCHOR) is True


def test_manual_designation_beats_automatic_judgement():
    """
    사장님 지정이 자동 판정을 이긴다 — 워밍업 제외까지 넘어선다.

    POS 가 메뉴 등록일을 주지 않아 자동 판정이 근사치이기 때문이다.
    뒤집히면 "신메뉴로 지정했는데 안 보인다"가 되고, 사장님은 고칠 방법이 없다.
    """
    criteria = service.months_criteria(3, ANCHOR)
    warmup = date(2025, 9, 20)
    old = row("OLD", "2025-08-22")                         # 자동으로는 워밍업에 걸린다
    recent = row("NEW", "2026-08-13")                      # 자동으로는 신메뉴다

    assert service._is_new(old, criteria, {"OLD": True}, warmup, ANCHOR) is True
    assert service._is_new(recent, criteria, {"NEW": False}, warmup, ANCHOR) is False
    assert service._is_new(recent, criteria, {}, warmup, ANCHOR) is True   # 지정 없음 → 자동


# ── 분류 필터 (2026-10-16) ─────────────────────────────────

def test_default_watches_only_the_wrapped_shabu_category():
    """사용자 지정 기본값. POS `기타` 분류에는 메뉴가 아니라 옵션이 들어 있다."""
    assert service.DEFAULT_CATEGORIES == ("월남쌈샤브샤브",)
    criteria = service.criteria_from({}, ANCHOR)
    assert criteria.categories == ("월남쌈샤브샤브",)
    assert criteria.covers("월남쌈샤브샤브") is True
    assert criteria.covers("기타") is False
    assert criteria.covers(None) is False


def test_category_outside_the_filter_is_not_new():
    criteria = service.months_criteria(3, ANCHOR)
    warmup = date(2025, 9, 20)
    assert service._is_auto_new(row("A", "2026-08-13"), criteria, warmup, ANCHOR) is True
    assert service._is_auto_new(row("B", "2026-08-13", "기타"),
                                criteria, warmup, ANCHOR) is False


def test_manual_designation_beats_the_category_filter():
    """분류 밖이라도 사장님이 지정하면 나온다 — 워밍업 제외와 같은 규칙이다."""
    criteria = service.months_criteria(3, ANCHOR)
    warmup = date(2025, 9, 20)
    other = row("ETC", "2026-08-13", "기타")
    assert service._is_new(other, criteria, {}, warmup, ANCHOR) is False
    assert service._is_new(other, criteria, {"ETC": True}, warmup, ANCHOR) is True


def test_adding_a_category_never_shrinks_the_list():
    """
    `토마토샤브` 는 120g 이 월남쌈샤브샤브, 70g 이 점심특선이다.
    분류를 하나만 걸면 같은 신메뉴의 반쪽이 사라진다.
    """
    warmup = date(2025, 9, 20)
    lunch = row("LUNCH", "2026-08-13", "점심특선")
    narrow = service.months_criteria(3, ANCHOR, ("월남쌈샤브샤브",))
    wide = service.months_criteria(3, ANCHOR, ("월남쌈샤브샤브", "점심특선"))
    assert service._is_auto_new(lunch, narrow, warmup, ANCHOR) is False
    assert service._is_auto_new(lunch, wide, warmup, ANCHOR) is True


def test_empty_or_null_categories_means_everything():
    """화면의 '전체' 선택. `None` 과 `[]` 둘 다 받는다."""
    for payload in ({"categories": None}, {"categories": []}):
        criteria = service.criteria_from(payload, ANCHOR)
        assert criteria.categories is None
        assert criteria.covers("기타") is True


def test_missing_categories_key_falls_back_to_the_default():
    """
    이 기능이 생기기 전에 저장된 설정에는 `categories` 키가 없다.
    '전체'(null)와 같게 다루면 옵션 수십 개가 갑자기 쏟아진다.
    """
    assert service.criteria_from({"mode": "months", "months": 3},
                                 ANCHOR).categories == service.DEFAULT_CATEGORIES


def test_invalid_categories_are_rejected():
    for payload in ({"categories": "월남쌈샤브샤브"}, {"categories": [1, 2]}):
        with pytest.raises(service.InvalidCriteria):
            service.criteria_from(payload, ANCHOR)


# ── API (실제 DB) ──────────────────────────────────────────

@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings.load()


@pytest.fixture(scope="module")
def seeded(settings: Settings) -> bool:
    try:
        with collector_repo.connect(settings) as connection:
            if collector_repo.count_rows(connection, "menu_sales") == 0:
                pytest.skip("적재된 메뉴 데이터가 없습니다 — `python -m collector.main --days 7`")
            if collector_repo.count_rows(connection, "users") == 0:
                pytest.skip("대시보드 계정이 없습니다 — `python -m server.seed` 실행")
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"DB를 열 수 없습니다: {error}")
    return True


@pytest.fixture
def auth_client(seeded, settings: Settings):
    """
    설정을 건드리는 테스트다 — 끝나면 **원래 값으로 되돌린다.**
    실제 사장님의 DB 를 쓰므로 테스트가 설정을 바꿔 놓고 가면 안 된다.
    """
    from server.db import open_write_connection
    from server.repository import settings as settings_repo
    from server.repository import system as system_repo

    with open_write_connection(settings) as session:
        store_id = system_repo.store_id_by_code(session, settings.store_code)
        saved = settings_repo.read(session, store_id, service.SETTING_KEY)
        saved_overrides = settings_repo.overrides(session, store_id)

    client = TestClient(app)
    response = client.post("/api/auth/login", json={
        "username": settings.dashboard_admin_id,
        "password": settings.dashboard_admin_pw,
    })
    assert response.status_code == 200
    yield client

    with open_write_connection(settings) as session:
        store_id = system_repo.store_id_by_code(session, settings.store_code)
        if saved is None:
            session.execute(
                "DELETE FROM app_settings WHERE store_id = ? AND setting_key = ?",
                (store_id, service.SETTING_KEY))
        else:
            settings_repo.write(session, store_id, service.SETTING_KEY, saved)
        for code in set(settings_repo.overrides(session, store_id)) | set(saved_overrides):
            if code in saved_overrides:
                settings_repo.set_override(session, store_id, code, saved_overrides[code])
            else:
                settings_repo.clear_override(session, store_id, code)


def test_new_menu_requires_login():
    """NFR-SEC-04 — 설정을 바꾸는 엔드포인트도 예외가 아니다."""
    client = TestClient(app)
    assert client.get(f"/api/menu/new?{PERIOD}").status_code == 401
    assert client.put(f"/api/menu/new/settings?{PERIOD}",
                      json={"mode": "months", "months": 6}).status_code == 401
    assert client.put("/api/menu/new/overrides/000021", json={"isNew": True}).status_code == 401


def test_new_menu_returns_criteria_even_when_empty(auth_client):
    """
    신메뉴가 없어도 기준은 돌려줘야 한다 — 화면이 "무슨 기준으로 없는지"를 말해야 한다.
    """
    body = auth_client.get(f"/api/menu/new?{PERIOD}").json()
    assert body["criteria"]["months"] == 3
    assert body["criteria"]["since"] == "2026-05-16"       # 종료일 2026-08-16 기준
    assert "data" in body and "totals" in body


def test_api_applies_the_default_category_filter(auth_client):
    body = auth_client.get(f"/api/menu/new?{PERIOD}").json()
    assert body["criteria"]["categories"] == ["월남쌈샤브샤브"]
    for item in body["data"]:
        assert item["category"] == "월남쌈샤브샤브" or item["source"] == "manual"


def test_catalog_lists_the_categories_present_in_the_data(auth_client):
    """칩 목록을 코드에 박지 않는다 — POS 에 분류가 새로 생겨도 고를 수 있어야 한다."""
    body = auth_client.get(f"/api/menu/new/catalog?{PERIOD}").json()
    assert "월남쌈샤브샤브" in body["categories"]
    assert body["categories"] == list(dict.fromkeys(body["categories"]))   # 중복 없음


def test_saving_categories_persists(auth_client):
    auth_client.put(f"/api/menu/new/settings?{PERIOD}",
                    json={"mode": "months", "months": 3,
                          "categories": ["월남쌈샤브샤브", "점심특선"]})
    body = auth_client.get(f"/api/menu/new?{PERIOD}").json()
    assert body["criteria"]["categories"] == ["월남쌈샤브샤브", "점심특선"]


def test_new_menu_items_are_sorted_with_zero_sales_last(auth_client):
    """매출 0원 옵션(육수·반반)은 빼지 않되 아래로 내려간다."""
    rows = auth_client.get(f"/api/menu/new?{PERIOD}").json()["data"]
    sales = [item["sales"] for item in rows]
    assert sales == sorted(sales, reverse=True)


def test_totals_count_only_menus_that_actually_sold(auth_client):
    """
    합계에 0원 옵션의 수량이 섞이면 숫자가 거짓말을 한다.

    프로덕션에서 2026-08-18 에 POS `기타` 분류가 생기며 `성인`·`반반` 같은 기존
    옵션이 새 코드로 다시 등록됐다. 섞어 더하면 "신메뉴 4,272개 판매"가 되는데
    실제 판매 메뉴는 144개였다.
    """
    body = auth_client.get(f"/api/menu/new?{PERIOD}").json()
    sold = [item for item in body["data"] if item["sales"] > 0]

    assert body["totals"]["count"] == len(body["data"])
    assert body["totals"]["soldCount"] == len(sold)
    assert body["totals"]["sales"] == sum(item["sales"] for item in sold)
    assert body["totals"]["quantity"] == sum(item["quantity"] for item in sold)


def test_widening_the_window_never_shrinks_the_list(auth_client):
    """기간을 늘렸는데 신메뉴가 줄면 판정이 잘못된 것이다."""
    counts = []
    for months in (1, 3, 6, 12):
        saved = auth_client.put(f"/api/menu/new/settings?{PERIOD}",
                                json={"mode": "months", "months": months})
        assert saved.status_code == 200
        counts.append(auth_client.get(f"/api/menu/new?{PERIOD}").json()["totals"]["count"])
    assert counts == sorted(counts)


def test_saved_criteria_persists(auth_client):
    auth_client.put(f"/api/menu/new/settings?{PERIOD}",
                    json={"mode": "since", "since": "2026-01-01"})
    body = auth_client.get(f"/api/menu/new?{PERIOD}").json()
    assert body["criteria"]["mode"] == "since"
    assert body["criteria"]["since"] == "2026-01-01"


def test_invalid_criteria_is_rejected_by_the_api(auth_client):
    response = auth_client.put(f"/api/menu/new/settings?{PERIOD}",
                               json={"mode": "months", "months": 0})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAM"


def test_override_designates_and_excludes(auth_client):
    """사장님 지정이 목록에 그대로 반영된다."""
    catalog = auth_client.get(f"/api/menu/new/catalog?{PERIOD}").json()["data"]
    end = PERIOD.split("to=")[1]
    # 조회 기간 안에 존재했던 메뉴 중에서 고른다 — 종료일 뒤에 처음 팔린 메뉴는
    # 지정해도 목록에 나오지 않는 것이 정상이기 때문이다
    # (test_menu_sold_after_the_period_is_not_listed).
    within = [item for item in catalog if item["firstSoldAt"] <= end]
    auto_new = next(item for item in within if item["auto"])
    not_new = next(item for item in within if not item["auto"])

    auth_client.put(f"/api/menu/new/overrides/{not_new['menuCode']}", json={"isNew": True})
    auth_client.put(f"/api/menu/new/overrides/{auto_new['menuCode']}", json={"isNew": False})

    codes = {item["menuCode"]: item for item in
             auth_client.get(f"/api/menu/new?{PERIOD}").json()["data"]}
    assert not_new["menuCode"] in codes
    assert codes[not_new["menuCode"]]["source"] == "manual"
    assert auto_new["menuCode"] not in codes

    # null 로 되돌리면 다시 자동 판정에 맡겨진다
    auth_client.put(f"/api/menu/new/overrides/{auto_new['menuCode']}", json={"isNew": None})
    codes = {item["menuCode"] for item in
             auth_client.get(f"/api/menu/new?{PERIOD}").json()["data"]}
    assert auto_new["menuCode"] in codes


def test_listed_menus_all_existed_within_the_period(auth_client):
    """조회 종료일 뒤에 처음 팔린 메뉴가 목록에 끼면 안 된다."""
    for period in (PERIOD, "from=2025-10-01&to=2026-08-16"):
        body = auth_client.get(f"/api/menu/new?{period}").json()
        end = period.split("to=")[1]
        for item in body["data"]:
            assert item["firstSoldAt"] <= end, item


def test_override_on_unknown_menu_is_rejected(auth_client):
    """닿지 않는 지정이 DB에 남으면 화면에서 지울 방법이 없다."""
    response = auth_client.put("/api/menu/new/overrides/NO-SUCH-CODE", json={"isNew": True})
    assert response.status_code == 404


def test_override_rejects_non_boolean(auth_client):
    response = auth_client.put("/api/menu/new/overrides/000021", json={"isNew": "네"})
    assert response.status_code == 400


def test_catalog_separates_automatic_and_manual(auth_client):
    """FN-253 패널은 '자동으로는 아닌데 내가 지정했다'를 구분해 보여줘야 한다."""
    body = auth_client.get(f"/api/menu/new/catalog?{PERIOD}").json()
    assert body["data"], "메뉴가 하나도 없습니다"
    for item in body["data"]:
        assert set(("auto", "override", "isNew")) <= set(item)
        expected = item["auto"] if item["override"] is None else item["override"]
        assert item["isNew"] == expected
