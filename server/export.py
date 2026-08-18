"""
단일 HTML 내보내기 — 파일 하나로 열리는 대시보드 스냅샷.

서버·인터넷 없이 더블클릭으로 열린다. 시연·공모전 제출·백업용이다.
⚠ 만든 시점의 데이터로 고정된다. 자동 갱신은 서버 배포 쪽에서만 된다.

같은 화면 코드(web/)를 그대로 쓴다 — 화면을 두 벌 만들지 않기 위해
API 응답을 파일에 박아 넣고, `api.js` 대신 그 데이터를 읽는 어댑터를 끼운다.

사용:
    python -m server.export                          # 최근 30일
    python -m server.export --days 90
    python -m server.export --from 2026-01-01 --to 2026-08-16
    python -m server.export --out C:/Users/.../대시보드.html
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import ROOT, Settings  # noqa: E402
from collector.logutil import enable_utf8_output, log, section  # noqa: E402
from server.db import open_connection  # noqa: E402
from server.repository import system as system_repo  # noqa: E402
from server.service import menu as menu_service  # noqa: E402
from server.service import sales as sales_service  # noqa: E402
from server.service import system as system_service  # noqa: E402
from server.service.period import Period, parse_period  # noqa: E402

WEB = ROOT / "web"
DIST = ROOT / "dist"


def build_payload(settings: Settings, period: Period) -> dict:
    """화면이 필요로 하는 모든 응답을 한 번에 모은다."""
    with open_connection(settings) as connection:
        store_id = system_repo.store_id_by_code(connection, settings.store_code)
        if store_id is None:
            raise SystemExit("수집된 데이터가 없습니다. 먼저 `python -m collector.main --days 7`")

        store = system_repo.store_info(connection, store_id)
        return {
            "generatedAt": _now_iso(),
            "period": {"from": period.date_from.isoformat(), "to": period.date_to.isoformat()},
            "storeName": store["store_name"] if store else settings.store_name,
            "summary": sales_service.summary(connection, store_id, period),
            "daily": sales_service.daily(connection, store_id, period),
            "weekday": sales_service.weekday(connection, store_id, period),
            "hourly": sales_service.hourly(connection, store_id, period),
            "menu": menu_service.ranking(connection, store_id, period, 10, "sales"),
            "menuByQuantity": menu_service.ranking(connection, store_id, period, 10, "quantity"),
            "status": system_service.status(connection, store_id),
        }


def render(payload: dict) -> str:
    """web/ 자산을 인라인해 자기완결 HTML을 만든다."""
    dashboard = (WEB / "dashboard.html").read_text(encoding="utf-8")
    css = (WEB / "css" / "style.css").read_text(encoding="utf-8")
    chartjs = (WEB / "vendor" / "chart.umd.min.js").read_text(encoding="utf-8")

    modules = {
        "format.js": (WEB / "js" / "format.js").read_text(encoding="utf-8"),
        "charts.js": (WEB / "js" / "charts.js").read_text(encoding="utf-8"),
        "widget.js": (WEB / "js" / "widgets" / "widget.js").read_text(encoding="utf-8"),
        "kpi.js": (WEB / "js" / "widgets" / "kpi.js").read_text(encoding="utf-8"),
        "daily.js": (WEB / "js" / "widgets" / "daily.js").read_text(encoding="utf-8"),
        "weekday.js": (WEB / "js" / "widgets" / "weekday.js").read_text(encoding="utf-8"),
        "hourly.js": (WEB / "js" / "widgets" / "hourly.js").read_text(encoding="utf-8"),
        "menu.js": (WEB / "js" / "widgets" / "menu.js").read_text(encoding="utf-8"),
    }

    body = _extract_body(dashboard)
    body = body.replace('<button class="btn-ghost" id="logout">로그아웃</button>', "")
    body = _replace_filters_with_notice(body)

    return _TEMPLATE.format(
        store=payload["storeName"],
        css=css,
        chartjs=chartjs,
        body=body,
        data=json.dumps(payload, ensure_ascii=False),
        modules=_bundle(modules),
    )


def _extract_body(html: str) -> str:
    start = html.index("<header")
    end = html.index("<script", start)
    return html[start:end]


def _replace_filters_with_notice(body: str) -> str:
    """기간 필터는 서버가 있어야 동작한다. 스냅샷에서는 안내 문구로 바꾼다."""
    start = body.index('<div class="filters">')
    end = body.index("</div>", body.index("</span>", start)) + len("</div>")
    notice = ('<div class="filters"><span class="chip active" id="snapshot-period"></span>'
              '<span class="chip" style="cursor:default">📄 파일 스냅샷 — 자동 갱신되지 않습니다</span>'
              "</div>")
    return body[:start] + notice + body[end:]


def _bundle(modules: dict[str, str]) -> str:
    """
    ES 모듈 import를 걷어내고 한 스코프에 이어 붙인다.
    file:// 로 열면 import가 CORS로 막히기 때문이다.
    """
    parts = []
    for name, source in modules.items():
        stripped = "\n".join(
            line for line in source.splitlines()
            if not line.strip().startswith("import ")
        ).replace("export function", "function").replace("export const", "const")
        parts.append(f"// ── {name} ──\n{stripped}")
    return "\n\n".join(parts)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# 스냅샷 전용 부트스트랩 — api.js 대신 내장 데이터를 읽는다.
_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{store} · 매출 대시보드</title>
<style>{css}</style>
<script>{chartjs}</script>
</head>
<body>
{body}
<script id="snapshot-data" type="application/json">{data}</script>
<script>
(function () {{
  const DATA = JSON.parse(document.getElementById('snapshot-data').textContent);

  // 서버가 없으므로 API 호출을 내장 데이터로 대체한다.
  const api = {{
    summary: async () => DATA.summary,
    daily: async () => DATA.daily,
    weekday: async () => DATA.weekday,
    hourly: async () => DATA.hourly,
    menuRanking: async (_p, _limit, sortBy) =>
      (sortBy === 'quantity' ? DATA.menuByQuantity : DATA.menu),
    status: async () => DATA.status,
  }};
  const redirectOnUnauthorized = () => false;

{modules}

  document.getElementById('store-name').textContent = DATA.storeName;
  document.getElementById('snapshot-period').textContent =
    DATA.period.from + ' ~ ' + DATA.period.to;

  const badge = document.getElementById('status-badge');
  badge.className = 'badge ' + DATA.status.status;
  badge.querySelector('[data-text]').textContent = '생성 ' + stamp(DATA.generatedAt);

  const range = document.getElementById('data-range');
  if (range && DATA.status.dataRange.from) {{
    range.textContent = '보유 데이터 ' + DATA.status.dataRange.from +
                        ' ~ ' + DATA.status.dataRange.to;
  }}

  const period = DATA.period;
  [kpiWidget(), dailyWidget(), weekdayWidget(), hourlyWidget(), menuWidget()]
    .forEach((w) => w.refresh(period));
}})();
</script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="단일 HTML 대시보드 내보내기")
    parser.add_argument("--days", type=int, default=30, help="최근 N일 (기본 30)")
    parser.add_argument("--from", dest="date_from", help="시작일 YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", help="종료일 YYYY-MM-DD")
    parser.add_argument("--out", help="저장 경로 (기본 dist/)")
    return parser.parse_args()


def main() -> int:
    enable_utf8_output()
    args = parse_args()
    settings = Settings.load()

    yesterday = date.today() - timedelta(days=1)
    if args.date_from:
        period = parse_period(args.date_from, args.date_to or yesterday.isoformat())
    else:
        period = parse_period((yesterday - timedelta(days=args.days - 1)).isoformat(),
                              yesterday.isoformat())

    section("단일 HTML 내보내기")
    log(f"  기간: {period.date_from} ~ {period.date_to} ({period.days}일)")

    payload = build_payload(settings, period)
    html = render(payload)

    if args.out:
        path = Path(args.out)
    else:
        DIST.mkdir(parents=True, exist_ok=True)
        path = DIST / f"소담촌마곡점_대시보드_{period.date_to.isoformat()}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")

    log(f"  저장: {path}")
    log(f"  크기: {len(html.encode('utf-8')):,} bytes")
    log("\n  이 파일은 더블클릭하면 바로 열립니다. 인터넷도 서버도 필요 없습니다.")
    log("  ⚠ 만든 시점의 데이터로 고정됩니다 — 자동 갱신은 서버 배포 쪽에서만 됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
