"""
대시보드 계정 생성/갱신.

`.env`의 DASHBOARD_ADMIN_ID / DASHBOARD_ADMIN_PW 를 읽어 bcrypt 해시로 저장한다.
평문 비밀번호는 DB에 들어가지 않는다 (FR-AUTH-04).

사용:
    python -m server.seed
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector import repository as collector_repo  # noqa: E402
from collector.config import Settings  # noqa: E402
from collector.logutil import enable_utf8_output, log, mask, section  # noqa: E402
from server.repository import users as user_repo  # noqa: E402
from server.security import hash_password  # noqa: E402


def main() -> int:
    enable_utf8_output()
    settings = Settings.load()

    section("대시보드 계정 설정")
    if not settings.dashboard_admin_id or not settings.dashboard_admin_pw:
        log("  .env의 DASHBOARD_ADMIN_ID / DASHBOARD_ADMIN_PW 가 비어 있습니다.")
        return 1
    if not settings.session_secret:
        log("  .env의 SESSION_SECRET 이 비어 있습니다.")
        return 1

    with collector_repo.connect(settings) as session:
        collector_repo.apply_schema(session)
        store_id = collector_repo.ensure_store(session, settings)

        password_hash = hash_password(settings.dashboard_admin_pw)
        existing = user_repo.find_by_username(session, settings.dashboard_admin_id)
        if existing:
            user_repo.update_password(session, existing["user_id"], password_hash)
            log(f"  기존 계정 비밀번호 갱신: {mask(settings.dashboard_admin_id, 3)}")
        else:
            user_repo.create(session, store_id, settings.dashboard_admin_id, password_hash)
            log(f"  계정 생성: {mask(settings.dashboard_admin_id, 3)}")

    log("  비밀번호는 bcrypt 해시로 저장했습니다 (평문 미저장).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
