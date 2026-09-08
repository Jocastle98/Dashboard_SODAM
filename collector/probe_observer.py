"""
관측 로직 — 요청 1건을 받아 "무엇이 왔는지"만 기록한다.

STEP 1의 원칙: 파싱 규칙을 확정하지 않는다. 관측하고 원본을 남긴다.
정식 파서(collector/parse.py)는 이 관측 결과가 docs/03에 확정된 뒤 STEP 3에서 작성한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import ROOT, Settings
from .formats import (
    BINARY_EXCEL_FORMATS,
    FORMAT_HTML,
    TEXTUAL_FORMATS,
    decode_korean_lossy,
    extract_tables,
    largest_table,
    looks_like_login_page,
    sniff_format,
)
from .logutil import fail, log, warn
from .pos_client import PosClient, PosSessionError, save_raw


@dataclass
class Observation:
    """요청 1건의 관측 결과. docs/03_POS_분석결과.md에 그대로 옮겨 적을 수 있는 형태."""

    label: str
    date_from: str
    date_to: str
    ok: bool = False
    status_code: int | None = None
    content_type: str = ""
    disposition: str = ""
    byte_size: int = 0
    file_format: str = ""
    elapsed_sec: float = 0.0
    raw_path: str = ""
    columns: list[str] = field(default_factory=list)
    data_rows: int | None = None
    session_expired: bool = False
    server_error: str = ""
    error: str = ""

    @property
    def http_failed(self) -> bool:
        return self.status_code is not None and self.status_code >= 400

    @property
    def state_label(self) -> str:
        if not self.ok:
            return "실패"
        if self.session_expired:
            return "만료"
        if self.http_failed:
            return f"HTTP{self.status_code}"
        return "ok"


class Probe:
    """PosClient를 감싸 관측 절차를 수행한다."""

    def __init__(self, client: PosClient, settings: Settings):
        self.client = client
        self.settings = settings

    def observe(self, date_from: str, date_to: str, label: str) -> Observation:
        log(f"\n▶ {label}  ({date_from} ~ {date_to})")
        observation = Observation(label=label, date_from=date_from, date_to=date_to)

        try:
            response = self.client.fetch_sales_report(date_from, date_to)
        except (PosSessionError, Exception) as error:  # noqa: BLE001 — 관측 중단 방지
            observation.error = f"{type(error).__name__}: {error}"
            fail(observation.error)
            return observation

        observation.ok = True
        observation.status_code = response.status_code
        observation.content_type = response.headers.get("Content-Type", "")
        observation.disposition = response.headers.get("Content-Disposition", "")
        observation.byte_size = len(response.content)
        observation.elapsed_sec = round(response.elapsed_sec, 2)
        observation.file_format = sniff_format(response.content)

        raw_path = save_raw(response.content, label)
        observation.raw_path = str(raw_path.relative_to(ROOT))

        report_headers(observation)
        inspect_content(observation, response.content, raw_path)
        return observation


# ── 서버 오류 감지 ──────────────────────────────────────
# Classic ASP는 500 응답에도 엑셀 MIME 헤더를 그대로 붙여 보낸다.
# 상태코드만 보고 넘기면 오류 페이지를 데이터로 착각한다.
SERVER_ERROR_PATTERNS = (
    re.compile(r"Microsoft OLE DB Provider[^<]*"),
    re.compile(r"개체 이름 '[^']*'[^<]*"),
    re.compile(r"열 이름 '[^']*'[^<]*"),
    re.compile(r"ODBC 드라이버[^<]*"),
)


def find_server_error(text: str) -> str:
    messages = [
        match.group(0).strip()
        for pattern in SERVER_ERROR_PATTERNS
        for match in [pattern.search(text)]
        if match
    ]
    return " / ".join(messages)


# ── 출력 ────────────────────────────────────────────────
def report_headers(obs: Observation) -> None:
    marker = "  ✗" if obs.http_failed else "  "
    log(f"{marker}HTTP {obs.status_code} · {obs.byte_size:,} bytes · {obs.elapsed_sec:.2f}s")
    log(f"  Content-Type: {obs.content_type or '(없음)'}")
    if obs.disposition:
        log(f"  Content-Disposition: {obs.disposition}")
    log(f"  실제 포맷(시그니처 판별): {obs.file_format}")
    log(f"  원본 저장: {obs.raw_path}")


# ── 본문 해석 ───────────────────────────────────────────
# POS에서 직접 받은 응답이든 사용자가 브라우저로 내려받은 파일이든
# 해석 규칙은 하나여야 한다. inspect_file.py도 이 함수를 그대로 쓴다.
def inspect_content(obs: Observation, content: bytes, source_path: Path) -> None:
    if obs.file_format in TEXTUAL_FORMATS:
        text = decode_korean_lossy(content)
        if looks_like_login_page(text):
            obs.session_expired = True
            warn("세션 만료로 보입니다 — 본문이 로그인 페이지입니다. 쿠키를 갱신하세요.")
            return

        server_error = find_server_error(text)
        if server_error:
            obs.server_error = server_error
            warn(f"서버 오류가 본문에 담겨 있습니다: {server_error}")

    if obs.file_format == FORMAT_HTML:
        inspect_html(obs, decode_korean_lossy(content))
    elif obs.file_format in BINARY_EXCEL_FORMATS:
        inspect_excel(obs, source_path)
    else:
        log("  본문 미리보기:")
        log(decode_korean_lossy(content)[:600])


def inspect_html(obs: Observation, html: str) -> None:
    tables = extract_tables(html)
    log(f"  <table> 개수: {len(tables)}")
    for index, rows in enumerate(tables):
        widths = sorted({len(row) for row in rows})
        log(f"   [table {index}] {len(rows)}행, 열 개수 {widths}")
        for row_index, row in enumerate(rows[:4]):
            log(f"      r{row_index}: {row}")
        if len(rows) > 6:
            log(f"      ... ({len(rows) - 6}행 생략)")
            for row_index in range(len(rows) - 2, len(rows)):
                log(f"      r{row_index}: {rows[row_index]}")

    main = largest_table(tables)
    if main:
        obs.columns = main[0]
        obs.data_rows = max(0, len(main) - 1)


def inspect_excel(obs: Observation, source_path: Path) -> None:
    log("  → 진짜 엑셀 바이너리입니다. pandas.read_excel로 열어야 합니다.")
    try:
        import pandas as pd  # type: ignore

        frame = pd.read_excel(source_path)
        obs.columns = [str(column) for column in frame.columns]
        obs.data_rows = len(frame)
        log(f"  컬럼: {obs.columns}")
        log(f"  데이터 행 수: {obs.data_rows}")
        log(frame.head(5).to_string())
    except Exception as error:  # noqa: BLE001 — pandas 미설치/엔진 부재도 관측 결과다
        warn(f"pandas로 열지 못함: {type(error).__name__}: {error} (원본은 그대로 있습니다)")
