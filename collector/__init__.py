"""
POS 수집기 패키지.

CLAUDE.md 규칙: POS(topint.co.kr) 접근은 오직 이 패키지 안에서만 이루어진다.
server/ 와 web/ 은 DB만 바라본다.

모듈 구성:
    config.py          .env 로딩 / Settings
    logutil.py         로그 · 비밀값 마스킹
    formats.py         포맷 판별 · euc-kr 디코딩 · 표 추출
    pos_client.py      HTTP 요청 · 재시도 · 요청 간 1초 대기
    probe_observer.py  STEP 1 관측
    probe_report.py    STEP 1 해석 · 분기 판단
    probe_topint.py    STEP 1 CLI 진입점
"""

__all__ = ["config", "logutil", "formats", "pos_client"]
