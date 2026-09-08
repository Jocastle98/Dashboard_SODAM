# CLAUDE.md

> 이 파일은 Claude Code가 매 세션 자동으로 읽는 프로젝트 컨텍스트입니다.

## 프로젝트

샤브샤브 **소담촌 마곡점** 매출 분석 대시보드.
소상공인 매출증대 AI 빅데이터 공모전 제출물이며, 최종 사용자는 마곡점 사장님 1인입니다.

목표: 사장님이 URL 하나로 접속해 **매일 자동 갱신되는 매출·메뉴·시간대 데이터**를 확인한다.

## 반드시 먼저 읽을 문서

| 파일 | 내용 |
|---|---|
| `docs/00_진행가이드.md` | 단계별 진행 순서(STEP 1~6)와 분기 판단 |
| `docs/01_요구사항명세서_SRS.md` | 기능/비기능 요구사항, 완료 기준, 리스크 |
| `docs/02_기능명세서_FS.md` | 화면·API·DB 스키마·테스트케이스 |
| `docs/03_POS_분석결과.md` | POS 엔드포인트 실측 결과 (**진행하며 계속 갱신할 것**) |

요구사항 ID(`FR-DASH-02`)와 기능 ID(`FN-220`)는 위 문서에 정의되어 있습니다.
**코드 주석과 커밋 메시지에 해당 ID를 명시**하여 추적 가능하게 하세요.

## 아키텍처 — 왜 이 구조인가

```
브라우저 (대시보드)  →  백엔드 API  →  DB  ←  수집기  →  POS(topint.co.kr)
```

**프론트엔드에서 topint.co.kr에 직접 요청하지 마세요.** CORS로 차단되며, 계정 정보가 노출됩니다.
POS 접근은 **오직 `collector/` 안에서만** 이루어집니다.

## POS 실측 정보 (STEP 1 완료 — 상세는 `docs/03`)

**도메인이 두 개다.** 로그인은 포털, 리포트는 asp 서브도메인.

```
POST https://topint.co.kr/act/member/login     mem_id / mem_pwd / mem_seq / rtn_page
GET  https://asp.topint.co.kr/asp_office/sale/...
서버: Classic ASP / IIS 8.5 / MS SQL Server
```

**사용하는 리포트 3종** (전부 `opendate_s`/`opendate_e` = YYYYMMDD):

| 용도 | 엔드포인트 | 추가 파라미터 |
|---|---|---|
| 주문 단위 상세 (일별·결제수단) | `sale/agentAnal_com_excel01.asp` | `branch=sodam001&branchAddChk=` |
| 시간대별 | `sale/timeAnal_excel.asp` | `brandcode=`(**비움**)`&branch=sodam001` |
| 메뉴별 | `sale/menuAnal_sub_1_excel.asp` | `brandcode=`(**비움**)`&branch=sodam001&bcode=&gcode=` |

**함정 5가지 — 반드시 지킬 것:**

1. **인코딩은 euc-kr.** UTF-8로 디코딩하면 메뉴명이 전부 깨집니다. 모든 응답 파싱에 `errors="replace"` 대신 정확한 `euc-kr` 디코딩을 적용하세요.
2. **`.xls` 확장자를 믿지 마세요.** Classic ASP는 HTML `<table>`을 엑셀 MIME으로 내보내는 경우가 많습니다. 파일 시그니처로 판별한 뒤 파서를 선택하세요 (`collector/probe_topint.py`의 `sniff_format()` 참고).
3. **세션 만료 감지.** 만료 시 200 응답에 로그인 HTML이 담겨 옵니다. Content-Type과 본문을 검사해 조용한 실패를 막으세요.
4. **인증하는 건 `ASPSESSIONID`가 아닙니다.** 매장 식별은 `.topint.co.kr` 신원 쿠키 8개(`comID`, `custCode`, `comNo`, `memID` …)가 합니다. `ASPSESSIONID`는 없어도 되고, 그것만 보내면 리포트가 비어서 옵니다. 수동 쿠키를 쓰지 말고 `auth.create_session()`을 쓰세요.
5. **인코딩이 한 문서 안에서 섞입니다.** `charset=euc-kr` 선언인데 `총매출액`/`순매출액`만 UTF-8 바이트입니다. 단일 인코딩으로는 디코딩 자체가 실패합니다. `formats.decode_korean()`이 바이트 런 단위로 처리하며, **`cp949`를 `utf-8`보다 먼저 시도하면 예외 없이 조용히 깨집니다.**
6. **500 응답에도 엑셀 MIME이 붙습니다.** 상태코드와 본문을 함께 검사하세요.
7. **`<table>`이 중첩되어 있습니다.** 그대로 파싱하면 첫 행이 전 셀을 이어붙인 문자열이 됩니다. **최빈 열 개수**로 진짜 데이터 행만 거르세요 (19/6/7열).

## 보안 규칙 (위반 금지)

- POS 계정은 **`.env`에만** 둡니다. 소스·문서·커밋·로그 어디에도 하드코딩 금지.
- `.env`는 반드시 `.gitignore`에 포함. `.env.example`만 커밋합니다.
- 대시보드 로그인 계정과 POS 계정은 **분리**합니다. 비밀번호는 bcrypt 해시로 저장.
- API 응답·프론트엔드 번들에 POS 계정이나 세션 쿠키가 절대 실려서는 안 됩니다.
- 로그에 쿠키·비밀번호를 출력하지 마세요. 마스킹 처리할 것.
- 커밋 전 실제 매출 수치가 담긴 샘플 파일이 포함되지 않았는지 확인하세요.

## POS 서버 배려

- 요청 간 **최소 1초 대기**. 초기 12개월 적재 시에도 예외 없음.
- 재시도는 3회, 5s/15s/45s 지수 백오프.
- User-Agent를 명시하고 Referer를 함께 보냅니다.
- 부하 테스트·병렬 요청 금지. 남의 운영 서버입니다.

## 기술 스택

| 영역 | 선택 |
|---|---|
| 수집기 | Python 3.11 / requests / pandas / beautifulsoup4 |
| 백엔드 | FastAPI + uvicorn |
| DB | SQLite (개발·오프라인) / PostgreSQL·Neon (배포) — `DATABASE_URL` 접두사로 갈림 |
| 프론트 | 순수 HTML/CSS/JS + Chart.js (빌드 도구 없이) |
| 스케줄 | APScheduler |

프론트엔드는 **빌드 없이 정적 파일로 동작**해야 합니다. 사장님 환경에서 문제가 생겼을 때 파일 하나만 열어보면 되도록.

## 산출물 형태 (2026-08-17 결정)

**서버 배포 + 단일 HTML 병행.** 같은 정적 프론트엔드 코드로 둘 다 만든다.

| 산출물 | 용도 | 갱신 | 만드는 것 |
|---|---|---|---|
| 서버 배포 (URL) | 사장님 상시 사용. 휴대폰 포함 | 매일 04시 자동 + 버튼 | — |
| **바로가기 HTML** | **사장님께 파일 하나로 전달** | ✅ 항상 최신 | `server/shortcut.py` |
| 단일 HTML 스냅샷 | 시연·공모전 제출·백업 | ❌ 생성 시점 고정 | `server/export.py` |

브라우저가 POS에 직접 접근할 수 없으므로(CORS·계정노출·세션) **파일 안에 데이터를 담은
채로 스스로 갱신되는 HTML은 불가능**하다. 갱신 주체는 반드시 서버다.

그래서 "파일 하나 + 항상 최신"은 **바로가기**로 만족시킨다 (2026-09-08 결정).
매출 수치가 한 글자도 없어 전달·보관에 제약이 없다. 스냅샷은 오프라인 시연용으로 남긴다.
**오프라인 + 최신 조합만은 어떤 방식으로도 안 된다.**

`web/`의 위젯 코드는 세 산출물이 그대로 공유한다 — 화면 코드를 두 벌 두지 않는다.

## 디렉터리

```
collector/   POS 수집·파싱·적재    (POS 접근은 여기서만)
collector/db/ DB 연결·방언          (SQLite ↔ PostgreSQL 차이는 여기서만)
server/      FastAPI 앱, API 라우터
api/         Vercel 함수 진입점 + 함수 전용 requirements.txt
web/         정적 프론트엔드
db/          스키마·마이그레이션
docs/        명세서
tests/       테스트
data/        수집 원본 (gitignore)
```

### server/ 모듈 구성

| 모듈 | 책임 |
|---|---|
| `main.py` | 앱 조립·오류 형식 통일·정적 파일 서빙 |
| `deps.py` | 설정/DB/현재 사용자/기간 파싱 의존성 |
| `security.py` | bcrypt, 세션 서명, 로그인 시도 제한 |
| `repository/` | SQL — **여기 밖으로 SQL이 나가지 않는다** |
| `service/` | 명세(docs/02 5장) 응답 형태로 가공 |
| `service/menu_alias.py` | 메뉴 표시명 별칭 — POS 원본은 보존, 표시만 교체 (FN-251) |
| `routers/` | 조율만 |
| `seed.py` | 대시보드 계정 생성 (`.env` → bcrypt) |
| `collect_trigger.py` | 수동 수집 트리거 — **local/github 판단은 여기서만** (FN-205) |
| `export.py` | 단일 HTML 내보내기 — `web/` 자산을 인라인한 스냅샷 (시점 고정) |
| `shortcut.py` | 바로가기 HTML — 배포 대시보드로 보내는 창구 (항상 최신) |
| `db.py` | 조회용 커넥션 — 연결·방언은 `collector/db/` 가 전부 한다 |

### web/ 모듈 구성

| 파일 | 책임 |
|---|---|
| `index.html` / `dashboard.html` | SCR-01 / SCR-02 |
| `js/api.js` | fetch 단일 창구, 401 처리 — **POS 주소가 들어가면 테스트가 실패한다** |
| `js/format.js` | 숫자·날짜 표기 규칙 (docs/02 8.4) |
| `js/charts.js` | Chart.js 공통 옵션 |
| `js/widgets/` | 위젯별 개별 로딩 (FN-260) |
| `js/refresh.js` | 지금 수집 버튼 — 트리거·폴링·완료 후 재조회 (FN-205) |
| `js/dashboard.js` | 기간 필터 조율만 |

### collector/ 현재 모듈 구성

| 모듈 | 책임 |
|---|---|
| `config.py` | `.env` 로딩, `Settings` — **환경변수는 여기서만 읽는다** |
| `db/dialect.py` | SQLite↔PostgreSQL 차이의 단일 출처 — 자리표시자·불리언·요일함수·스키마파일 |
| `db/session.py` | 커넥션 래퍼 — repository가 방언을 몰라도 되게 한다 |
| `db/drivers.py` | 커넥션 생성 (sqlite3 / psycopg). `prepare_threshold=None` 이유가 여기 |
| `db/__init__.py` | 공개 창구 — `connect()` / `apply_schema()` / `now()` / `describe_target()` |
| `migrate.py` | CLI — DB 이관 (SQLite→Neon). **POS 요청 없음**, 재실행 안전 |
| `logutil.py` | 로그 출력, 비밀값 `mask()`, UTF-8 출력 고정 |
| `formats.py` | `sniff_format()` / `decode_korean()` / `looks_like_login_page()` / `extract_tables()` — **인코딩·포맷 함정이 전부 여기 모여 있다** |
| `auth.py` | 포털 자동 로그인, 세션 확보 — **세션 생성은 `create_session()` 하나로** |
| `pos_client.py` | 리포트 3종 요청, 재시도 3회(5/15/45s), 요청 간 1초 대기 — **POS 요청은 여기서만** |
| `probe_observer.py` | 관측 — 응답/파일 해석 규칙의 단일 출처 |
| `probe_report.py` | 관측 결과 해석·분기 판단 |
| `probe_forms.py` | 화면 폼/파라미터 추출 (HTML 분석만) |
| `parse/tables.py` | 표 선택·중복제거·값 정규화 — **3종 파서의 단일 출처** |
| `parse/orders.py` `parse/menu.py` `parse/cancels.py` | 리포트별 파서 |
| `aggregate.py` | 주문 → 일별·시간대별 집계, 품질 검증(DQ-03) |
| `repository.py` | UPSERT 적재 — **SQL은 여기서만** |
| `service.py` | 수집 파이프라인 (조회→파싱→집계→적재) |
| `main.py` | 수집기 CLI 진입점 (조율만) |
| `scheduler.py` | 매일 04시 수집 (FN-601) — 겹쳐 돌지 않게 max_instances=1 |
| `notify.py` | 수집 실패 알림 (FN-606) — 알림 실패가 수집을 멈추지 않는다 |
| `probe_topint.py` | CLI — 리포트 실측 |
| `probe_discover.py` | CLI — 화면·파라미터 탐색 |
| `inspect_file.py` | CLI — 내려받은 파일 분석 |

`probe_topint`와 `inspect_file`은 `probe_observer.inspect_content()`를 **같이 호출**한다.
해석 규칙을 두 벌 두지 않기 위함이다.

## 코드 작성 원칙 — 모듈화 (필수)

**모든 코드는 모듈 단위로 분리해서 작성한다.** 한 파일에 여러 관심사를 몰아넣지 않는다.

- **한 모듈 = 한 책임.** 요청·파싱·적재·표현을 같은 파일에 섞지 않는다.
- **규칙은 한 곳에만.** euc-kr 디코딩, 포맷 판별, 세션 만료 판정 같은 규칙이 두 파일에 중복되면
  한쪽만 고쳐져서 조용히 어긋난다. `formats.py`처럼 단일 출처를 두고 재사용한다.
- **진입점은 조율만.** `probe_topint.py`, `main.py`, 라우터 파일에는 로직을 두지 않는다.
- **의존 방향은 한 방향.** `entry → service → client/format → config`. 역방향 import 금지.
- 서버는 `router / service / repository`로, 프론트는 `api.js / charts.js / format.js / widgets/`로 분리한다.
- 새 기능을 기존 파일에 덧붙이기 전에 **새 모듈이 맞는지 먼저 판단**한다.

## 작업 방식

- **한 세션에 한 단계씩.** 여러 단계를 한꺼번에 진행하지 마세요.
- 코드 작성 전 **무엇을 만들지 먼저 요약**하고 확인을 받으세요.
- POS 응답 구조는 추측하지 말고 **실제 파일을 확인한 뒤** 파서를 작성하세요. 추측한 컬럼명으로 코드를 짜면 전부 다시 짜야 합니다.
- 새로 알아낸 POS 동작은 즉시 `docs/03_POS_분석결과.md`에 기록하세요.
- 실제 매출 데이터로 검증되기 전까지 어떤 단계도 "완료"로 표시하지 마세요.

## 실행 방법

```bash
python -m pip install -r requirements.txt
cp .env.example .env          # 실제 값 입력 (커밋되지 않음)

python -m collector.main --init             # DB 스키마 적용
python -m collector.main --days 7           # 최근 7일 수집 (검증용)
python -m collector.main --backfill         # 과거 12개월 적재
python -m collector.main --yesterday        # 전일 수집 (스케줄러용)
python -m collector.main --status           # 적재 현황

python -m collector.migrate --from sqlite:///./data/sodam.db   # SQLite → Neon 이관 (POS 요청 없음)
python -m collector.migrate --from sqlite:///./data/sodam.db --verify-only

python -m server.seed                       # 대시보드 계정 생성 (bcrypt)
python -m server.main                       # 대시보드 서버 (http://127.0.0.1:8000)

python -m collector.scheduler --once        # 스케줄러 작업 1회 실행 (검증)
python -m collector.scheduler              # 스케줄러 상주 실행
python -m server.export --days 30          # 단일 HTML 스냅샷 → dist/ (시점 고정)
python -m server.shortcut                  # 바로가기 HTML → dist/ (항상 최신, DASHBOARD_URL 필요)

# 로컬은 .env 의 SQLite 를 쓴다. Neon 을 향해 돌리려면:
DATABASE_URL="$(grep -m1 ^DATABASE_URL= .env.neon | cut -d= -f2-)" python -m pytest tests/ -q

python -m collector.probe_topint --quick    # 리포트 실측 (자동 로그인)
python -m collector.probe_discover          # 화면·파라미터 탐색
python -m collector.inspect_file            # data/probe/에 넣어둔 파일 분석
python -m pytest tests/ -q                  # 테스트
```

## 현재 진행 상태

- [x] 요구사항·기능 명세 작성
- [x] POS 다운로드 엔드포인트 확인
- [x] STEP 0 — 저장소 구조, `.gitignore`, `.env.example`, `requirements.txt`
- [x] STEP 1 — POS 실측 완료. 리포트 3종 확보, 2년 소급 가능 확인 (`docs/03`)
- [x] STEP 2 — 로그인 자동화 (`collector/auth.py`) — 실제 로그인 검증 완료
- [x] STEP 3 — DB 스키마 + 파서 + 초기 적재
      **12개월 실데이터 적재 완료** (2025-08-21~2026-08-16, 주문 16,116건)
      DQ-03 361일 전부 통과, 결제수단 합 16,116건 전부 일치
- [x] STEP 4 — API 구현 (`server/`) — 실 DB 데이터로 검증, 테스트 76건 통과
- [x] STEP 5 — 대시보드 UI 틀 (`web/`) — 로그인·KPI·4개 차트 동작
- [x] STEP 6 — 스케줄러(`--once` 실행 검증) + 단일 HTML 내보내기 + 배포 구성
      (Dockerfile / fly.toml / render.yaml / `docs/06_배포가이드.md`)
- [x] STEP 6-2 — 사용자 요청 3건 (2026-09-08). 테스트 106건 통과
      · FN-205 지금 수집 버튼 (`collect_trigger.py` local/github 2백엔드)
        + `.github/workflows/collect.yml` (schedule + workflow_dispatch)
      · FN-235 지난주 같은 요일 대비 (`/api/sales/weekly-compare` + 위젯)
      · FN-251 메뉴 표시명 별칭 (`초등학생(70g)` → `초등학생 월남쌈샤브 (70g)`)
      · 바로가기 HTML (`server/shortcut.py`) — "파일 하나 + 항상 최신"
- [x] STEP 7-1 — **PostgreSQL 이식 완료** (2026-09-08). 테스트 126건 통과
      · `collector/db/` 4모듈 신설 — 방언 차이를 한 곳에 모음
      · Neon 이관 완료: 10테이블 32,770행. **SQLite/Neon 서비스 응답 완전 일치 확인**
        (4개 기간 × 8개 응답 대조 — 요일 번호 포함)
      · 부수 발견: 메뉴 순위 SQL에 동점 처리가 없어 순서가 흔들리던 것 수정
      · 부수 발견: `datetime('now')`와 `now()`가 다른 형식을 만들던 것 통일
- [x] STEP 7-2 — **Vercel 배포 완료** (2026-09-09)
      https://sodam-dashboard.vercel.app  (sodam5/sodam-dashboard)
      · 리전 확인: `X-Vercel-Id: icn1::sin1::` — 서울 PoP 진입, 싱가포르 함수 실행
      · 화면 체감 ~166ms (API 7개 병렬) / 정적 파일 CDN HIT 27ms
      · 로그인·KPI·요일비교·메뉴별칭 전부 프로덕션에서 값 일치 확인
      · 바로가기 HTML 생성 → `dist/소담촌마곡점_대시보드_바로가기.html`
- [ ] **← 현재: STEP 7-3 — 자동 수집 연결**
      · GitHub Actions Secrets 등록 + 워크플로 커밋·푸시 (아직 한 번도 안 돌았다)
      · Vercel 에 `DISPATCH_REPO`/`DISPATCH_TOKEN` 등록 → 「지금 수집」 버튼 활성화
      · 현재 `/api/system/collect/status` 는 `backend=none`, 버튼은 숨겨져 있다
      · 데이터가 2026-08-16 까지라 갱신 배지가 `failed` 로 보인다 (수집이 붙으면 해소)
      Fly.io 무료 폐지로 방향 전환. 수집=GitHub Actions / DB=Neon / 화면=Vercel
      아래 「다음 세션 시작점」의 "지금 할 일" 순서대로 — **PostgreSQL 이식부터**
- [ ] 세부 기능: 이동평균·히트맵 토글, CSV 내보내기(FN-264),
      메뉴 상세(SCR-03), 관리자 화면(SCR-05)

## 🔖 다음 세션 시작점 (2026-08-18 중단)

**"무엇부터 할까요?"라고 물으면 → 아래 「지금 할 일」 0번부터 이어서 진행할 것.**
호스팅 비교는 이미 끝났다. 다시 검토하지 말고 확정된 구성으로 진행한다.

### 확정된 배포 구성 (2026-08-18 결정)

Fly.io는 2024-10부터 신규 계정 무료 허용량이 폐지됐다(최소 월 $2). `docs/06` 1장의
"A / 0원" 표는 **틀린 정보이며 수정 대상**이다. 그리고 Vercel Hobby는 함수가 **10초**에서
끊긴다 — `pos_client.py`의 재시도 백오프(5/15/45초)만 최대 65초라 **수집기를 Vercel에
올리는 것은 불가능**하다. 그래서 역할을 셋으로 나눈다.

| 역할 | 서비스 | 근거 |
|---|---|---|
| 수집 (매일 자동 + 수동 버튼) | **GitHub Actions** | 실행시간 제한 사실상 없음 → 현재 코드 무수정. public 저장소라 분당 과금 없음 |
| 데이터 보관 | **Neon Postgres 무료** | 영구 무료 + 상업적 이용 허용 + 카드 불필요. 0.5GB 중 사용량 5.5MB |
| 화면 (사장님 접속) | **Vercel Hobby** | git push → 자동 배포 |

갱신 트리거는 **자동(매일 1회) + 수동(Actions `Run workflow` 버튼)** 두 가지만 넣는다.
**"접속 시 갱신"은 채택하지 않았다** — 사장님이 POS 응답을 기다려야 하고, 탭을 여러 개
열면 POS에 동시 요청이 가서 「POS 서버 배려」 규칙을 어긴다.

### ⚠ 최우선 — public 저장소에 실매출이 공개돼 있다

사용자가 public 유지를 선택했다(2026-08-18). 그러나 아래는 **사장님 영업 기밀**이다.

| 위치 | 내용 |
|---|---|
| `docs/05_DB스키마_확정안.md:403` | 총 매출 943,159,900원 / 주문 16,116건 / 객단가 58,523원 |
| `docs/03_POS_분석결과.md:205-206, 249-250, 338-340` | 일별 실매출·결제수단 실측치 |

**세션 시작 시 이 수치를 예시값으로 치환할지 먼저 물을 것.** 히스토리까지 지우려면
force push가 필요하고, 이미 공개된 값은 캐시에 남을 수 있다는 점도 함께 알린다.
`.env`·`*.db`·`data/`·`dist/`는 **한 번도 커밋된 적 없다** (2026-08-18 전체 히스토리 검사 완료).

### 지금 할 일 (이 순서 그대로)

| # | 작업 | 담당 | 상태 |
|---|---|---|---|
| 0 | 실매출 수치 치환 여부 확인 | 사용자 판단 | ⬜ |
| 1 | Neon 가입 → `.env`의 `DATABASE_URL` | 사용자 | ✅ 2026-09-08 |
| 2 | `db/schema.sql` PostgreSQL 이식 | Claude | ✅ `db/schema_pg.sql` |
| 3 | `collector/repository.py` 드라이버·방언 교체 | Claude | ✅ |
| 4 | `server/db.py` + `server/repository/` 교체 | Claude | ✅ |
| 5 | Neon 적재 + `pytest` 통과 확인 | Claude | ✅ 이관으로 대체 (POS 재수집 불필요) |
| 6 | GitHub Actions 워크플로 (schedule + workflow_dispatch) | Claude | ✅ 2026-09-08 |
| 7 | FastAPI → Vercel 함수 + `vercel.json` | Claude | ✅ 파일 준비 완료 (배포는 미실행) |
| 8 | `docs/06` 요금 정보 수정 (Fly.io 무료 폐지 반영) | Claude | ✅ |
| 9 | `vercel login` → 환경변수 → `vercel --prod` | 둘 다 | ✅ 2026-09-09 |
| 10 | Actions Secrets 등록 + `Run workflow` 1회 검증 | 둘 다 | ⬜ |
| 11 | `DASHBOARD_URL` + 바로가기 HTML 생성 | Claude | ✅ 2026-09-09 |

**6번은 파일만 만들어 뒀고 아직 한 번도 돌지 않았다.** Neon(`DATABASE_URL`)과
Actions Secrets이 없으면 실패한다 — 2~5번을 끝낸 뒤 Actions 화면에서
`Run workflow`로 1회 검증할 것.

**2~5(이식)를 먼저 끝내 검증한 뒤 6~7(배포)로 넘어간다.** 이식이 안 끝난 상태에서
Actions·Vercel을 붙여도 검증할 대상이 없다. 1번이 안 됐으면 그것부터 요청한다.

### PostgreSQL 이식 — 완료. 결정한 것과 그 이유

`collector/db/` 4모듈로 방언 차이를 한 곳에 모았다. repository는 `?` 자리표시자로
SQL을 쓰고, 갈리는 조각만 `session.dialect`에 물어본다 (전역 상태 없음).

**로드맵과 다르게 결정한 것 3가지 — 되짚지 말 것:**

| 로드맵 | 실제 결정 | 이유 |
|---|---|---|
| `TEXT`(시각) → `TIMESTAMPTZ` | **TEXT 유지** | 조회 결과가 `datetime` 객체가 되면 `fromisoformat(text)`·`_parse_iso()`가 깨지고, ISO 문자열을 dict 키로 쓰는 서비스 코드(`{row["biz_date"]: row}`)가 조용히 빈다 |
| `datetime('now')` → `NOW()` | **DB DEFAULT 제거** | 두 함수가 서로 다른 형식을 만들어 한 DB 안에 형식이 두 가지였다. 형식은 `db.now()` 한 곳에서만 정한다 |
| `--backfill`로 12개월 재적재 | **`collector/migrate.py`로 이관** | 이미 검증된 데이터다. POS 389요청을 다시 보낼 이유가 없다 |

`GENERATED BY DEFAULT AS IDENTITY`를 쓴 이유: 이관 때 `menu_id`/`store_id`를 그대로
유지해야 `menu_sales` 참조가 살아남는다. 옮긴 뒤 `setval`로 시퀀스를 맞춘다.

### ⚠ `vercel.json` 에 주석을 넣을 수 없다

Vercel 은 스키마를 엄격히 검증한다. `"//"` 키는 **최상단에도** 거부된다
(`vercel link` 는 통과하지만 `vercel deploy` 가 막는다). 설정 근거는
`docs/06` 2-E 장에만 둔다 — 파일에 다시 주석을 넣지 말 것.

FastAPI 는 Vercel 이 `services` 모델로 잡는다. 그래서 최상단 `functions` 를 쓸 수 없고,
서비스에 `entrypoint: "server.main:app"` 가 필요하다. `api/index.py` 는 이 경로에서
쓰이지 않지만 자체 호스팅용으로 남겨 둔다.

### 리전 = 싱가포르 조합 (2026-09-09 완료)

Vercel 함수 `sin1` ↔ Neon `ap-southeast-1`. 둘 다 설정 완료.
**한쪽만 바꾸면 안 된다** — 아래 표의 최악 조합이 된다.

**Vercel에 서울 리전(`icn1`)이 있는데도 싱가포르를 쓰는 이유:**
API 호출 하나가 DB를 3회쯤 왕복하는데(`/api/summary` = 기간합계×2 + 수집이력),
브라우저→함수 왕복은 위젯들이 병렬로 불러 화면 한 장에 사실상 1회다.
DB 왕복만 배수로 늘어나므로 **사용자 옆보다 DB 옆이 이긴다.**

| 조합 | 브라우저→함수 | 함수→DB ×3 | 화면 한 장 |
|---|---|---|---|
| **sin1 + ap-southeast-1** (채택) | ~80 ms | 3 × ~5 ms | **~95 ms** |
| icn1(서울) + ap-southeast-1 | ~10 ms | 3 × ~70 ms | ~220 ms |
| sin1 + us-east-2 | ~80 ms | 3 × ~230 ms | ~770 ms |

실측: `SELECT 1` 왕복이 오하이오 400ms → 싱가포르 **70ms**, pytest 134초 → **57초**.
로컬 SQLite는 7초 — **이 느림은 로컬 개발만의 문제다.** 배포하면 쿼리가 DB 옆에서 돈다.

✅ **Hobby도 단일 리전 지정은 된다** (2026-09-09 Vercel 문서 확인).
`Hobby = Single region / Pro = 5 / Enterprise = All`. 제한은 복수 리전에만 걸린다.
플랜보다 많이 넣으면 빌드 이전에 배포가 실패하므로 `["sin1"]` 하나를 유지할 것.

**원본은 로컬 `data/sodam.db`다.** Neon 프로젝트를 지워도 데이터를 잃지 않는다 —
`migrate.py`로 26초에 복구되고 POS 요청은 0회다.

### 이식 전에 파악해 둔 것 (기록 보존)

SQL이 `repository`에만 모여 있어(본 문서 「모듈화」 규칙) **고칠 파일은 5개뿐**이다.

| 대상 | 바꿀 것 |
|---|---|
| `db/schema.sql` | `INTEGER PRIMARY KEY AUTOINCREMENT`→`SERIAL`, `TEXT`(시각)→`TIMESTAMPTZ`, `INTEGER`(0/1)→`BOOLEAN`, `datetime('now')`→`NOW()` |
| `collector/repository.py` | `sqlite3`→`psycopg`, 자리표시자 `?`→`%s`, `sqlite3.Row`→`dict_row` |
| `collector/service.py` | 타입 힌트 `sqlite3.Connection` 정리 |
| `server/db.py` | 커넥션 풀. Neon은 5분 유휴 시 scale-to-zero → 첫 요청 지연을 감안할 것 |
| `server/repository/sales.py` | `strftime('%w', ...)`→`EXTRACT(DOW FROM ...)` — **요일 번호 기준이 달라 반드시 확인** |

UPSERT(`ON CONFLICT ... DO UPDATE`)는 양쪽 문법이 같아 그대로 쓴다.
`--backfill`은 **로컬에서 원격 Neon을 향해 1회** 실행한다 (약 7분, POS 389요청).

### 비밀값을 어디에 두는가 — `.env`는 계속 이그노어

`.env`는 내 PC 전용이며 커밋하지 않는다. 같은 값을 서비스별로 따로 등록한다.

**Vercel 에 `.env` 를 그대로 복사하지 말 것.** 로컬 `.env` 에는
`SCHEDULER_ENABLED=true` 와 POS 계정이 들어 있다 — 서버리스에는 상주 프로세스가 없고,
`true` 면 함수가 APScheduler 와 POS 클라이언트를 적재한다.

| 비밀값 | GitHub Actions Secrets | Vercel 환경변수 |
|---|---|---|
| `POS_USER_ID` / `POS_USER_PW` | ✅ | ❌ **넣지 않는다** |
| `DATABASE_URL` (Neon) | ✅ 쓰기 | ✅ 읽기 |
| `SESSION_SECRET` | ❌ | ✅ |
| `DASHBOARD_ADMIN_ID` / `_PW` | ✅ (계정 생성 1회) | ❌ |
| `DISPATCH_REPO` / `DISPATCH_TOKEN` | ❌ | ✅ (지금 수집 버튼) |

`.env` 는 **로컬 SQLite** 를 가리킨다. Neon 주소는 `.env.neon` 에 따로 두고
(`.gitignore` 의 `.env.*` 로 제외) Vercel·Actions 에 등록한다.
`SESSION_COOKIE_SECURE` 는 Vercel 에서 자동으로 켜진다 — 등록하지 않아도 된다.

**Vercel에는 POS 계정을 올리지 않는다.** 사장님이 접속하는 쪽이 POS 계정을 들 이유가 없다.
이것이 「POS 접근은 오직 `collector/` 안에서만」 규칙의 배포판이다.

### 알고 갈 것 — Vercel Hobby는 상업적 이용 금지

Hobby 약관은 "관련된 누구든 금전적 이익을 목적으로 하는 배포"를 금지한다. 공모전 데모는
허용 예시에 가깝지만, 사장님이 영업에 상시 사용하면 회색지대다. 문제가 되면 **Cloudflare
Pages**(무료·상업적 이용 명시 허용·git 연동 배포)로 옮긴다 — 정적 프론트라 10분이면 된다.

### 수동 수집 버튼 — 배포 시 남은 일

`server/collect_trigger.py`는 백엔드 2종을 다 구현했다. **`local`은 실제 POS 수집으로
검증됐고, `github`은 단위 테스트만 통과한 상태다** (Neon·Actions가 아직 없어서).

배포 후 Vercel에 넣을 것 (`docs/06` 5-2장):

| 이름 | 값 | 비고 |
|---|---|---|
| `DISPATCH_REPO` | `소유자/저장소` | |
| `DISPATCH_TOKEN` | fine-grained PAT | **권한은 Actions: Read and write 하나만** |
| `DASHBOARD_URL` | 배포 주소 | 바로가기 HTML이 가리킬 곳 |

`GITHUB_` 접두사를 쓰지 않은 이유: Actions가 그 이름 공간을 예약해 쓴다.

⚠ **Actions `schedule`은 저장소 60일 무활동 시 자동 정지한다.** 자동 수집이
조용히 끊기고 알림이 없다. `docs/06` 7장의 월 1회 점검 항목에 넣어 뒀다.

### 재개 시 확인 (1분)

```bash
python -m pytest tests/ -q          # 126건 통과해야 정상
python -m collector.main --status   # 2025-08-21 ~ 2026-08-16 / orders 16,000+
```

`data/sodam.db`가 없어졌다면 (약 7분):
```bash
python -m collector.main --init && python -m server.seed
python -m collector.main --backfill
```

### 되짚을 필요 없는 것 (이미 해결)

- POS 인증 — `comID`/`memID` 쿠키가 핵심. `auth.create_session()`이 처리
- 인코딩 혼재 — `formats.decode_korean()`이 바이트 런 단위로 처리
- 중첩표 2배 — `parse/tables.py`가 표 선택 + 중복 제거 2겹으로 방어
- 시간대 데이터 — `timeAnal` 수집 불필요. 주문의 `sold_at`에서 유도
- **호스팅 비교** — 2026-08-18 결론. Fly.io 유료화, Vercel 단독은 10초 제한으로 불가
- **`collector/scheduler.py` (APScheduler)** — Vercel엔 상주 프로세스가 없어 배포 경로로
  쓰지 않는다. 로컬·자체 서버용으로 남겨두고, 배포 스케줄은 GitHub Actions가 담당한다

## 사용자 확인 필요 (코드로 해결 불가)

- REQ-LEGAL-01 — 탑아이앤티 이용약관의 자동화 접근 조항 확인, 매장주 서면 동의
- NFR-SEC-07 — 공유된 계정 비밀번호 변경 후 `.env`에 반영
- SRS 2.3 1순위 — 탑아이앤티 공식 API 제공 여부 문의
