"""시스템 상태 — 수집 지연 판정 (FN-203 / FR-SYS-01)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from ..repository import system as repo

DELAYED_AFTER_HOURS = 36   # FN-203 — 36시간 초과 시 지연
FAILED_AFTER_HOURS = 72    # 72시간 초과 시 실패


def status(connection: sqlite3.Connection, store_id: int) -> dict:
    last = repo.last_collection(connection, store_id)
    span = repo.data_range(connection, store_id)

    collected_at = last["finished_at"] if last else None
    return {
        "lastCollectedAt": collected_at,
        "lastCollectedDate": last["target_to"] if last else None,
        "status": _judge(collected_at),
        "dataRange": {
            "from": span["date_from"] if span else None,
            "to": span["date_to"] if span else None,
        },
    }


def _judge(collected_at: str | None) -> str:
    """`ok` | `delayed` | `failed`. 수집 이력이 없으면 failed."""
    if not collected_at:
        return "failed"
    try:
        moment = datetime.fromisoformat(collected_at)
    except ValueError:
        return "failed"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    elapsed = datetime.now(timezone.utc) - moment
    if elapsed > timedelta(hours=FAILED_AFTER_HOURS):
        return "failed"
    if elapsed > timedelta(hours=DELAYED_AFTER_HOURS):
        return "delayed"
    return "ok"


def collection_history(connection: sqlite3.Connection, store_id: int, limit: int = 30) -> dict:
    """FN-501 — 관리자 화면의 수집 이력."""
    return {
        "data": [
            {
                "reportType": row["report_type"],
                "startedAt": row["started_at"],
                "finishedAt": row["finished_at"],
                "targetFrom": row["target_from"],
                "targetTo": row["target_to"],
                "status": row["status"],
                "recordCount": row["record_count"],
                "errorMessage": row["error_message"],
            }
            for row in repo.recent_logs(connection, store_id, limit)
        ]
    }
