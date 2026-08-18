"""
POS 로그인 자동화 (STEP 2) — 세션 확보만 책임진다.

실측으로 밝혀진 구조 (docs/03_POS_분석결과.md 7장):
    로그인 포털 : https://topint.co.kr/member/login   (utf-8, POST)
    리포트 서버 : https://asp.topint.co.kr/asp_office/...  (euc-kr)
    → 도메인이 다르다. requests.Session이 도메인별 쿠키를 알아서 관리한다.

CLAUDE.md 보안 규칙:
  · 계정은 .env(Settings)에서만 읽는다 — 하드코딩 금지
  · 로그에 비밀번호·쿠키 값을 남기지 않는다 (mask 경유)
  · 200 응답이어도 실패일 수 있으므로 본문으로 판별한다
"""

from __future__ import annotations

import re

import requests

from .config import Settings
from .formats import decode_korean_lossy
from .logutil import log, mask, warn
from .pos_client import USER_AGENT

LOGIN_PAGE_PATH = "/member/login"

# 폼을 그대로 전송하는 게 아니라 AJAX로 보낸다 (실측: 로그인 페이지의 JS)
#   $.ajax({ method:"POST", url:"/act/member/login", dataType:"json",
#            data: $("#form1").serialize() })
#   .done(data => { if (data.result) location.href = data.redirect... })
LOGIN_ACTION_PATH = "/act/member/login"

# 로그인 폼 필드 (실측: mem_id / mem_pwd / mem_seq / rtn_page)
ID_FIELD = "mem_id"
PW_FIELD = "mem_pwd"


class PosLoginError(RuntimeError):
    """로그인 실패 — 계정이 틀렸거나 폼 구조가 바뀐 경우."""


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _hidden_fields(html: str) -> dict[str, str]:
    """폼의 hidden 값(mem_seq, rtn_page, CSRF 토큰 등)을 그대로 되돌려 보낸다."""
    fields: dict[str, str] = {}
    for tag in re.findall(r"<input[^>]*type=['\"]hidden['\"][^>]*>", html, re.I):
        name = re.search(r"name=['\"]([^'\"]+)", tag, re.I)
        value = re.search(r"value=['\"]([^'\"]*)", tag, re.I)
        if name:
            fields[name.group(1)] = value.group(1) if value else ""
    return fields


def login(settings: Settings, session: requests.Session | None = None) -> requests.Session:
    """
    포털 로그인 후 세션을 돌려준다.
    실패하면 PosLoginError를 던진다 — 조용히 빈 세션을 반환하지 않는다.
    """
    if not settings.pos_user_id or not settings.pos_user_pw:
        raise PosLoginError("POS_USER_ID / POS_USER_PW 가 .env에 없습니다.")

    session = session or build_session()
    portal = settings.pos_portal_url
    page_url = portal + LOGIN_PAGE_PATH
    action_url = portal + LOGIN_ACTION_PATH

    page = session.get(page_url, timeout=30)
    payload = _hidden_fields(decode_korean_lossy(page.content))
    payload[ID_FIELD] = settings.pos_user_id
    payload[PW_FIELD] = settings.pos_user_pw

    log(f"  로그인 시도: {mask(settings.pos_user_id, 3)} → {action_url}")
    response = session.post(
        action_url,
        data=payload,
        headers={
            "Referer": page_url,
            "Origin": portal,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=30,
    )

    result = _parse_login_result(response)
    if not result.get("result"):
        raise PosLoginError(
            f"로그인 실패 (HTTP {response.status_code}) — 응답: {result}\n"
            "계정 또는 폼 구조를 확인하세요."
        )

    log(f"  로그인 성공 · HTTP {response.status_code}")
    _log_cookies(session)

    # 브라우저는 로그인 직후 redirectUrl로 이동한다. 그래야 리포트 서버 세션이 붙는다.
    # 서버가 알려주는 값을 우선하고, 없으면 .env의 POS_LANDING_URL로 되돌아간다.
    landing = result.get("redirectUrl") or settings.pos_landing_url
    if landing:
        session.get(landing, timeout=30)
        log(f"  진입 화면: {landing}")
    return session


def _parse_login_result(response: requests.Response) -> dict:
    """JSON 응답을 기대하되, HTML이 돌아오면 그 사실을 결과에 담아 알린다."""
    try:
        return response.json()
    except ValueError:
        snippet = decode_korean_lossy(response.content)[:200].replace("\n", " ")
        return {"result": False, "raw": snippet}


def _log_cookies(session: requests.Session) -> None:
    for cookie in session.cookies:
        log(f"    쿠키 {cookie.domain}{cookie.path} {cookie.name} = {mask(cookie.value)}")


# 쿠키를 하나씩 빼면서 실측한 결과 (2026-08-16). 정상 = 주문 104 / 시간대 9 / 메뉴 28.
#   comID 하나만        → 정상          ← 핵심 쿠키
#   comID 만 제외       → 주문 4 / 메뉴 0   (실패)
#   memID 만 제외       → 메뉴 161         ⚠ 전 체인 데이터가 섞여 나온다
#   ASPSESSIONID 하나만 → 주문 4 / 메뉴 0   (실패)
#
# ⚠ memID 누락이 가장 위험하다. 오류가 아니라 '더 많은' 행이 돌아오기 때문에
#   다른 매장 매출이 대시보드에 섞여도 조용히 지나간다.
#   → 부분집합을 만들지 말고 Cookie 헤더 전체를 그대로 쓴다.
#
# ASPSESSIONID는 asp 호스트 전용(host-only)이라 포털에서 받은 값은
# asp.topint.co.kr 요청에 전송되지도 않는다. 인증에는 불필요하다.
REQUIRED_COOKIES = ("comID", "memID")
IDENTITY_COOKIES = ("comID", "memID", "comNo", "ComName", "custCode", "memSeq", "grade")
IDENTITY_DOMAIN = ".topint.co.kr"
ASP_HOST = "asp.topint.co.kr"


def _cookie_domain(name: str) -> str:
    """브라우저와 동일한 도메인 배치를 재현한다 (data/evidence/f12_cookies.png 대조)."""
    return ASP_HOST if name.startswith("ASPSESSIONID") else IDENTITY_DOMAIN


def cookie_session(settings: Settings) -> requests.Session:
    """
    저장해 둔 쿠키로 세션을 만든다 (자동 로그인이 막혔을 때의 예비 수단).

    `POS_SESSION_COOKIE`에는 브라우저 `Cookie:` 헤더 전체를 넣는다.
    ⚠ ASPSESSIONID 하나만 넣으면 매장이 식별되지 않아 리포트가 비어서 온다.
    """
    cookie = settings.pos_session_cookie.strip()
    if not cookie:
        raise PosLoginError("POS_SESSION_COOKIE가 비어 있습니다.")

    session = build_session()
    names: list[str] = []
    for part in cookie.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, value = (chunk.strip() for chunk in part.split("=", 1))
        session.cookies.set(name, value, domain=_cookie_domain(name))
        names.append(name)
        log(f"  쿠키 적용: {name} ({_cookie_domain(name)}) = {mask(value)}")

    _check_cookie_set(names)
    return session


def _check_cookie_set(names: list[str]) -> None:
    """
    쿠키가 빠졌는지 검사한다.
    누락은 오류가 아니라 '조용히 잘못된 데이터'로 나타나므로 반드시 경고한다.
    """
    blocking = [name for name in REQUIRED_COOKIES if name not in names]
    if blocking:
        raise PosLoginError(
            f"필수 쿠키가 없습니다: {', '.join(blocking)}\n"
            "  comID 가 없으면 리포트가 비고, memID 가 없으면 다른 매장 데이터가 섞입니다.\n"
            "  브라우저 개발자도구 Network 탭의 Cookie 헤더 전체를 넣으세요."
        )

    missing = [name for name in IDENTITY_COOKIES if name not in names]
    if missing:
        warn(
            f"신원 쿠키 일부가 빠졌습니다: {', '.join(missing)}\n"
            "    부분집합은 매장 범위를 넓힐 수 있습니다. Cookie 헤더 전체를 넣으세요."
        )


def create_session(settings: Settings) -> requests.Session:
    """
    세션 확보의 단일 진입점.
    계정이 있으면 자동 로그인, 없으면 수동 쿠키로 넘어간다.
    """
    if settings.pos_user_id and settings.pos_user_pw:
        return login(settings)
    log("  계정이 없어 수동 쿠키로 진행합니다 (.env의 POS_USER_ID/PW 권장)")
    return cookie_session(settings)
