"""
POS HTTP 클라이언트 — POS 접근은 collector/ 안에서만, 그중에서도 이 모듈을 통해서만.

CLAUDE.md 「POS 서버 배려」를 여기 한 곳에서 강제한다.
  · 요청 간 최소 1초 대기 (초기 12개월 적재 시에도 예외 없음)
  · 재시도 3회, 5s/15s/45s 지수 백오프
  · User-Agent 명시 + Referer 동봉
  · 병렬 요청 금지 — 이 클라이언트는 순차 호출만 제공한다

STEP 2에서 auth.py가 build_session()을 로그인 기반으로 교체한다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import RAW_DIR, Settings
from .logutil import fail, log, mask, warn

SALE_DIR = "/asp_office/sale"

# 실측으로 확정한 리포트 3종 (docs/03_POS_분석결과.md 2장)
ORDERS_PATH = f"{SALE_DIR}/agentAnal_com_excel01.asp"      # 주문 단위 상세
HOURLY_PATH = f"{SALE_DIR}/timeAnal_excel.asp"             # 시간대별
MENU_PATH = f"{SALE_DIR}/menuAnal_sub_1_excel.asp"         # 메뉴별
CANCEL_PATH = f"{SALE_DIR}/agentAnal_com_excel03.asp"      # 주문 취소내역

REPORT_PATH = ORDERS_PATH  # 하위 호환
REFERER = "https://asp.topint.co.kr/asp_office/sale/agentAnal_com.asp?frameID=fra_agentAnal_com"
USER_AGENT = "SodamDashboard-Collector/0.1 (authorized store-owner data collection)"

COOKIE_DOMAIN = "asp.topint.co.kr"
RETRY_BACKOFF_SEC = (5, 15, 45)  # FN-603
TIMEOUT_SEC = 30


class PosSessionError(RuntimeError):
    """세션 쿠키가 없거나 만료된 상태."""


@dataclass
class PosResponse:
    """요청 1건의 원시 결과. 해석은 formats/parse가 맡는다."""

    status_code: int
    content: bytes
    headers: dict[str, str]
    elapsed_sec: float
    url: str


class PosClient:
    def __init__(self, settings: Settings, session: requests.Session):
        """
        세션은 반드시 주입받는다 — `auth.create_session()`이 단일 출처다.
        이 클래스는 '어떻게 로그인하는가'를 알지 않는다.
        """
        self.settings = settings
        self.session = session
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Referer", REFERER)

    # ── 리포트 3종 ──────────────────────────────────────
    # date_* 는 YYYYMMDD 문자열.
    # 재시도와 1초 대기가 내장되어 있으므로 호출부에서 sleep을 넣지 않는다.

    def fetch_orders(self, date_from: str, date_to: str) -> PosResponse:
        """매장별 매출세부분석 — 주문(영수증) 단위 19컬럼."""
        return self._get(self.settings.pos_base_url + ORDERS_PATH, {
            "opendate_s": date_from,
            "opendate_e": date_to,
            "branch": self.settings.pos_branch,
            "branchAddChk": "",
        })

    def fetch_hourly(self, date_from: str, date_to: str) -> PosResponse:
        """
        시간대별 매출현황 — 6컬럼.
        ⚠ brandcode를 채우면 빈 결과가 온다. branch를 비우면 전 체인 합계가 온다.
        """
        return self._get(self.settings.pos_base_url + HOURLY_PATH, {
            "opendate_s": date_from,
            "opendate_e": date_to,
            "brandcode": self.settings.pos_report_brandcode,
            "branch": self.settings.pos_branch,
        })

    def fetch_menu(self, date_from: str, date_to: str) -> PosResponse:
        """메뉴별 매출현황 — 7컬럼 (분류명/메뉴명/메뉴코드/총매출액/판매수량)."""
        return self._get(self.settings.pos_base_url + MENU_PATH, {
            "opendate_s": date_from,
            "opendate_e": date_to,
            "brandcode": self.settings.pos_report_brandcode,
            "branch": self.settings.pos_branch,
            "bcode": "",
            "gcode": "",
        })

    def fetch_cancels(self, date_from: str, date_to: str) -> PosResponse:
        """주문 취소내역 — DQ-01(취소 건 분류)용."""
        return self._get(self.settings.pos_base_url + CANCEL_PATH, {
            "opendate_s": date_from,
            "opendate_e": date_to,
            "branch": self.settings.pos_branch,
            "branchAddChk": "",
        })

    def fetch_sales_report(self, date_from: str, date_to: str) -> PosResponse:
        """probe_observer 호환용 별칭."""
        return self.fetch_orders(date_from, date_to)

    def fetch_page(self, path: str, params: dict[str, str] | None = None) -> PosResponse:
        """
        리포트 화면 등 임의의 POS 페이지 조회 (STEP 1 탐색용).

        Classic ASP는 조회 조건을 Session에 담아두는 경우가 많다.
        엑셀 URL을 바로 때렸을 때 값이 비는 현상의 원인일 수 있으므로,
        상위 화면을 먼저 열어보는 경로가 필요하다.
        """
        return self._request("GET", self.settings.pos_base_url + path, params=params or {})

    def post_page(self, path: str, data: dict[str, str] | None = None) -> PosResponse:
        """
        jqGrid/AJAX 엔드포인트 조회 (STEP 1 탐색용).
        화면이 POST + JSON으로 데이터를 받아오는 경로가 따로 있다.
        """
        return self._request(
            "POST",
            self.settings.pos_base_url + path,
            data=data or {},
            extra_headers={"X-Requested-With": "XMLHttpRequest"},
        )

    def _get(self, url: str, params: dict[str, str]) -> PosResponse:
        return self._request("GET", url, params=params)

    def _request(
        self,
        method: str,
        url: str,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> PosResponse:
        last_error: Exception | None = None

        for attempt in range(len(RETRY_BACKOFF_SEC) + 1):
            if attempt:
                wait = RETRY_BACKOFF_SEC[attempt - 1]
                warn(f"재시도 {attempt}/{len(RETRY_BACKOFF_SEC)} — {wait}초 후")
                time.sleep(wait)
            try:
                started = time.time()
                response = self.session.request(
                    method, url, params=params, data=data,
                    headers=extra_headers, timeout=TIMEOUT_SEC,
                )
                elapsed = time.time() - started
                self._be_polite()
                return PosResponse(
                    status_code=response.status_code,
                    content=response.content,
                    headers=dict(response.headers),
                    elapsed_sec=elapsed,
                    url=response.url,
                )
            except requests.RequestException as error:
                last_error = error
                fail(f"요청 실패: {type(error).__name__}: {error}")

        raise PosSessionError(f"3회 재시도 후에도 실패했습니다: {last_error}")

    def _be_polite(self) -> None:
        """남의 운영 서버다. 성공·실패와 무관하게 매 요청 뒤 대기한다."""
        time.sleep(self.settings.request_delay_sec)


def save_raw(content: bytes, label: str, directory: Path = RAW_DIR) -> Path:
    """FN-607 원본 보존. data/ 는 gitignore 대상이라 커밋되지 않는다."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{label}.bin"
    path.write_bytes(content)
    return path
