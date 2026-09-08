"""
설정 로딩 — .env 단일 진입점.

CLAUDE.md 보안 규칙: POS 계정은 .env에만 둔다.
어떤 모듈도 os.environ을 직접 읽지 않고 이 모듈의 Settings를 통해 접근한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "probe"


def _flag(value: str, default: bool = False) -> bool:
    """빈 값이면 `default`. 'true/1/yes/on' 만 참으로 본다."""
    if not value:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _parse_env_file(path: Path) -> dict[str, str]:
    """의존성 없이 .env를 읽는다 (python-dotenv 미설치 환경에서도 동작)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    """실행에 필요한 값 묶음. 비밀값은 repr에서 제외한다."""

    pos_base_url: str = "https://asp.topint.co.kr"
    pos_portal_url: str = "https://topint.co.kr"
    # 로그인 응답의 redirectUrl. 여기를 한 번 방문해야 리포트 서버 세션이 붙는다.
    pos_landing_url: str = ""
    pos_branch: str = ""
    pos_store_branch_name: str = ""
    pos_hq_branch: str = ""
    # 매장이 속한 브랜드 코드 (소담촌 = 00000). 기록·식별용이며 요청에는 쓰지 않는다.
    pos_brandcode: str = ""
    # 리포트 요청에 실어 보낼 brandcode.
    # ⚠ 반드시 빈 값이어야 한다. 00000을 보내면 timeAnal·menuAnal 모두
    #    "해당되는 기간에 정보가 없습니다"를 반환한다 (docs/03 2.2 실측).
    pos_report_brandcode: str = ""
    pos_user_id: str = field(default="", repr=False)
    pos_user_pw: str = field(default="", repr=False)
    # STEP 1 임시 수단. 자동 로그인이 되므로 평소에는 비워 둔다.
    pos_session_cookie: str = field(default="", repr=False)

    # 대시보드 계정 — POS 계정과 분리한다 (FR-AUTH-03/04)
    dashboard_admin_id: str = field(default="", repr=False)
    dashboard_admin_pw: str = field(default="", repr=False)
    session_secret: str = field(default="", repr=False)
    # 세션 쿠키에 Secure 를 붙일지 (NFR-SEC-01). HTTPS 배포에서는 반드시 True.
    # 명시하지 않으면 Vercel 환경(VERCEL 환경변수)에서 자동으로 켜진다 —
    # 깜빡해서 평문으로 쿠키가 오가는 일을 막기 위한 기본값이다.
    session_cookie_secure: bool = False

    database_url: str = "sqlite:///./data/sodam.db"
    store_code: str = "SODAM_MAGOK"
    store_name: str = "소담촌 마곡점"

    # 배포된 대시보드 주소. 바로가기 HTML(server/shortcut.py)이 이곳을 가리킨다.
    dashboard_url: str = ""

    # 수동 수집 버튼 (FN-205 / FR-COL-07)
    # Vercel 함수는 10초에서 끊기고 POS 계정도 올리지 않는다 → 배포판은 Actions를 깨운다.
    dispatch_repo: str = ""                       # "소유자/저장소"
    dispatch_workflow: str = "collect.yml"
    dispatch_ref: str = "main"
    dispatch_token: str = field(default="", repr=False)
    manual_collect_min_interval_sec: int = 600  # 연타·여러 탭으로 POS를 두드리지 않게

    collect_hour: int = 4
    collect_tz: str = "Asia/Seoul"
    request_delay_sec: float = 1.0
    backfill_months: int = 12
    scheduler_enabled: bool = False

    # 실패 알림 (FN-606 / NFR-OPS-03)
    alert_webhook_url: str = field(default="", repr=False)
    alert_email_to: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = field(default="", repr=False)
    smtp_password: str = field(default="", repr=False)

    @classmethod
    def load(cls, path: Path = ENV_PATH) -> "Settings":
        """.env → OS 환경변수 순으로 덮어쓴다 (배포 환경에서는 OS 변수가 우선)."""
        raw = _parse_env_file(path)
        raw.update({k: v for k, v in os.environ.items() if k in raw})

        def get(key: str, default: str = "") -> str:
            return os.environ.get(key, raw.get(key, default)).strip()

        return cls(
            pos_base_url=get("POS_BASE_URL", "https://asp.topint.co.kr").rstrip("/"),
            pos_portal_url=get("POS_PORTAL_URL", "https://topint.co.kr").rstrip("/"),
            pos_landing_url=get("POS_LANDING_URL"),
            pos_branch=get("POS_BRANCH"),
            pos_store_branch_name=get("POS_STORE_BRANCH_NAME"),
            pos_hq_branch=get("POS_HQ_BRANCH"),
            pos_brandcode=get("POS_BRANDCODE"),
            pos_report_brandcode=get("POS_REPORT_BRANDCODE"),
            pos_user_id=get("POS_USER_ID"),
            pos_user_pw=get("POS_USER_PW"),
            pos_session_cookie=get("POS_SESSION_COOKIE"),
            dashboard_admin_id=get("DASHBOARD_ADMIN_ID"),
            dashboard_admin_pw=get("DASHBOARD_ADMIN_PW"),
            session_secret=get("SESSION_SECRET"),
            session_cookie_secure=_flag(
                get("SESSION_COOKIE_SECURE"), default=bool(os.environ.get("VERCEL"))
            ),
            database_url=get("DATABASE_URL", "sqlite:///./data/sodam.db"),
            store_code=get("STORE_CODE", "SODAM_MAGOK"),
            store_name=get("STORE_NAME", "소담촌 마곡점"),
            dashboard_url=get("DASHBOARD_URL"),
            dispatch_repo=get("DISPATCH_REPO"),
            dispatch_workflow=get("DISPATCH_WORKFLOW", "collect.yml"),
            dispatch_ref=get("DISPATCH_REF", "main"),
            dispatch_token=get("DISPATCH_TOKEN"),
            manual_collect_min_interval_sec=int(
                get("MANUAL_COLLECT_MIN_INTERVAL_SEC", "600") or 600),
            collect_hour=int(get("COLLECT_HOUR", "4") or 4),
            collect_tz=get("COLLECT_TZ", "Asia/Seoul"),
            request_delay_sec=float(get("REQUEST_DELAY_SEC", "1.0") or 1.0),
            backfill_months=int(get("BACKFILL_MONTHS", "12") or 12),
            scheduler_enabled=get("SCHEDULER_ENABLED", "false").lower() in ("1", "true", "yes"),
            alert_webhook_url=get("ALERT_WEBHOOK_URL"),
            alert_email_to=get("ALERT_EMAIL_TO"),
            smtp_host=get("SMTP_HOST"),
            smtp_port=int(get("SMTP_PORT", "587") or 587),
            smtp_user=get("SMTP_USER"),
            smtp_password=get("SMTP_PASSWORD"),
        )
