"""
Vercel 서버리스 함수 진입점.

Vercel의 Python 런타임은 이 파일에서 `app`(ASGI) 을 찾아 실행한다.
**로직은 두지 않는다** — 앱 조립은 `server/main.py` 가 하고, 여기서는 그것을 가리킬 뿐이다.
파일 위치(`api/`)와 이름이 곧 라우팅이므로 옮기면 배포가 깨진다.

`vercel.json` 의 rewrite 가 모든 경로를 이 함수로 보낸다. FastAPI 가 그 안에서
API와 정적 파일(`web/`)을 함께 서빙한다 — 배포 대상을 하나로 줄이기 위함이다.

⚠ 이 함수는 **POS에 접근하지 않는다.** POS 계정도 여기 없다.
  수집은 GitHub Actions 가 하고, 화면은 Neon 에서 읽기만 한다
  (CLAUDE.md 「POS 접근은 오직 collector/ 안에서만」의 배포판).

⚠ Vercel Hobby 함수는 10초에서 끊긴다. 수집기를 여기서 돌릴 수 없는 이유다.
"""

from __future__ import annotations

import sys
from pathlib import Path

# 저장소 루트를 import 경로에 넣는다 — 함수는 api/ 안에서 실행된다
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.main import app  # noqa: E402,F401 — Vercel 이 이 이름을 찾는다
