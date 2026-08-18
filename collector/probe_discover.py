"""
파라미터 탐색 진입점 — 500 오류의 원인을 화면에서 직접 확인한다.

엑셀 URL을 바로 호출하면 매장이 비어 SQL 오류가 난다.
조회 화면(agentAnal_com.asp)을 먼저 열어 실제 파라미터 이름과 값을 읽는다.

사용:
    python -m collector.probe_discover
    python -m collector.probe_discover /asp_office/sale/agentAnal_com.asp
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import Settings  # noqa: E402
from collector.formats import decode_korean_lossy, sniff_format  # noqa: E402
from collector.logutil import enable_utf8_output, log, section  # noqa: E402
from collector.auth import PosLoginError, create_session
from collector.pos_client import PosClient, save_raw  # noqa: E402
from collector.probe_forms import find_frames, report_forms  # noqa: E402

REPORT_SCREEN = "/asp_office/sale/agentAnal_com.asp"
DEFAULT_PARAMS = {"frameID": "fra_agentAnal_com"}


def fetch_and_report(client: PosClient, path: str, params: dict[str, str], label: str) -> str:
    log(f"\n▶ {path}")
    response = client.fetch_page(path, params)
    html = decode_korean_lossy(response.content)

    log(f"  HTTP {response.status_code} · {len(response.content):,} bytes")
    log(f"  Content-Type: {response.headers.get('Content-Type', '(없음)')}")
    log(f"  포맷: {sniff_format(response.content)}")
    log(f"  원본 저장: {save_raw(response.content, label)}")

    frames = find_frames(html)
    if frames:
        log(f"  하위 프레임: {frames}")

    report_forms(html)
    return html


def main() -> int:
    enable_utf8_output()
    settings = Settings.load()

    try:
        client = PosClient(settings, create_session(settings))
    except PosLoginError as error:
        log(f"\n{error}")
        return 1

    path = sys.argv[1] if len(sys.argv) > 1 else REPORT_SCREEN
    params = DEFAULT_PARAMS if path == REPORT_SCREEN else {}

    section("조회 화면 탐색 — 엑셀 URL의 올바른 파라미터 찾기")
    html = fetch_and_report(client, path, params, "screen_agentAnal_com")

    frames = [frame for frame in find_frames(html) if frame.lower().endswith(".asp")]
    for index, frame in enumerate(frames[:3]):
        frame_path = frame if frame.startswith("/") else f"/asp_office/sale/{frame}"
        section(f"하위 프레임 {index + 1}: {frame_path}")
        fetch_and_report(client, frame_path.split("?")[0], {}, f"screen_frame{index + 1}")

    fetch_branch_list(client)

    log("\n찾은 매장 코드를 .env의 POS_BRANCH에 반영한 뒤 probe_topint를 다시 실행하세요.")
    return 0


BRANCH_LIST_PATH = "/asp_office/sale/agentAnal_com_branch_sch.asp"


def fetch_branch_list(client: PosClient) -> None:
    """
    매장 목록은 화면 로드 후 AJAX로 채워진다.
    `branch` select가 정적 HTML에 비어 있으므로 이 엔드포인트가 유일한 출처다.
    """
    section("매장 목록 조회 — POS_BRANCH에 넣을 실제 값")

    response = client.post_page(BRANCH_LIST_PATH)
    body = decode_korean_lossy(response.content)
    log(f"  HTTP {response.status_code} · {len(response.content):,} bytes")
    log(f"  Content-Type: {response.headers.get('Content-Type', '(없음)')}")
    log(f"  원본 저장: {save_raw(response.content, 'branch_list')}")
    log("\n  응답 본문:")
    log(body[:2000])


if __name__ == "__main__":
    raise SystemExit(main())
