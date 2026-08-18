"""
내려받은 파일 분석기 — 쿠키 없이 STEP 1을 진행하는 경로.

세션 쿠키를 복사하기 어렵거나 자동 접근을 아직 쓸 수 없을 때,
사장님/사용자가 POS 화면에서 **직접 내려받은 파일**을 그대로 분석한다.

관측 규칙은 probe_observer와 완전히 동일하다 (같은 함수를 호출한다).
따라서 여기서 나온 결론을 그대로 docs/03_POS_분석결과.md에 적어도 된다.

사용:
    python -m collector.inspect_file                      # data/probe/ 안의 파일 전부
    python -m collector.inspect_file "C:/Users/.../매출.xls"
    python -m collector.inspect_file 파일1.xls 파일2.xls
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # python collector/inspect_file.py 로도 실행 가능하게
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config import RAW_DIR, ROOT  # noqa: E402
from collector.formats import sniff_format  # noqa: E402
from collector.logutil import enable_utf8_output, fail, log, section  # noqa: E402
from collector.probe_observer import Observation, inspect_content  # noqa: E402
from collector.probe_report import report_columns, report_menu_and_hour, report_summary  # noqa: E402

# POS가 내려주는 파일은 확장자를 믿을 수 없으므로 넓게 받는다.
SCAN_SUFFIXES = (".xls", ".xlsx", ".html", ".htm", ".csv", ".bin", ".txt")


def collect_targets(arguments: list[str]) -> list[Path]:
    """인자가 없으면 data/probe/ 를 훑는다."""
    if not arguments:
        if not RAW_DIR.exists():
            return []
        return sorted(
            path for path in RAW_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in SCAN_SUFFIXES
        )

    targets: list[Path] = []
    for argument in arguments:
        path = Path(argument).expanduser()
        if path.is_dir():
            targets.extend(
                sorted(p for p in path.iterdir()
                       if p.is_file() and p.suffix.lower() in SCAN_SUFFIXES)
            )
        else:
            targets.append(path)
    return targets


def inspect(path: Path) -> Observation:
    """파일 1개를 관측한다. 날짜 정보는 파일명에서 유추하지 않고 비워 둔다(추측 금지)."""
    log(f"\n▶ {path.name}")

    observation = Observation(label=path.stem, date_from="?", date_to="?")
    if not path.exists():
        observation.error = "파일을 찾을 수 없습니다"
        fail(f"{observation.error}: {path}")
        return observation

    content = path.read_bytes()
    observation.ok = True
    observation.byte_size = len(content)
    observation.file_format = sniff_format(content)
    try:
        observation.raw_path = str(path.relative_to(ROOT))
    except ValueError:  # 저장소 밖의 경로
        observation.raw_path = str(path)

    log(f"  크기: {observation.byte_size:,} bytes")
    log(f"  확장자: {path.suffix or '(없음)'}")
    log(f"  실제 포맷(시그니처 판별): {observation.file_format}")
    if path.suffix.lower() in (".xls", ".xlsx") and observation.file_format == "html":
        log("  ⚠ 확장자는 엑셀인데 내용은 HTML입니다 — CLAUDE.md 함정 2번 그대로입니다.")

    inspect_content(observation, content, path)
    return observation


def print_usage_hint() -> None:
    section("분석할 파일이 없습니다")
    log("  POS 화면에서 매출 리포트를 내려받아 아래 폴더에 넣고 다시 실행하세요:")
    log(f"    {RAW_DIR}")
    log()
    log("  또는 경로를 직접 지정:")
    log('    python -m collector.inspect_file "C:/Users/82103/Downloads/매출.xls"')
    log()
    log("  기간 조회 동작(확인 항목 2)을 보려면 POS 화면에서 기간을 다르게 잡아")
    log("  최소 2개 파일을 받아주세요 — 하루치 1개, 7일치 1개.")


def main() -> int:
    enable_utf8_output()
    targets = collect_targets(sys.argv[1:])

    if not targets:
        print_usage_hint()
        return 1

    section(f"내려받은 파일 분석 — {len(targets)}개")
    observations = [inspect(path) for path in targets]

    report_columns(observations)
    report_menu_and_hour(observations)
    report_summary(observations)

    log("\n이 결과를 docs/03_POS_분석결과.md에 옮겨 적으면 STEP 1이 끝납니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
