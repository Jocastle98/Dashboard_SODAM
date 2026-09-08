"""
API 테스트 — docs/02 5장 명세와 9장 테스트케이스를 고정한다.

실제 적재된 DB를 사용한다. 데이터가 없으면 건너뛴다
(CLAUDE.md: 실데이터로 검증되기 전까지 완료로 표시하지 않는다).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from collector import repository as collector_repo
from collector.config import Settings
from server.main import app

PERIOD = "from=2026-08-10&to=2026-08-16"


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings.load()


@pytest.fixture(scope="module")
def seeded(settings: Settings) -> bool:
    try:
        with collector_repo.connect(settings) as connection:
            if collector_repo.count_rows(connection, "daily_sales") == 0:
                pytest.skip("적재된 데이터가 없습니다 — `python -m collector.main --days 7` 실행")
            if collector_repo.count_rows(connection, "users") == 0:
                pytest.skip("대시보드 계정이 없습니다 — `python -m server.seed` 실행")
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"DB를 열 수 없습니다: {error}")
    return True


@pytest.fixture
def client(seeded) -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_client(client: TestClient, settings: Settings) -> TestClient:
    response = client.post("/api/auth/login", json={
        "username": settings.dashboard_admin_id,
        "password": settings.dashboard_admin_pw,
    })
    assert response.status_code == 200
    return client


# ── 인증 (TC-01 ~ TC-05) ───────────────────────────────────

def test_login_succeeds_with_correct_credentials(client, settings):
    response = client.post("/api/auth/login", json={
        "username": settings.dashboard_admin_id,
        "password": settings.dashboard_admin_pw,
    })
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_login_fails_with_wrong_password(client, settings):
    response = client.post("/api/auth/login", json={
        "username": settings.dashboard_admin_id, "password": "wrong-password",
    })
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_FAILED"


def test_failure_message_does_not_reveal_which_field_was_wrong(client):
    """FN-105 — 계정 열거 방지."""
    unknown = client.post("/api/auth/login",
                          json={"username": "no-such-user", "password": "x"}).json()
    assert unknown["error"]["message"] == "아이디 또는 비밀번호가 올바르지 않습니다."


def test_session_cookie_is_httponly(client, settings):
    """NFR-SEC-03 — 스크립트가 세션 쿠키를 읽을 수 없어야 한다."""
    response = client.post("/api/auth/login", json={
        "username": settings.dashboard_admin_id, "password": settings.dashboard_admin_pw,
    })
    assert "httponly" in response.headers["set-cookie"].lower()


def test_unauthenticated_request_is_rejected(client):
    """TC-04 / NFR-SEC-04."""
    assert client.get(f"/api/summary?{PERIOD}").status_code == 401


def test_logout_invalidates_the_session(auth_client):
    """TC-05."""
    auth_client.post("/api/auth/logout")
    assert auth_client.get(f"/api/summary?{PERIOD}").status_code == 401


def test_login_response_never_contains_pos_credentials(auth_client, settings):
    """NFR-SEC-03 / TC-18 — 응답에 POS 계정이나 해시가 실려서는 안 된다."""
    body = auth_client.get("/api/auth/session").text
    assert settings.pos_user_pw not in body
    assert "password" not in body.lower()


# ── 조회 (TC-06 ~ TC-11) ───────────────────────────────────

def test_daily_returns_one_point_per_day(auth_client):
    """TC-06 — 7일 선택 시 7개."""
    data = auth_client.get(f"/api/sales/daily?{PERIOD}").json()["data"]
    assert len(data) == 7


def test_daily_marks_missing_days_as_null_not_zero(auth_client):
    """FR-DASH-12 — 미수집일을 0원으로 오인하면 안 된다."""
    data = auth_client.get("/api/sales/daily?from=2020-01-01&to=2020-01-03").json()["data"]
    assert all(row["sales"] is None for row in data)
    assert all(row["isClosed"] is False for row in data)


def test_end_before_start_is_rejected(auth_client):
    """TC-08."""
    response = auth_client.get("/api/sales/daily?from=2026-08-16&to=2026-08-10")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAM"


def test_summary_compares_against_previous_period(auth_client):
    """FN-210 — 직전 동일 길이 기간과 비교."""
    body = auth_client.get(f"/api/summary?{PERIOD}").json()
    assert body["period"]["from"] == "2026-08-10"
    assert body["current"]["totalSales"] > 0
    assert set(body["change"]) == {"totalSales", "orderCount", "avgTicket", "dailyAvg"}


def test_avg_ticket_equals_sales_over_orders(auth_client):
    current = auth_client.get(f"/api/summary?{PERIOD}").json()["current"]
    assert current["avgTicket"] == current["totalSales"] // current["orderCount"]


def test_weekday_returns_monday_first(auth_client):
    """FN-230 — 화면 순서(월~일)와 일치해야 한다."""
    data = auth_client.get(f"/api/sales/weekday?{PERIOD}").json()["data"]
    assert [row["dayOfWeek"] for row in data] == ["월", "화", "수", "목", "금", "토", "일"]


def test_hourly_reports_availability_and_peaks(auth_client):
    """TC-13 — 데이터가 없으면 available=false로 위젯을 숨긴다."""
    body = auth_client.get(f"/api/sales/hourly?{PERIOD}").json()
    assert body["available"] is True
    assert 1 <= len(body["peakHours"]) <= 3


def test_hourly_is_unavailable_for_empty_period(auth_client):
    body = auth_client.get("/api/sales/hourly?from=2020-01-01&to=2020-01-02").json()
    assert body["available"] is False


# ── 메뉴 (TC-12) ───────────────────────────────────────────

def test_menu_ranking_shares_are_consistent(auth_client):
    """TC-12 — 비중 합이 실제 매출 비중과 맞아야 한다."""
    body = auth_client.get(f"/api/menu/ranking?{PERIOD}&limit=100").json()
    assert body["totalSales"] > 0
    assert sum(row["sales"] for row in body["data"]) == body["totalSales"]
    assert abs(sum(row["share"] for row in body["data"]) - 100) < 1.0


def test_menu_ranking_is_sorted_by_sales(auth_client):
    data = auth_client.get(f"/api/menu/ranking?{PERIOD}").json()["data"]
    assert data == sorted(data, key=lambda row: -row["sales"])
    assert [row["rank"] for row in data] == list(range(1, len(data) + 1))


def test_menu_ranking_can_sort_by_quantity(auth_client):
    data = auth_client.get(f"/api/menu/ranking?{PERIOD}&sortBy=quantity").json()["data"]
    assert data == sorted(data, key=lambda row: -row["quantity"])


def test_abc_grades_are_assigned(auth_client):
    data = auth_client.get(f"/api/menu/ranking?{PERIOD}").json()["data"]
    assert data[0]["abcGrade"] == "A"
    assert all(row["abcGrade"] in ("A", "B", "C") for row in data)


def test_unknown_menu_returns_404(auth_client):
    response = auth_client.get(f"/api/menu/NO-SUCH-CODE/trend?{PERIOD}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# ── 요일 비교 (FN-235 / FR-DASH-13) ────────────────────────

def test_weekly_compare_returns_seven_weekdays(auth_client):
    body = auth_client.get(f"/api/sales/weekly-compare?{PERIOD}").json()
    assert [row["dayOfWeek"] for row in body["data"]] == ["월", "화", "수", "목", "금", "토", "일"]


def test_weekly_compare_pairs_the_same_weekday_a_week_apart(auth_client):
    """'지난주 수요일 vs 이번주 수요일' — 두 날짜가 정확히 7일 차이여야 한다."""
    from datetime import date

    body = auth_client.get(f"/api/sales/weekly-compare?{PERIOD}").json()
    for row in body["data"]:
        this_day = date.fromisoformat(row["thisWeek"]["date"])
        last_day = date.fromisoformat(row["lastWeek"]["date"])
        assert (this_day - last_day).days == 7


def test_weekly_compare_uses_calendar_weeks(auth_client):
    """이번 주는 월요일에 시작한다 — '최근 7일' 같은 이동 구간이 아니다."""
    body = auth_client.get(f"/api/sales/weekly-compare?{PERIOD}").json()
    assert body["thisWeek"]["from"] == "2026-08-10"      # 월요일
    assert body["lastWeek"]["from"] == "2026-08-03"


def test_weekly_compare_change_matches_the_two_values(auth_client):
    body = auth_client.get(f"/api/sales/weekly-compare?{PERIOD}").json()
    for row in body["data"]:
        this_sales, last_sales = row["thisWeek"]["sales"], row["lastWeek"]["sales"]
        if this_sales is None or last_sales is None:
            assert row["change"] is None       # 0원으로 치면 ▼100%가 된다 (FR-DASH-12)
            continue
        expected = round((this_sales - last_sales) / last_sales * 100, 1)
        assert row["change"] == expected


def test_weekly_compare_total_only_counts_paired_days(auth_client):
    """
    이번 주가 아직 안 끝났을 때 3일 합계와 7일 합계를 비교하면
    사장님이 매출이 반토막 난 것으로 오해한다.
    """
    body = auth_client.get(f"/api/sales/weekly-compare?{PERIOD}").json()
    paired = [row for row in body["data"]
              if row["thisWeek"]["sales"] is not None and row["lastWeek"]["sales"] is not None]
    assert body["total"]["pairedDays"] == len(paired)
    assert body["total"]["thisWeekSales"] == sum(r["thisWeek"]["sales"] for r in paired)
    assert body["total"]["lastWeekSales"] == sum(r["lastWeek"]["sales"] for r in paired)


def test_weekly_compare_falls_back_to_the_last_day_with_sales(auth_client):
    """
    수집이 며칠 밀려도 표가 통째로 비지 않아야 한다 —
    기간 안에서 매출이 있는 마지막 날이 속한 주를 기준으로 잡는다 (FN-235).
    """
    body = auth_client.get("/api/sales/weekly-compare?from=2026-08-10&to=2026-09-30").json()
    assert body["total"]["pairedDays"] > 0


# ── 메뉴 표시명 (FN-251 / FR-DASH-14) ──────────────────────

def test_menu_ranking_applies_display_aliases(auth_client):
    """
    POS 원본 이름 `초등학생(70g)` 이 화면까지 새어 나가면 안 된다.
    DB는 그대로 두고 표시 단계에서만 갈아 끼운다.
    """
    from server.service.menu_alias import ALIASES

    body = auth_client.get(f"/api/menu/ranking?{PERIOD}&limit=100").json()
    by_code = {row["menuCode"]: row["menuName"] for row in body["data"]}
    matched = {code: name for code, name in ALIASES.items() if code in by_code}
    if not matched:
        pytest.skip("이 기간에 별칭 대상 메뉴가 팔리지 않았습니다")
    for code, alias in matched.items():
        assert by_code[code] == alias


# ── 시스템 ─────────────────────────────────────────────────

def test_status_reports_data_range(auth_client):
    body = auth_client.get("/api/system/status").json()
    assert body["status"] in ("ok", "delayed", "failed")
    assert body["dataRange"]["from"] <= body["dataRange"]["to"]


def test_collect_status_describes_the_button(auth_client):
    """FN-205 — 화면은 이 세 값만 보고 버튼을 그린다."""
    body = auth_client.get("/api/system/collect/status").json()
    assert body["backend"] in ("local", "github", "none")
    assert isinstance(body["available"], bool)
    assert isinstance(body["running"], bool)
    assert body["retryAfterSec"] >= 0


def test_collect_endpoints_require_login(client):
    """
    NFR-SEC-04 — 인증 없이 POS 수집을 유발할 수 있으면 안 된다.

    ⚠ 인증된 POST 는 여기서 시험하지 않는다. 실제로 POS에 요청이 나가기 때문이다
      (CLAUDE.md 「POS 서버 배려」). 차단 장치 검증은 tests/test_collect_trigger.py 가
      수집 본체를 대역으로 바꿔 놓고 한다.
    """
    assert client.get("/api/system/collect/status").status_code == 401
    assert client.post("/api/system/collect").status_code == 401


# ── 정적 프론트엔드 ────────────────────────────────────────

def test_login_page_is_served(client):
    assert "소담촌" in client.get("/").text


def test_dashboard_page_is_served(client):
    assert "대시보드" in client.get("/dashboard").text


def test_frontend_never_contains_pos_credentials(client, settings):
    """TC-18 — 번들에 POS 계정이 없어야 한다."""
    for path in ("/", "/dashboard", "/js/api.js", "/js/dashboard.js", "/js/login.js",
                 "/js/refresh.js", "/js/widgets/weeklycompare.js"):
        body = client.get(path).text
        assert settings.pos_user_pw not in body
        assert "topint.co.kr" not in body      # 프론트는 POS를 알지도 못한다
