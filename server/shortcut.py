"""
바로가기 HTML 내보내기 — 파일 하나로 **항상 최신** 대시보드를 여는 창구.

`server/export.py`(스냅샷)와 목적이 정반대다. 그래서 별도 모듈로 둔다:

    export.py    수집 결과를 파일에 박아 넣는다. 오프라인에서 열리지만 시점이 고정된다.
    shortcut.py  배포된 대시보드로 보내기만 한다. 인터넷이 필요하지만 항상 최신이다.

**왜 파일이 스스로 갱신될 수 없는가.** 브라우저는 POS(topint.co.kr)에 직접 요청할 수
없다 — CORS로 막히고, 뚫는다 해도 POS 계정이 파일 안에 노출된다. 갱신하는 주체는
반드시 서버(수집기)여야 하므로, "파일 하나"와 "항상 최신"을 동시에 만족시키는 길은
파일이 그 서버를 가리키는 것뿐이다.

이 파일에는 **매출 수치가 한 글자도 들어가지 않는다.** 주소만 들어 있어
누구에게 전달해도, 저장소에 커밋해도 영업 기밀이 새지 않는다.

사용:
    python -m server.shortcut                              # DASHBOARD_URL 사용
    python -m server.shortcut --url https://sodam.vercel.app
    python -m server.shortcut --out "C:/Users/.../바탕화면/소담촌 매출.html"
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import ROOT, Settings  # noqa: E402
from collector.logutil import enable_utf8_output, log, section  # noqa: E402

DIST = ROOT / "dist"

# 리디렉트가 막혔을 때도 사장님이 길을 잃지 않도록 눌 수 있는 링크를 함께 둔다.
# 외부 자원을 하나도 쓰지 않는다 — 매장 네트워크가 CDN을 막아도 열려야 한다.
_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta http-equiv="refresh" content="0; url={url}">
<style>
  body {{ margin: 0; min-height: 100vh; display: flex; align-items: center;
         justify-content: center; background: #F8F9FA; color: #212529;
         font-family: -apple-system, "Segoe UI", "Malgun Gothic", sans-serif; }}
  .box {{ text-align: center; padding: 32px 24px; }}
  .emoji {{ font-size: 44px; }}
  h1 {{ font-size: 19px; margin: 12px 0 6px; }}
  p {{ font-size: 13px; color: #868E96; margin: 0 0 22px; }}
  a {{ display: inline-block; padding: 11px 22px; font-size: 14px; font-weight: 600;
       color: #fff; background: #C8102E; border-radius: 8px; text-decoration: none; }}
  .note {{ font-size: 11px; color: #ADB5BD; margin-top: 26px; line-height: 1.7; }}
</style>
</head>
<body>
<div class="box">
  <div class="emoji">🍲</div>
  <h1>{store} 매출 대시보드</h1>
  <p>대시보드로 이동하고 있습니다…</p>
  <a href="{url}">열리지 않으면 여기를 누르세요</a>
  <div class="note">
    이 파일은 바로가기입니다. 매출 데이터는 들어 있지 않습니다.<br>
    화면은 매일 새벽 자동으로 갱신되며, 대시보드의 <b>지금 수집</b> 버튼으로
    즉시 받아올 수도 있습니다.<br>
    인터넷 연결이 필요합니다.
  </div>
</div>
<script>location.replace({url_js});</script>
</body>
</html>
"""


def render(url: str, store_name: str) -> str:
    """주소는 HTML과 JS 두 문맥에 들어간다 — 각각 맞게 이스케이프한다."""
    safe_url = html.escape(url, quote=True)
    return _TEMPLATE.format(
        title=html.escape(f"{store_name} 매출 대시보드"),
        store=html.escape(store_name),
        url=safe_url,
        url_js=_js_string(url),
    )


def _js_string(value: str) -> str:
    """`</script>` 나 따옴표가 섞여도 스크립트가 깨지지 않게 만든다."""
    escaped = (value.replace("\\", "\\\\").replace("'", "\\'")
                    .replace("<", "\\x3C").replace(">", "\\x3E"))
    return f"'{escaped}'"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="바로가기 HTML 내보내기")
    parser.add_argument("--url", help="배포된 대시보드 주소 (기본: .env 의 DASHBOARD_URL)")
    parser.add_argument("--out", help="저장 경로 (기본 dist/)")
    return parser.parse_args()


def main() -> int:
    enable_utf8_output()
    args = parse_args()
    settings = Settings.load()

    url = (args.url or settings.dashboard_url).strip().rstrip("/")
    if not url:
        log("배포 주소를 모릅니다. `.env` 의 DASHBOARD_URL 을 채우거나 --url 로 넘기세요.")
        return 2
    if not url.startswith(("http://", "https://")):
        log(f"주소가 http(s):// 로 시작해야 합니다: {url}")
        return 2

    section("바로가기 HTML 내보내기")
    log(f"  대상: {url}")

    if args.out:
        path = Path(args.out)
    else:
        DIST.mkdir(parents=True, exist_ok=True)
        path = DIST / f"{settings.store_name.replace(' ', '')}_대시보드_바로가기.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(url, settings.store_name), encoding="utf-8")

    log(f"  저장: {path}")
    log("\n  이 파일을 사장님께 전달하면 더블클릭으로 대시보드가 열립니다.")
    log("  화면은 항상 최신입니다 — 파일에는 매출 수치가 들어 있지 않습니다.")
    log("  ⚠ 인터넷 연결이 필요합니다. 오프라인용은 `python -m server.export`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
