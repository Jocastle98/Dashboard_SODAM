"""
HTML 폼 구조 분석 — 실제 파라미터 이름과 허용 값을 알아낸다.

2026-08-16 실측에서 `branch=sodam001`로 요청했더니 SQL 오류가 났다:
    개체 이름 '_2026..p_store_order'이(가) 잘못되었습니다
DB 이름 접두사가 비어 있다는 뜻이므로, `sodam001`은 매장 코드가 아니거나
파라미터 이름이 다르다. 추측하지 말고 조회 화면의 폼에서 직접 읽어낸다.

HTTP는 다루지 않는다 — HTML 문자열만 받는다 (pos_client와 책임 분리).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .logutil import log, section


@dataclass
class Field:
    tag: str          # input | select | textarea
    name: str
    field_type: str = ""
    value: str = ""
    options: list[tuple[str, str]] = field(default_factory=list)  # (value, 표시문자열)


@dataclass
class Form:
    action: str
    method: str
    fields: list[Field] = field(default_factory=list)


def extract_forms(html: str) -> list[Form]:
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        return _extract_forms_regex(html)

    soup = BeautifulSoup(html, "html.parser")
    forms: list[Form] = []
    for form_tag in soup.find_all("form"):
        form = Form(
            action=form_tag.get("action", ""),
            method=(form_tag.get("method") or "get").lower(),
        )
        for tag in form_tag.find_all(["input", "select", "textarea"]):
            name = tag.get("name") or tag.get("id") or ""
            if not name:
                continue
            entry = Field(tag=tag.name, name=name, value=tag.get("value", ""))
            if tag.name == "input":
                entry.field_type = tag.get("type", "text")
            elif tag.name == "select":
                entry.options = [
                    (option.get("value", ""), option.get_text(strip=True))
                    for option in tag.find_all("option")
                ]
            form.fields.append(entry)
        forms.append(form)
    return forms


def _extract_forms_regex(html: str) -> list[Form]:
    forms: list[Form] = []
    for match in re.finditer(r"<form([^>]*)>(.*?)</form>", html, re.S | re.I):
        attributes, body = match.group(1), match.group(2)
        form = Form(
            action=_attribute(attributes, "action"),
            method=(_attribute(attributes, "method") or "get").lower(),
        )
        for tag_match in re.finditer(r"<(input|select|textarea)([^>]*)>", body, re.I):
            tag, attributes = tag_match.group(1).lower(), tag_match.group(2)
            name = _attribute(attributes, "name") or _attribute(attributes, "id")
            if name:
                form.fields.append(
                    Field(tag=tag, name=name,
                          field_type=_attribute(attributes, "type"),
                          value=_attribute(attributes, "value"))
                )
        forms.append(form)
    return forms


def _attribute(attributes: str, name: str) -> str:
    match = re.search(rf'{name}\s*=\s*["\']?([^"\'\s>]*)', attributes, re.I)
    return match.group(1) if match else ""


# ── 폼 밖에 있는 단서 ──────────────────────────────────────
# Classic ASP 화면은 조회 조건을 JS 변수나 하드코딩된 URL에 담아두기도 한다.

BRANCH_PATTERN = re.compile(r'branch\w*\s*[=:]\s*["\']?([\w-]+)', re.I)
EXCEL_LINK_PATTERN = re.compile(r'([\w/]+_excel\d*\.asp\?[^"\'\s<>]*)', re.I)


def find_branch_hints(html: str) -> list[str]:
    """`branch` 로 시작하는 변수/파라미터에 실제로 어떤 값이 들어가는지 수집."""
    return sorted({value for value in BRANCH_PATTERN.findall(html) if value})


def find_excel_links(html: str) -> list[str]:
    """화면이 실제로 호출하는 엑셀 URL — 파라미터 조합의 정답지."""
    return sorted(set(EXCEL_LINK_PATTERN.findall(html)))


# ── 보고 ───────────────────────────────────────────────────

def report_forms(html: str) -> None:
    section("조회 화면의 폼 구조 — 실제 파라미터 이름과 허용 값")

    forms = extract_forms(html)
    if not forms:
        log("  <form>을 찾지 못했습니다. 프레임으로 분리된 화면일 수 있습니다.")
    for index, form in enumerate(forms):
        log(f"\n  [form {index}] {form.method.upper()} {form.action or '(action 없음)'}")
        for entry in form.fields:
            label = f"{entry.tag}:{entry.name}"
            if entry.field_type:
                label += f" ({entry.field_type})"
            log(f"    {label} = {entry.value!r}")
            for value, text in entry.options[:20]:
                log(f"        └ option {value!r} → {text}")
            if len(entry.options) > 20:
                log(f"        └ ... {len(entry.options) - 20}개 더")

    hints = find_branch_hints(html)
    log(f"\n  branch 관련 값 후보: {hints or '없음'}")

    links = find_excel_links(html)
    if links:
        log("\n  화면이 호출하는 엑셀 URL:")
        for link in links:
            log(f"    {link}")


def find_frames(html: str) -> list[str]:
    """프레임 기반 화면이면 실제 내용은 하위 프레임에 있다."""
    return sorted(set(re.findall(r'<i?frame[^>]+src\s*=\s*["\']([^"\']+)', html, re.I)))
