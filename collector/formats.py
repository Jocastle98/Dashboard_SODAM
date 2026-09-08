"""
응답 포맷 판별 · 디코딩 · 표 추출.

CLAUDE.md 「함정 3가지」가 전부 이 모듈에 모여 있다.
STEP 3의 parse.py도 이 모듈을 재사용한다 — 판별 규칙을 두 곳에 두지 않는다.
"""

from __future__ import annotations

import re

# ── 파일 시그니처 ──────────────────────────────────────────
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # Excel 97-2003
_ZIP_MAGIC = b"PK\x03\x04"  # Excel 2007+ (xlsx)

FORMAT_XLS_OLE2 = "xls_ole2"
FORMAT_XLSX_ZIP = "xlsx_zip"
FORMAT_HTML = "html"
FORMAT_XML_SS = "xml_ss"
FORMAT_TEXT = "text"
FORMAT_EMPTY = "empty"
FORMAT_UNKNOWN = "unknown"

TEXTUAL_FORMATS = (FORMAT_HTML, FORMAT_TEXT, FORMAT_XML_SS, FORMAT_UNKNOWN)
BINARY_EXCEL_FORMATS = (FORMAT_XLS_OLE2, FORMAT_XLSX_ZIP)


def sniff_format(content: bytes) -> str:
    """
    함정 2번 — 확장자(.xls)를 믿지 않고 파일 시그니처로 실제 포맷을 판별한다.
    Classic ASP는 HTML <table>을 엑셀 MIME으로 내보내는 경우가 많다.

    반환값:
        xls_ole2 / xlsx_zip  진짜 엑셀 바이너리 → pandas.read_excel
        html                 HTML 표 위장       → extract_tables
        xml_ss               Excel 2003 XML SpreadsheetML
        text                 구분자 텍스트 추정
        empty / unknown      원본을 직접 열어볼 것
    """
    if not content:
        return FORMAT_EMPTY

    head = content[:2048]
    if head.startswith(_OLE2_MAGIC):
        return FORMAT_XLS_OLE2
    if head.startswith(_ZIP_MAGIC):
        return FORMAT_XLSX_ZIP

    probe = head.lstrip(b"\xef\xbb\xbf").lstrip()
    lowered = probe[:512].lower()

    if b"<?xml" in lowered and b"spreadsheet" in head[:4096].lower():
        return FORMAT_XML_SS
    if lowered.startswith(b"<") or b"<table" in head.lower() or b"<html" in lowered:
        return FORMAT_HTML
    if b"\t" in head or b"," in head:
        return FORMAT_TEXT
    return FORMAT_UNKNOWN


# 시도 순서가 중요하다. cp949는 euc-kr의 상위집합이라
# UTF-8 바이트를 예외 없이 "읽어버리고" 엉뚱한 한자를 만들어낸다.
# 따라서 반드시 euc-kr → utf-8 → cp949 순으로 좁은 것부터 시도한다.
RUN_ENCODINGS = ("euc-kr", "utf-8", "cp949")


def decode_korean(content: bytes) -> str:
    """
    함정 1번 — 인코딩은 euc-kr. UTF-8로 디코딩하면 메뉴명이 전부 깨진다.
    errors='replace'로 뭉개지 않고 euc-kr → cp949 → utf-8 순으로 정확히 시도한다.

    ⚠ 2026-08-16 실측에서 밝혀진 추가 함정:
      agentAnal_com_excel01.asp 응답은 charset=euc-kr을 선언하면서도
      일부 컬럼명("총매출액", "순매출액")만 UTF-8 바이트로 섞여 나온다.
      전체를 한 인코딩으로 읽으면 반드시 실패하거나 조용히 깨진다.
      → 단일 인코딩이 통하지 않으면 바이트 런 단위로 내려간다.
    """
    try:
        return content.decode("euc-kr")  # 대부분의 응답은 여기서 끝난다
    except UnicodeDecodeError:
        return decode_mixed_korean(content)


def decode_mixed_korean(content: bytes, errors: str = "strict") -> str:
    """
    인코딩이 섞인 문서를 바이트 런 단위로 디코딩한다.

    ASCII 구간(<0x80)은 어느 인코딩에서든 동일하므로 경계로 삼을 수 있다.
    비ASCII 런은 통째로 euc-kr → utf-8 → cp949 순으로 시도한다.
    한 셀 안의 한글은 하나의 인코딩으로 통일되어 있으므로 런 단위면 충분하다.
    """
    parts: list[str] = []
    index, length = 0, len(content)

    while index < length:
        if content[index] < 0x80:
            end = index
            while end < length and content[end] < 0x80:
                end += 1
            parts.append(content[index:end].decode("ascii"))
        else:
            end = index
            while end < length and content[end] >= 0x80:
                end += 1
            parts.append(_decode_run(content[index:end], errors))
        index = end

    return "".join(parts)


def _decode_run(run: bytes, errors: str) -> str:
    for encoding in RUN_ENCODINGS:
        try:
            return run.decode(encoding)
        except UnicodeDecodeError:
            continue
    if errors == "strict":
        raise UnicodeDecodeError(
            "euc-kr", run, 0, min(len(run), 1),
            "euc-kr/utf-8/cp949 모두 실패 — 인코딩 가정이 틀렸거나 바이너리입니다",
        )
    return run.decode("euc-kr", errors="replace")


def decode_korean_lossy(content: bytes) -> str:
    """미리보기 전용. 파싱 경로에서는 decode_korean()을 쓴다."""
    try:
        return decode_korean(content)
    except UnicodeDecodeError:
        return decode_mixed_korean(content, errors="replace")


def looks_like_login_page(text: str) -> bool:
    """
    함정 3번 — 세션 만료 시 200 응답에 로그인 HTML이 담겨온다.
    상태코드만 보면 조용히 실패하므로 본문을 검사한다.
    """
    markers = ("login", "로그인", "userid", "user_id", "passwd", "password", "아이디")
    head = text[:4000].lower()
    hits = sum(1 for marker in markers if marker in head)
    has_form = "<form" in head or "<input" in head
    return hits >= 2 and has_form


# ── 표 추출 ────────────────────────────────────────────────

Table = list[list[str]]


def extract_tables(html: str) -> list[Table]:
    """<table>들을 셀 문자열 2차원 배열로 추출. bs4가 있으면 사용, 없으면 정규식 폴백."""
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        return _extract_tables_regex(html)

    soup = BeautifulSoup(html, "html.parser")
    tables: list[Table] = []
    for table in soup.find_all("table"):
        rows: Table = []
        for tr in table.find_all("tr"):
            cells = [cell.get_text(strip=True) for cell in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def _extract_tables_regex(html: str) -> list[Table]:
    tables: list[Table] = []
    for table_html in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S | re.I):
        rows: Table = []
        for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S | re.I):
            cells = [
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell))
                .replace("&nbsp;", " ")
                .strip()
                for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S | re.I)
            ]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def largest_table(tables: list[Table]) -> Table | None:
    """데이터 표는 보통 행이 가장 많다 (머리글·레이아웃 표를 걸러내기 위한 관측용 휴리스틱)."""
    return max(tables, key=len) if tables else None
