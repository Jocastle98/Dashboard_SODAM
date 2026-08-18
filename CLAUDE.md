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
| DB | SQLite (개발) → PostgreSQL (배포) |
| 프론트 | 순수 HTML/CSS/JS + Chart.js (빌드 도구 없이) |
| 스케줄 | APScheduler |

프론트엔드는 **빌드 없이 정적 파일로 동작**해야 합니다. 사장님 환경에서 문제가 생겼을 때 파일 하나만 열어보면 되도록.

## 산출물 형태 (2026-08-17 결정)

**서버 배포 + 단일 HTML 병행.** 같은 정적 프론트엔드 코드로 둘 다 만든다.

| 산출물 | 용도 | 갱신 |
|---|---|---|
| 서버 배포 (URL) | 사장님 상시 사용. 휴대폰 포함 | 매일 04시 자동 |
| 단일 HTML 파일 | 시연·공모전 제출·백업 | 생성 시점 고정 |

브라우저가 POS에 직접 접근할 수 없으므로(CORS·계정노출·세션) **HTML 더블클릭만으로
자동 갱신되는 구조는 불가능**하다. 단일 HTML은 수집 결과를 파일에 박아 넣은 스냅샷이다.
`web/`의 위젯 코드는 두 산출물이 그대로 공유한다 — 화면 코드를 두 벌 두지 않는다.

## 디렉터리

```
collector/   POS 수집·파싱·적재    (POS 접근은 여기서만)
server/      FastAPI 앱, API 라우터
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
| `routers/` | 조율만 |
| `seed.py` | 대시보드 계정 생성 (`.env` → bcrypt) |
| `export.py` | 단일 HTML 내보내기 — `web/` 자산을 인라인한 스냅샷 |

### web/ 모듈 구성

| 파일 | 책임 |
|---|---|
| `index.html` / `dashboard.html` | SCR-01 / SCR-02 |
| `js/api.js` | fetch 단일 창구, 401 처리 — **POS 주소가 들어가면 테스트가 실패한다** |
| `js/format.js` | 숫자·날짜 표기 규칙 (docs/02 8.4) |
| `js/charts.js` | Chart.js 공통 옵션 |
| `js/widgets/` | 위젯별 개별 로딩 (FN-260) |
| `js/dashboard.js` | 기간 필터 조율만 |

### collector/ 현재 모듈 구성

| 모듈 | 책임 |
|---|---|
| `config.py` | `.env` 로딩, `Settings` — **환경변수는 여기서만 읽는다** |
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

python -m server.seed                       # 대시보드 계정 생성 (bcrypt)
python -m server.main                       # 대시보드 서버 (http://127.0.0.1:8000)

python -m collector.scheduler --once        # 스케줄러 작업 1회 실행 (검증)
python -m collector.scheduler              # 스케줄러 상주 실행
python -m server.export --days 30          # 단일 HTML 내보내기 → dist/

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
- [ ] **← 현재: 호스팅 선택 후 실제 배포**
      데이터 영속성 때문에 볼륨이 있는 방식만 유효 — `docs/06` 1장 참고
- [ ] 세부 기능: 이동평균·히트맵 토글, CSV 내보내기(FN-264),
      메뉴 상세(SCR-03), 관리자 화면(SCR-05)

## 🔖 다음 세션 시작점 (2026-08-17 중단)

Phase 1 기능은 **전부 동작하는 상태**다. DB에 12개월 실데이터가 들어 있고
API·대시보드·스케줄러가 모두 검증됐다. 남은 것은 **배포**와 **세부 기능**이다.

### 먼저 확인할 것 (재개 시 1분)

```bash
python -m pytest tests/ -q          # 76건 통과해야 정상
python -m collector.main --status   # 2025-08-21 ~ 2026-08-16 / orders 16,000+
python -m server.main               # http://127.0.0.1:8000 로그인 → 대시보드
```

`data/sodam.db`가 없어졌다면 다시 만든다 (약 7분):
```bash
python -m collector.main --init && python -m server.seed
python -m collector.main --backfill
```

### 다음 작업 후보 — 사용자에게 물어볼 것

| # | 작업 | 상태 | 비고 |
|---|---|---|---|
| **1** | **호스팅 선택 후 실제 배포** | 대기 | Fly.io 권장(무료+볼륨). `docs/06` 1장에 A/B/C 비교. 계정 필요 |
| 2 | 화면 피드백 반영 | 사용자가 `dist/*.html` 확인 완료 | 고칠 점을 들으면 반영 |
| 3 | AC-05 / AC-08 눈으로 검증 | 🟡 미검증 | 기간 필터 클릭, 375px 폭 확인 |
| 4 | 이동평균·요일×시간 히트맵 토글 | API(`/api/sales/heatmap`) 이미 있음 | 화면만 붙이면 됨 |
| 5 | CSV 내보내기 (FN-264) | 미착수 | |
| 6 | 메뉴 상세 SCR-03 / 관리자 SCR-05 | API 일부 존재 | `/api/menu/{code}/trend`, `/api/system/collections` |

### 되짚을 필요 없는 것 (이미 해결)

- POS 인증 — `comID`/`memID` 쿠키가 핵심. `auth.create_session()`이 처리
- 인코딩 혼재 — `formats.decode_korean()`이 바이트 런 단위로 처리
- 중첩표 2배 — `parse/tables.py`가 표 선택 + 중복 제거 2겹으로 방어
- 시간대 데이터 — `timeAnal` 수집 불필요. 주문의 `sold_at`에서 유도

## 사용자 확인 필요 (코드로 해결 불가)

- REQ-LEGAL-01 — 탑아이앤티 이용약관의 자동화 접근 조항 확인, 매장주 서면 동의
- NFR-SEC-07 — 공유된 계정 비밀번호 변경 후 `.env`에 반영
- SRS 2.3 1순위 — 탑아이앤티 공식 API 제공 여부 문의
