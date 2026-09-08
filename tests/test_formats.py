"""
collector/formats.py 단위 테스트 — POS 접속 없이 CLAUDE.md 「함정 3가지」를 검증한다.

실행: pytest tests/test_formats.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from collector.formats import (  # noqa: E402
    FORMAT_EMPTY,
    FORMAT_HTML,
    FORMAT_XLS_OLE2,
    FORMAT_XLSX_ZIP,
    decode_korean,
    decode_mixed_korean,
    extract_tables,
    largest_table,
    looks_like_login_page,
    sniff_format,
)

HTML_REPORT = """
<html><body>
<table border=1>
  <tr><th>영업일자</th><th>매출액</th><th>결제건수</th></tr>
  <tr><td>2026-08-15</td><td>1,234,000</td><td>121</td></tr>
  <tr><td>2026-08-14</td><td>987,600</td><td>98</td></tr>
</table>
</body></html>
"""

LOGIN_PAGE = """
<html><body>
<form action="login.asp" method="post">
  아이디 <input name="user_id"> 비밀번호 <input type="password" name="passwd">
  <input type="submit" value="로그인">
</form>
</body></html>
"""


# ── 함정 2: .xls 확장자를 믿지 않는다 ──────────────────────

def test_sniff_detects_html_disguised_as_excel():
    """Classic ASP가 HTML <table>을 엑셀 MIME으로 내보내는 경우."""
    assert sniff_format(HTML_REPORT.encode("euc-kr")) == FORMAT_HTML


def test_sniff_detects_real_xls_by_signature():
    assert sniff_format(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64) == FORMAT_XLS_OLE2


def test_sniff_detects_xlsx_by_signature():
    assert sniff_format(b"PK\x03\x04" + b"\x00" * 64) == FORMAT_XLSX_ZIP


def test_sniff_handles_empty_response():
    assert sniff_format(b"") == FORMAT_EMPTY


def test_sniff_ignores_leading_whitespace_and_bom():
    assert sniff_format("﻿\r\n  <html><body>x".encode("utf-8")) == FORMAT_HTML


# ── 함정 1: 인코딩은 euc-kr ────────────────────────────────

def test_decode_korean_reads_euckr_menu_names():
    assert decode_korean("소담 샤브 정식".encode("euc-kr")) == "소담 샤브 정식"


def test_decode_korean_falls_back_to_utf8():
    assert decode_korean("소담 샤브 정식".encode("utf-8")) == "소담 샤브 정식"


def test_decode_korean_raises_instead_of_silently_mangling():
    """errors='replace'로 뭉개면 깨진 메뉴명이 조용히 DB에 들어간다."""
    with pytest.raises(UnicodeDecodeError):
        decode_korean(b"\xff\xfe\xff\xfe\xff\xfe")


# ── 실측으로 드러난 추가 함정: 한 문서에 euc-kr과 UTF-8이 섞임 ──
# 2026-08-16 agentAnal_com_excel01.asp 응답 — charset=euc-kr 선언인데
# "총매출액"/"순매출액"만 UTF-8 바이트로 나왔다.

MIXED_ENCODING_ROW = (
    b"<table><tr><td>" + "할인액".encode("euc-kr") + b"</td>"
    b"<td>" + "총매출액".encode("utf-8") + b"</td>"
    b"<td>" + "카드결제".encode("euc-kr") + b"</td></tr></table>"
)


def test_declared_encoding_cannot_read_mixed_document():
    """전제 확인 — 선언된 euc-kr로도, utf-8로도 전체가 읽히지 않는다."""
    for encoding in ("euc-kr", "utf-8"):
        with pytest.raises(UnicodeDecodeError):
            MIXED_ENCODING_ROW.decode(encoding)


def test_cp949_must_not_be_tried_before_utf8():
    """
    cp949는 euc-kr의 상위집합이라 UTF-8 바이트를 예외 없이 읽어버린다.
    먼저 시도하면 예외도 없이 엉뚱한 한자가 DB에 들어간다 — 시도 순서가 규칙이다.
    """
    mangled = MIXED_ENCODING_ROW.decode("cp949")
    assert "총매출액" not in mangled  # 조용히 깨진다
    assert "총매출액" in decode_korean(MIXED_ENCODING_ROW)


def test_decode_korean_recovers_mixed_encoding_document():
    text = decode_korean(MIXED_ENCODING_ROW)
    assert "할인액" in text
    assert "총매출액" in text
    assert "카드결제" in text


def test_mixed_decoder_keeps_ascii_markup_intact():
    assert decode_mixed_korean(MIXED_ENCODING_ROW).count("<td>") == 3


def test_extract_tables_reads_mixed_encoding_headers():
    rows = extract_tables(decode_korean(MIXED_ENCODING_ROW))[0]
    assert rows[0] == ["할인액", "총매출액", "카드결제"]


# ── 함정 3: 세션 만료 감지 ─────────────────────────────────

def test_login_page_is_detected():
    assert looks_like_login_page(LOGIN_PAGE) is True


def test_report_is_not_mistaken_for_login_page():
    assert looks_like_login_page(HTML_REPORT) is False


# ── 표 추출 ────────────────────────────────────────────────

def test_extract_tables_returns_header_and_rows():
    tables = extract_tables(HTML_REPORT)
    assert len(tables) == 1
    rows = tables[0]
    assert rows[0] == ["영업일자", "매출액", "결제건수"]
    assert len(rows) == 3


def test_largest_table_picks_the_data_table():
    html = "<table><tr><td>머리글</td></tr></table>" + HTML_REPORT
    assert largest_table(extract_tables(html))[0] == ["영업일자", "매출액", "결제건수"]


def test_largest_table_of_nothing_is_none():
    assert largest_table([]) is None
