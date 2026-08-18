-- 소담촌 마곡점 매출 대시보드 — DB 스키마
-- 설계 근거: docs/05_DB스키마_확정안.md (docs/03 실측 결과 기반)
--
-- SQLite 방언. PostgreSQL 이식 시 바꿀 것:
--   INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL
--   TEXT(ISO8601 시각)                → TIMESTAMPTZ
--   INTEGER(0/1)                      → BOOLEAN
--   datetime('now')                   → NOW()

PRAGMA foreign_keys = ON;

-- ── 매장 ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stores (
  store_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  store_code    TEXT    NOT NULL UNIQUE,   -- 'SODAM_MAGOK'
  store_name    TEXT    NOT NULL,          -- '소담촌 마곡점'
  pos_branch    TEXT    NOT NULL,          -- 'sodam001' — POS 조회 키
  pos_brandcode TEXT,                      -- '00000' — 기록용. 요청에는 쓰지 않는다
  open_hour     INTEGER DEFAULT 11,
  close_hour    INTEGER DEFAULT 22,
  created_at    TEXT    DEFAULT (datetime('now'))
);

-- ── 대시보드 사용자 (POS 계정과 분리, FR-AUTH-03/04) ───
CREATE TABLE IF NOT EXISTS users (
  user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id      INTEGER NOT NULL REFERENCES stores(store_id),
  username      TEXT    NOT NULL UNIQUE,
  password_hash TEXT    NOT NULL,          -- bcrypt
  role          TEXT    DEFAULT 'owner',   -- owner | manager | admin
  last_login_at TEXT,
  created_at    TEXT    DEFAULT (datetime('now'))
);

-- ── 주문(영수증) 단위 원본 ─────────────────────────────
-- POS가 일별 집계가 아니라 주문 단위로 준다. 모든 집계의 원천이다.
-- PRIMARY KEY가 FR-COL-05 / FN-604 멱등성을 보장한다.
CREATE TABLE IF NOT EXISTS orders (
  store_id      INTEGER NOT NULL REFERENCES stores(store_id),
  order_no      TEXT    NOT NULL,            -- '202608150001'
  biz_date      TEXT    NOT NULL,            -- '2026-08-15' (order_no 앞 8자)
  sold_at       TEXT    NOT NULL,            -- '2026-08-15 11:02'
  paid_at       TEXT,
  total_amt     INTEGER NOT NULL DEFAULT 0,
  discount_amt  INTEGER NOT NULL DEFAULT 0,
  net_amt       INTEGER NOT NULL DEFAULT 0,
  vat_amt       INTEGER NOT NULL DEFAULT 0,
  cash_amt      INTEGER NOT NULL DEFAULT 0,
  card_amt      INTEGER NOT NULL DEFAULT 0,
  gift_amt      INTEGER NOT NULL DEFAULT 0,  -- 상품권
  point_amt     INTEGER NOT NULL DEFAULT 0,
  credit_amt    INTEGER NOT NULL DEFAULT 0,  -- 외상결제
  prepaid_amt   INTEGER NOT NULL DEFAULT 0,  -- 선수금
  card_issuer   TEXT,
  card_acquirer TEXT,
  table_name    TEXT,
  collected_at  TEXT    DEFAULT (datetime('now')),
  PRIMARY KEY (store_id, order_no)
);
-- 승인번호는 저장하지 않는다 (SRS 6.3 개인정보 미수집, 대시보드에 불필요)

CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(store_id, biz_date DESC);
CREATE INDEX IF NOT EXISTS idx_orders_sold ON orders(store_id, sold_at);

-- ── 일별 집계 (orders에서 파생) ────────────────────────
CREATE TABLE IF NOT EXISTS daily_sales (
  store_id      INTEGER NOT NULL REFERENCES stores(store_id),
  biz_date      TEXT    NOT NULL,
  sales_amount  INTEGER,
  order_count   INTEGER,
  discount_amt  INTEGER DEFAULT 0,
  cancel_amt    INTEGER DEFAULT 0,
  vat_amt       INTEGER DEFAULT 0,
  cash_amt      INTEGER DEFAULT 0,
  card_amt      INTEGER DEFAULT 0,
  etc_amt       INTEGER DEFAULT 0,        -- 상품권+포인트+외상+선수금
  is_closed     INTEGER DEFAULT 0,        -- DQ-02. 수집 성공 + 주문 0건 → 1
  updated_at    TEXT    DEFAULT (datetime('now')),
  PRIMARY KEY (store_id, biz_date)
);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_sales(store_id, biz_date DESC);

-- ── 시간대별 (orders.sold_at에서 유도) ─────────────────
-- timeAnal 리포트를 수집하지 않는다. 주문에서 유도한 값이 실측과 완전 일치했다.
CREATE TABLE IF NOT EXISTS hourly_sales (
  store_id      INTEGER NOT NULL REFERENCES stores(store_id),
  biz_date      TEXT    NOT NULL,
  hour          INTEGER NOT NULL CHECK (hour BETWEEN 0 AND 23),
  sales_amount  INTEGER,
  order_count   INTEGER,
  PRIMARY KEY (store_id, biz_date, hour)
);
CREATE INDEX IF NOT EXISTS idx_hourly_date ON hourly_sales(store_id, biz_date DESC);

-- ── 메뉴 ──────────────────────────────────────────────
-- menu_code는 TEXT. '000012'를 정수로 바꾸면 앞의 0이 날아간다.
CREATE TABLE IF NOT EXISTS menus (
  menu_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id    INTEGER NOT NULL REFERENCES stores(store_id),
  menu_code   TEXT    NOT NULL,
  menu_name   TEXT    NOT NULL,
  category    TEXT,                       -- POS 분류명
  first_seen  TEXT    DEFAULT (datetime('now')),
  last_seen   TEXT,
  is_active   INTEGER DEFAULT 1,
  UNIQUE (store_id, menu_code)
);

CREATE TABLE IF NOT EXISTS menu_sales (
  store_id     INTEGER NOT NULL REFERENCES stores(store_id),
  biz_date     TEXT    NOT NULL,
  menu_id      INTEGER NOT NULL REFERENCES menus(menu_id),
  quantity     INTEGER,
  sales_amount INTEGER,
  PRIMARY KEY (store_id, biz_date, menu_id)
);
CREATE INDEX IF NOT EXISTS idx_menu_date ON menu_sales(store_id, biz_date DESC);

-- ── 취소 내역 (DQ-01) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS order_cancels (
  store_id     INTEGER NOT NULL REFERENCES stores(store_id),
  biz_date     TEXT    NOT NULL,
  order_no     TEXT    NOT NULL,          -- 주문 리포트 형식으로 정규화됨
  seq          INTEGER NOT NULL,          -- 한 주문에 여러 품목
  cancel_type  TEXT,                      -- '전체취소'
  sold_at      TEXT,                      -- 취소 리포트는 시각만 준다
  canceled_at  TEXT,
  item_name    TEXT,
  quantity     INTEGER,
  amount       INTEGER,
  reason       TEXT,
  PRIMARY KEY (store_id, biz_date, order_no, seq)
);
CREATE INDEX IF NOT EXISTS idx_cancels_date ON order_cancels(store_id, biz_date DESC);

-- ── 수집 이력 (FR-COL-06 / FN-501) ─────────────────────
-- is_closed 판정의 근거이기도 하다.
CREATE TABLE IF NOT EXISTS collection_logs (
  log_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id      INTEGER REFERENCES stores(store_id),
  report_type   TEXT,                     -- orders | menu | cancels
  started_at    TEXT,
  finished_at   TEXT,
  target_from   TEXT,
  target_to     TEXT,
  status        TEXT,                     -- success | partial | failed
  record_count  INTEGER,
  error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_logs_recent ON collection_logs(store_id, started_at DESC);

-- ── 원본 보존 (FN-607) ─────────────────────────────────
-- 응답이 HTML이고 월 700KB에 이르므로 DB에 넣지 않는다.
-- 파일로 두고 경로와 해시만 남긴다. data/ 는 gitignore 대상.
CREATE TABLE IF NOT EXISTS raw_files (
  raw_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id     INTEGER REFERENCES stores(store_id),
  report_type  TEXT,
  target_from  TEXT,
  target_to    TEXT,
  file_path    TEXT,
  byte_size    INTEGER,
  sha256       TEXT,
  collected_at TEXT DEFAULT (datetime('now'))
);
