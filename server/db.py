"""
DB 연결 — 읽기 전용 조회용.

수집기(`collector/repository.py`)와 같은 SQLite 파일을 본다.
스키마 정의와 쓰기는 수집기 쪽이 담당하고, 여기서는 조회만 한다.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from collector.config import Settings
from collector.repository import database_path


@contextmanager
def open_connection(settings: Settings) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path(settings))
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def rows(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return connection.execute(sql, params).fetchall()


def one(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Row | None:
    return connection.execute(sql, params).fetchone()
