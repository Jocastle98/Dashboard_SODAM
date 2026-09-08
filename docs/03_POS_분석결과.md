# POS 응답 실측 결과 (STEP 1)

| 항목 | 내용 |
|---|---|
| 상태 | ✅ **완료** — 실제 매출 데이터 확보, 파서 작성 가능 |
| 측정일 | 2026-08-16 |
| 측정 도구 | `collector/probe_topint.py`, `collector/probe_discover.py`, `collector/auth.py` |
| 인증 | **자동 로그인 성공** (`collector/auth.py`) — 수동 쿠키 불필요 |
| 원본 위치 | `data/probe/*.bin` (gitignore — 커밋되지 않음) |

> 이 문서에는 추측을 쓰지 않는다. 실제로 관측한 값만 적는다.

---

## 요약

| # | 확인 항목 | 결과 |
|---|---|---|
| 1 | 응답의 실제 파일 포맷 | ✅ **HTML `<table>`을 엑셀 MIME으로 위장** (진짜 xls 아님) |
| 2 | 기간 조회 동작 | ✅ **기간 내 전체 행 반환** (합계 1행 아님) → 월 단위 12회 요청 |
| 3 | 과거 소급 가능 범위 | ✅ **최소 2년** (2024-08-15 데이터 확인) |
| 4 | 표의 컬럼 구성 | ✅ 3개 리포트 전부 확보 |
| 5 | 메뉴별 / 시간대별 | ✅ **둘 다 확보** — 각각 전용 리포트 존재 |

**SRS 영향:** `ASM-01`(12개월 소급 가정) 성립, `FR-COL-03` 그대로 진행 가능,
`FR-DASH-05`(시간대) / `FR-DASH-06`(메뉴) 모두 데이터 확보.

---

## 1. 인증 구조 — 도메인이 두 개다

```
로그인 포털 : https://topint.co.kr        (utf-8)
리포트 서버 : https://asp.topint.co.kr    (euc-kr)
```

### 로그인 절차 (실측 확정)

```
① GET  https://topint.co.kr/member/login        → hidden 필드(mem_seq, rtn_page) 수집
② POST https://topint.co.kr/act/member/login    → 폼 전송이 아니라 AJAX 엔드포인트
        data: mem_id, mem_pwd, mem_seq, rtn_page
        응답: {"result":true,"message":"","redirectUrl":"https://asp.topint.co.kr/asp_office/asp_main/main.asp"}
③ 이후 asp.topint.co.kr 요청에 쿠키가 자동 전달됨
```

> `<form>`의 action은 비어 있고 JS가 `/act/member/login`으로 보낸다.
> 폼 URL로 POST하면 로그인 페이지가 그대로 되돌아온다 (200이지만 실패).

### 🔴 가장 중요한 발견 — 인증하는 것은 `ASPSESSIONID`가 아니다

로그인 후 설정되는 쿠키 9개 (브라우저 개발자도구 대조 완료):

| 쿠키 | 도메인 | 값(마곡점) | 역할 |
|---|---|---|---|
| `ASPSESSIONID****` | **`asp.topint.co.kr`** | 세션마다 변동 | ASP 세션 — **인증에 불필요** |
| `comID` | `.topint.co.kr` | 회사 코드 | 회사 식별 |
| `comNo` | `.topint.co.kr` | 사업자번호 | |
| `ComName` | `.topint.co.kr` | 회사명 — **euc-kr 바이트** | 표시용 |
| `custCode` | `.topint.co.kr` | 매장 코드 | **매장 식별** |
| `memID` | `.topint.co.kr` | 로그인 ID | 회원 |
| `memSeq` | `.topint.co.kr` | 회원 일련번호 | |
| `grade` | `.topint.co.kr` | 권한 등급 | |
| `menuState` | `.topint.co.kr` | 메뉴 상태 | |

> 실제 값은 `.env`에만 둔다. 이 문서에는 적지 않는다 (CLAUDE.md 보안 규칙).
> 대조에 쓴 개발자도구 캡처는 실제 값이 찍혀 있어 커밋하지 않는다
> (`data/evidence/f12_cookies.png` — gitignore 대상).

> **`ComName`이 개발자도구에서 깨져 보이는 것은 정상이다.**
> 값이 euc-kr 바이트(`\xbc\xd2\xb4\xe3\xc3\xcc ...`)인데 브라우저는 UTF-8로 표시하려 해서
> 그렇다. euc-kr로 디코딩하면 `소담촌 마곡점`이다 (직접 확인).
> `.env`에 넣을 때는 **깨진 그대로** 두어야 원본 바이트가 전송된다. 한글로 고치면 안 된다.

**어느 쿠키가 실제로 필요한지 하나씩 빼면서 실측했다** (정상 = 주문 104 / 시간대 9 / 메뉴 28):

| 보낸 쿠키 | 주문 | 시간대 | 메뉴 | 판정 |
|---|---|---|---|---|
| 9개 전부 | 104 | 9 | 28 | 정상 |
| `ASPSESSIONID` 제외 8개 | 104 | 9 | 28 | 정상 |
| **`comID` 하나만** | **104** | **9** | **28** | **정상 — 핵심 쿠키** |
| `comID` 만 제외 | 4 | 2 | 0 | 실패 |
| **`memID` 만 제외** | 104 | 9 | **161** | 🔴 **전 체인 데이터** |
| `ASPSESSIONID` 하나만 | 4 | 2 | 0 | 실패 |
| `ComName`/`comNo`/`grade`/`menuState`/`custCode`/`memSeq` 각각 제외 | 104 | 9 | 28 | 영향 없음 |

→ **`comID`가 매장을 특정한다.** `ASPSESSIONID`는 인증에 관여하지 않는다.

> 🔴 **가장 위험한 실패 모드: `memID` 누락.**
> 오류가 아니라 **행이 더 많이** 돌아온다 (메뉴 28 → 161). 다른 매장 매출이
> 사장님 대시보드에 섞여도 아무도 알아채지 못한다.
> → 쿠키를 골라 넣지 말 것. `auth._check_cookie_set()`이 `comID`/`memID` 누락 시
>   예외를 던지고, 나머지 신원 쿠키 누락은 경고한다.

`ASPSESSIONID`는 `asp.topint.co.kr` 전용(host-only) 쿠키다. 포털 로그인에서 받은
`topint.co.kr` 소속 `ASPSESSIONID`는 asp 서브도메인 요청에 **전송되지도 않는다.**
그런데도 리포트가 정상 반환되는 것이 위 표의 근거다.

`ASPSESSIONID`만 보냈을 때 나던 오류:

```
개체 이름 '_2026..p_store_order'이(가) 잘못되었습니다.   ← 매장 DB 접두사가 빔
열 이름 'status'이(가) 잘못되었습니다.                    ← 매장 목록 조회 실패
```

리포트 제목도 `매장별매출세부내역 ()` 으로 매장명이 비어 나왔다.

> 브라우저에서 `ASPSESSIONID`만 복사하는 방식은 **작동하지 않는다.**
> `collector/auth.py`의 자동 로그인을 쓰거나, 부득이하면 `Cookie:` 헤더 전체를 넣을 것.

> ⚠ 신원 쿠키는 만료가 `Session`이다(브라우저 종료 시 소멸). 서버 세션 타임아웃과
> 무관하게 오래 유효할 수 있으나, 수집기는 매번 로그인하는 편이 안전하다.

### 매장/브랜드 코드 (로그인 후에만 조회됨)

```
POST /asp_office/common/combo/combo_branchSel_sch.asp
 → [{"gbn":"2","code":"sodam001","name":"마곡점","cd_hdadminbranch":"sodam900"}]

POST /asp_office/common/combo/combo_brandcode_sch.asp
 → [{"code":"00000","name":"소담촌"},{"code":"00002","name":"신사냉삼촌"}]
```

| 값 | 용도 |
|---|---|
| `branch = sodam001` | 마곡점 — `.env`의 `POS_BRANCH` 그대로 |
| `brandcode = 00000` | 소담촌 — ⚠ **리포트에 넘기면 안 된다** (2장 참고) |

### `.env` 에 기록한 실측값

| 키 | 값 | 비고 |
|---|---|---|
| `POS_PORTAL_URL` | `https://topint.co.kr` | 로그인 |
| `POS_BASE_URL` | `https://asp.topint.co.kr` | 리포트 |
| `POS_LANDING_URL` | `.../asp_office/asp_main/main.asp` | 로그인 응답의 `redirectUrl` |
| `POS_BRANCH` | `sodam001` | 마곡점 |
| `POS_STORE_BRANCH_NAME` | `마곡점` | 콤보 응답의 `name` |
| `POS_HQ_BRANCH` | `sodam900` | 콤보 응답의 `cd_hdadminbranch` |
| `POS_BRANDCODE` | `00000` | 소담촌. **기록용** |
| `POS_REPORT_BRANDCODE` | (빈 값) | **요청용. 채우면 리포트가 빈다** |
| `POS_USER_ID` / `POS_USER_PW` | 계정 | 자동 로그인 |
| `POS_SESSION_COOKIE` | 쿠키 9개 전체 | 예비 수단 |
| `BACKFILL_MONTHS` | `12` | 소급 2년 이상 가능하나 기본 12개월 |

`POS_BRANDCODE`와 `POS_REPORT_BRANDCODE`를 나눈 이유:
브랜드 코드 자체는 매장 식별 정보로 남겨둘 가치가 있지만, 리포트 요청에 실으면
`timeAnal`·`menuAnal` 양쪽 모두 `해당되는 기간에 정보가 없습니다`를 반환한다 (둘 다 실측).
한 키로 두면 누군가 "빈 값이 실수"라고 생각해 채워 넣는 순간 조용히 데이터가 사라진다.

두 경로 모두 동작 검증 완료:

| 경로 | 주문 | 시간대 | 메뉴 |
|---|---|---|---|
| 자동 로그인 (`create_session`) | 104행 | 9행 | 28행 |
| 저장된 쿠키 9개 (`cookie_session`) | 104행 | 9행 | 28행 |

---

## 2. 사용할 리포트 3종

메뉴 전체는 `/asp_office/asp_main/main.asp` 에서 확보했다 (`docs/img/menu.png` 대조 완료).

| 대시보드 요구사항 | 화면 | 엑셀 엔드포인트 |
|---|---|---|
| 일별 매출·결제건수·결제수단 | 매장별 매출세부분석 | `sale/agentAnal_com_excel01.asp` |
| 시간대별 매출 (`FR-DASH-05`) | 시간대별 매출현황 | `sale/timeAnal_excel.asp` |
| 메뉴별 매출 (`FR-DASH-06`) | 메뉴별 매출현황 | `sale/menuAnal_sub_1_excel.asp` |

### 2.1 매장별 매출세부분석 — `agentAnal_com_excel01.asp`

```
GET /asp_office/sale/agentAnal_com_excel01.asp
    ?opendate_s=YYYYMMDD&opendate_e=YYYYMMDD&branch=sodam001&branchAddChk=
```

**주문(영수증) 단위** 상세. 컬럼 19개 (POS 원문 그대로):

| # | 컬럼명 | 예시 | 매핑 |
|---|---|---|---|
| 0 | `No.` | `1` | (순번) |
| 1 | `매장명` | `마곡점` | |
| 2 | `주문번호` | `202608150001` | 앞 8자가 영업일자 |
| 3 | `판매시간` | `2026-08-15 11:02` | 시간대 산출 |
| 4 | `결제시간` | `2026-08-15 12:21` | |
| 5 | `총매출액` | `56,700` | `daily_sales.sales_amount` |
| 6 | `할인액` | `0` | `daily_sales.discount_amt` |
| 7 | `순매출액` | `56,700` | |
| 8 | `현금결제` | `56,700` | 결제수단 |
| 9 | `카드결제` | `0` | 결제수단 |
| 10 | `상품권` | `0` | 결제수단 |
| 11 | `포인트` | `0` | 결제수단 |
| 12 | `외상결제` | `0` | 결제수단 |
| 13 | `선수금` | `0` | 결제수단 |
| 14 | `부가세` | `5,154` | |
| 15 | `카드사` | `신한카드` | |
| 16 | `매입사` | `신한카드` | |
| 17 | `승인번호` | `03205041` | ⚠ **저장하지 않을 것** (불필요) |
| 18 | `테이블명` | `20` | 회전율 분석 가능 |

**합계 행이 섞여 있다.** `No.=0`, `결제시간` 칸에 `합계` 문자열이 들어간 행이 데이터 맨 앞에 온다.
파서에서 `No.=0` 행은 제외하거나 검증용으로만 쓴다.

실측값 (2026-08-15):
```
합계: 총매출 3,175,900 / 할인 0 / 순매출 3,175,900
      현금 249,300 / 카드 2,926,600 / 부가세 288,682
주문 50건
```

### 2.2 시간대별 매출현황 — `timeAnal_excel.asp`

```
GET /asp_office/sale/timeAnal_excel.asp
    ?opendate_s=YYYYMMDD&opendate_e=YYYYMMDD&brandcode=&branch=sodam001
```

> ⚠ **`brandcode`는 반드시 빈 값으로 보낼 것.**
> `brandcode=00000`을 넣으면 `해당되는 기간에 정보가 없습니다.` 가 돌아온다.
> `branch`를 비우면 **전 체인 111개 매장 합계**가 나온다 (`매장수` 컬럼으로 확인 가능).

컬럼 6개:

| # | 컬럼명 | 예시 |
|---|---|---|
| 0 | `No.` | `1` |
| 1 | `시간대` | `11:00 ~ 11:59` |
| 2 | `매장수` | `1` ← **1이어야 정상.** 111이면 매장 필터 실패 |
| 3 | `순매출액` | `408,000` |
| 4 | `영수건수` | `7` |
| 5 | `영수단가` | `58,286` |

실측값 (2026-08-15 마곡점): 11시 408,000/7건, 12시 390,000/7건 — 총 9개 시간대 행

### 2.3 메뉴별 매출현황 — `menuAnal_sub_1_excel.asp`

```
GET /asp_office/sale/menuAnal_sub_1_excel.asp
    ?opendate_s=YYYYMMDD&opendate_e=YYYYMMDD&brandcode=&branch=sodam001&bcode=&gcode=
```

컬럼 7개:

| # | 컬럼명 | 예시 | 매핑 |
|---|---|---|---|
| 0 | `순서` | `1` | |
| 1 | `분류명` | `월남쌈샤브샤브` | `menus.category` |
| 2 | `메뉴명` | `월남쌈샤브(120g)` | `menus.menu_name` |
| 3 | `메뉴코드` | `000012` | `menus.menu_code` |
| 4 | `총매출액` | `2,475,900` | `menu_sales.sales_amount` |
| 5 | `일평균매출액` | `2,475,900` | (파생값 — 저장 불필요) |
| 6 | `판매수량` | `131` | `menu_sales.quantity` |

실측값 (2026-08-15 마곡점): 27개 메뉴 행. 단일 매장 계정이라 `branch` 유무와 무관하게 동일 결과.

### 2.4 부가 엔드포인트 (참고)

| 엔드포인트 | 내용 | 컬럼 |
|---|---|---|
| `agentAnal_com_excel02.asp` | 결제 취소내역(결제변경 포함) | 해당일 데이터 없음 |
| `agentAnal_com_excel03.asp` | 주문 취소내역 | `No./매장/구분/주문번호/판매시간/취소시간/품목/수량/금액/취소사유` |
| `dateAnal_excel.asp` | 기간별 매출분석 | ⚠ 파라미터 미해결 — 메뉴 목록이 반환됨 |

`excel03`은 `DQ-01`(취소 건 분류)에 쓸 수 있다. `dateAnal`은 `excel01`로 대체 가능하므로 후순위.

---

## 3. 응답 포맷 ✅

| 항목 | 관측값 |
|---|---|
| `Content-Type` | `application/vnd.ms-excel;charset=euc-kr` |
| `Content-Disposition` | `attachment; filename=매장별매출세부내역(2026-08-16).xls` |
| 파일 시그니처 판별 | **`html`** — OLE2/zip 시그니처 없음 |
| 응답 크기 | 1일 44KB / 7일 178KB |
| 응답 시간 | 0.4 ~ 1.5s |

**CLAUDE.md 함정 2번 확인.** 파서는 **BeautifulSoup**. `pandas.read_excel` 불가.

### 3.1 ⚠ 표 구조 — 중첩 `<table>` 주의

`<table>`이 4~5개이고 **헤더 표가 데이터 표 안에 중첩**되어 있다.
그대로 파싱하면 첫 행이 모든 셀을 이어붙인 문자열 하나로 나온다.

→ **최빈 열 개수(mode)로 진짜 데이터 행만 걸러낸다.**
   `agentAnal`은 19열, `timeAnal`은 6열, `menuAnal`은 7열.

### 3.2 ⚠ 새로 발견된 함정 — 인코딩이 한 문서 안에서 섞인다

문서는 `charset=euc-kr`을 선언하지만 **일부 컬럼명만 UTF-8 바이트**다.

| 컬럼 | 실제 인코딩 | euc-kr로 읽으면 |
|---|---|---|
| `할인액`, `현금결제`, `카드결제` … | euc-kr | 정상 |
| **`총매출액`** | **UTF-8** (`EC B4 9D EB A7 A4 …`) | `珥�留ㅼ�����` |
| **`순매출액`** | **UTF-8** | `���留ㅼ�����` |

- `euc-kr` 전체 디코딩 → position 2664에서 실패
- `utf-8` 전체 디코딩 → position 95에서 실패
- `cp949` 전체 디코딩 → position 2828에서 실패

→ **어떤 단일 인코딩으로도 이 문서를 읽을 수 없다.**
`formats.decode_mixed_korean()` — 바이트 런 단위 디코딩으로 해결.

> ⚠ 시도 순서가 규칙이다. `cp949`는 euc-kr의 상위집합이라 UTF-8 바이트를 **예외 없이**
> 읽어버리고 엉뚱한 한자를 만든다. 반드시 `euc-kr → utf-8 → cp949` 순으로 시도할 것.
> 테스트로 고정: `tests/test_formats.py::test_cp949_must_not_be_tried_before_utf8`

### 3.3 500 응답에도 엑셀 헤더가 붙는다

오류 시에도 `Content-Type: application/vnd.ms-excel`과 `Content-Disposition`이 그대로 온다.
상태코드와 본문을 함께 검사하지 않으면 오류 페이지를 데이터로 착각한다.
→ `probe_observer.find_server_error()`로 본문 내 SQL 오류를 감지한다.

---

## 4. 기간 조회 동작 ✅

| 조회 조건 | 데이터 행 수 |
|---|---|
| 단일일 (20260815) | 50 (+합계 1) |
| 7일 (20260809~20260815) | 226 |
| 1일 (2025-08-15) | 63 |

**기간 내 주문이 전부 반환된다.** 합계 1행만 오는 방식이 아니다.

→ **가이드 분기표: "기간 조회로 여러 행이 나옴" → 초기 12개월 적재를 월 단위 12회 요청으로 처리.**
   365회 순회가 아니라 12회면 된다. 요청 간 1초 대기 유지 시 12초.

> 다만 응답 크기가 7일에 178KB이므로 월 단위는 700KB 내외가 된다.
> 타임아웃 여유를 두고, 실패 시 주 단위로 잘라 재시도하는 편이 안전하다.

---

## 5. 과거 소급 가능 범위 ✅

| 대상일 | 결과 | 합계 매출 |
|---|---|---|
| 2026-08-15 (당일) | ✅ 50건 | 3,175,900 |
| 2025-08-15 (1년 전) | ✅ 63건 | 3,674,000 |
| 2024-08-15 (2년 전) | ✅ 63건 | 3,563,200 |

**최소 2년 소급 가능.** 주문번호 접두사(`202408150001`)로 실제 해당 연도 데이터임을 확인했다.

- SRS `ASM-01`(12개월 소급 가능) — ✅ 성립
- `FR-COL-03`(과거 12개월 일괄 수집) — ✅ 그대로 진행. 2년도 가능
- `AC-03`(최소 3개월 적재) — ✅ 충족

---

## 6. 스키마 영향 (docs/02 6장 대조)

`excel01`은 **주문 단위**다. FS의 `daily_sales`는 일 단위 집계이므로 중간 테이블이 필요하다.

| FS 스키마 | 실측 원천 | 조치 |
|---|---|---|
| `daily_sales.sales_amount` | `excel01.총매출액` 합산 | 집계 |
| `daily_sales.order_count` | `excel01.주문번호` distinct | 집계 |
| `daily_sales.discount_amt` | `excel01.할인액` 합산 | 집계 |
| `daily_sales.cancel_amt` | `excel03` (주문 취소내역) | 별도 수집 |
| `hourly_sales` | **`timeAnal` 직접 제공** | 그대로 적재 |
| `menu_sales` | **`menuAnal` 직접 제공** | 그대로 적재 |
| `menus.category` | `menuAnal.분류명` | ✅ 확보 |
| — | `주문번호/결제수단/테이블명/부가세` | **`orders` 테이블 신설** |

### 제안: `orders` 테이블 신설

```sql
CREATE TABLE orders (
  store_id     INT,
  order_no     VARCHAR(30),     -- 202608150001
  biz_date     DATE,            -- order_no 앞 8자
  sold_at      TIMESTAMP,       -- 판매시간
  paid_at      TIMESTAMP,       -- 결제시간
  total_amt    BIGINT,          -- 총매출액
  discount_amt BIGINT,
  net_amt      BIGINT,          -- 순매출액
  cash_amt     BIGINT, card_amt BIGINT, gift_amt BIGINT,
  point_amt    BIGINT, credit_amt BIGINT, prepaid_amt BIGINT,
  vat_amt      BIGINT,
  card_issuer  VARCHAR(50),     -- 카드사
  card_acquirer VARCHAR(50),    -- 매입사
  table_name   VARCHAR(20),
  PRIMARY KEY (store_id, order_no)
);
```

`daily_sales`는 이 테이블에서 집계한다 (`FN-607` 원본 보존 + 재집계 동시 해결).
`승인번호`는 저장하지 않는다 — 대시보드에 불필요하고 카드 거래 식별자에 해당한다.

**FS 6장 스키마 수정은 STEP 3 착수 시 확정한다.**

---

## 7. 데이터 품질 확인 필요 (STEP 3에서)

| 규칙 | 확인 방법 | 상태 |
|---|---|---|
| `DQ-01` 음수 = 취소 | `excel01`에 음수 행이 있는지 | 미확인 |
| `DQ-02` 휴무일 구분 | 조회 결과가 0건인 날 | 미확인 |
| `DQ-03` 일별 합계 ↔ 메뉴별 합계 오차 1% | `excel01` 합계 vs `menuAnal` 합계 | 미확인 |
| 숫자 표기 | 콤마 있음 (`3,175,900`) 확인 | ✅ |
| 날짜 표기 | `2026-08-15 11:02` (공백 구분) | ✅ |

---

## 8. 다음 단계

STEP 1 종료. **STEP 3(스키마 + 파서 + 적재)로 진행 가능.**

| 순서 | 작업 |
|---|---|
| 1 | `db/schema.sql` — `orders` 추가한 스키마 확정 |
| 2 | `collector/parse.py` — 리포트 3종 파서 (중첩 표·혼재 인코딩 처리) |
| 3 | `collector/load.py` — UPSERT 적재 |
| 4 | `collector/main.py` — 기간 인자 진입점 |
| 5 | 최근 7일 검증 → 통과 시 과거 12~24개월 적재 |

### 사용자 확인 필요 (코드로 해결 불가)

| # | 내용 | 영향 |
|---|---|---|
| 1 | REQ-LEGAL-01 — 이용약관 자동화 접근 조항 확인, 매장주 서면 동의 | 프로젝트 적법성 |
| 2 | NFR-SEC-07 — 공유 계정 비밀번호 변경 후 `.env` 반영 | 보안 |
| 3 | SRS 2.3 1순위 — 탑아이앤티 공식 API 제공 여부 문의 | 수집 방식 |

---

*이 문서는 진행하며 계속 갱신한다. 새로 알아낸 POS 동작은 즉시 여기에 기록할 것.*
