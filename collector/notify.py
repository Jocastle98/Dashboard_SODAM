"""
수집 실패 알림 (FN-606 / NFR-OPS-03).

웹훅과 이메일 중 `.env`에 설정된 것만 보낸다. 둘 다 비어 있으면 로그만 남긴다.
알림 실패가 수집을 멈추게 해서는 안 된다 — 예외를 밖으로 던지지 않는다.

⚠ 알림 본문에 계정·쿠키를 넣지 않는다 (CLAUDE.md 보안 규칙).
"""

from __future__ import annotations

import json
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from .config import Settings
from .logutil import log, warn

TIMEOUT_SEC = 10


def notify_failure(settings: Settings, title: str, detail: str) -> None:
    body = f"{title}\n\n{detail}\n\n— 소담촌 마곡점 매출 수집기"
    log(f"  알림: {title}")

    if settings.alert_webhook_url:
        _send_webhook(settings.alert_webhook_url, title, body)
    if settings.alert_email_to and settings.smtp_host:
        _send_email(settings, title, body)
    if not settings.alert_webhook_url and not settings.alert_email_to:
        warn("알림 대상이 설정되지 않았습니다 (.env의 ALERT_WEBHOOK_URL / ALERT_EMAIL_TO)")


def _send_webhook(url: str, title: str, body: str) -> None:
    """Slack·Discord·Teams 모두 `text` 필드를 받는다."""
    payload = json.dumps({"text": f"*{title}*\n{body}"}).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
            log(f"  웹훅 발송 완료 (HTTP {response.status})")
    except (urllib.error.URLError, OSError) as error:
        warn(f"웹훅 발송 실패: {type(error).__name__}: {error}")


def _send_email(settings: Settings, title: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = f"[소담촌 마곡점] {title}"
    message["From"] = settings.smtp_user or settings.alert_email_to
    message["To"] = settings.alert_email_to
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=TIMEOUT_SEC) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
        log("  이메일 발송 완료")
    except (smtplib.SMTPException, OSError) as error:
        warn(f"이메일 발송 실패: {type(error).__name__}: {error}")
