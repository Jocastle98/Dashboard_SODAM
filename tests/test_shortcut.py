"""
바로가기 HTML 테스트 (server/shortcut.py).

이 산출물의 존재 이유는 "파일 하나 전달 + 항상 최신"이다. 그러려면 두 가지가 지켜져야 한다.

  · 파일에 매출 수치가 들어가지 않는다 — 누구에게 전달해도 영업 기밀이 새지 않는다.
  · 주소가 두 문맥(HTML 속성 / JS 문자열)에 들어가므로 각각 맞게 이스케이프된다.
"""

from __future__ import annotations

import re

from server import shortcut

URL = "https://sodam-magok.vercel.app"
STORE = "소담촌 마곡점"


def test_points_at_the_deployed_dashboard():
    page = shortcut.render(URL, STORE)
    assert f'url={URL}' in page          # meta refresh
    assert f'href="{URL}"' in page       # 리디렉트가 막혔을 때 누를 링크
    assert URL in page.split("location.replace(")[1]


def test_contains_no_sales_figures():
    """
    매출이 들어 있지 않다는 것이 이 파일의 핵심 성질이다.
    6자리 이상 숫자는 CSS 색상(#F8F9FA) 말고는 나오면 안 된다.
    """
    page = shortcut.render(URL, STORE)
    without_colors = re.sub(r"#[0-9A-Fa-f]{6}", "", page)
    assert not re.search(r"\d{6,}", without_colors)


def test_needs_no_database_or_web_assets():
    """스냅샷(export.py)과 달리 DB도 web/ 자산도 읽지 않아야 한다."""
    source = (shortcut.__file__ and open(shortcut.__file__, encoding="utf-8").read())
    assert "open_connection" not in source
    assert "read_text" not in source


def test_escapes_a_url_that_would_break_out_of_the_script():
    """
    주소가 실행 가능한 코드로 새어 나가지 않는지 본다.
    `alert(1)` 이라는 글자가 문자열 안에 남는 것은 무해하다 —
    문제는 문자열이나 `<script>` 태그를 **빠져나가는** 것이다.
    """
    hostile = "https://x.test/'+alert(1)+'</script><script>"
    literal = shortcut._js_string(hostile)

    assert literal.count("'") == 4          # 여닫는 2개 + 이스케이프된 안쪽 2개
    assert literal.startswith("'") and literal.endswith("'")
    assert "\\'" in literal                 # 안쪽 따옴표가 이스케이프됐다
    assert "\\x3C" in literal               # < 가 JS 문자열 안에서 무력화됐다

    # 스크립트 태그가 늘어나지 않았다 — 주소가 태그를 닫고 새로 열지 못했다
    hostile_page = shortcut.render(hostile, STORE)
    benign_page = shortcut.render(URL, STORE)
    assert hostile_page.count("<script") == benign_page.count("<script")
    assert hostile_page.count("</script>") == benign_page.count("</script>")


def test_escapes_a_store_name_with_markup():
    page = shortcut.render(URL, "<b>소담촌</b>")
    assert "<b>소담촌</b>" not in page
    assert "&lt;b&gt;" in page
