"""
대시보드 백엔드 (FastAPI).

의존 방향은 한 방향이다 (CLAUDE.md 모듈화 원칙):
    routers → service → repository → db
라우터에는 로직을 두지 않고, SQL은 repository 밖으로 나가지 않는다.

POS 접근은 collector/ 안에서만 이루어진다. 이 패키지는 DB만 바라본다.
"""
