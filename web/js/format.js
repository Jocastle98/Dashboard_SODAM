/**
 * 숫자·날짜 표기 규칙 (docs/02 8.4).
 * 화면 어디서든 같은 규칙을 쓰도록 여기 한 곳에 둔다.
 */

export const WON = (n) => (n == null ? '—' : `${n.toLocaleString('ko-KR')}원`);

/** 축약 표기: 12,340,000원 → 1,234만원 */
export function shortWon(n) {
  if (n == null) return '—';
  if (Math.abs(n) >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억원`;
  if (Math.abs(n) >= 10_000) return `${Math.round(n / 10_000).toLocaleString('ko-KR')}만원`;
  return WON(n);
}

/** 축 눈금용 — 단위 없이 짧게 */
export function axisWon(n) {
  if (Math.abs(n) >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억`;
  if (Math.abs(n) >= 10_000) return `${Math.round(n / 10_000).toLocaleString('ko-KR')}만`;
  return n.toLocaleString('ko-KR');
}

export const COUNT = (n) => (n == null ? '—' : `${n.toLocaleString('ko-KR')}건`);
export const QTY = (n) => (n == null ? '—' : `${n.toLocaleString('ko-KR')}개`);

/**
 * 증감 표기 — 색상과 화살표를 함께 쓴다.
 * 색만으로 구분하면 색맹 사용자가 읽을 수 없다 (NFR-USE-04).
 */
export function delta(rate) {
  if (rate == null) return { text: '비교 데이터 없음', cls: 'flat' };
  if (rate > 0) return { text: `▲ ${rate.toFixed(1)}%`, cls: 'up' };
  if (rate < 0) return { text: `▼ ${Math.abs(rate).toFixed(1)}%`, cls: 'down' };
  return { text: '— 0.0%', cls: 'flat' };
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

/** '2026-08-15' → '08/15' */
export const shortDate = (iso) => iso.slice(5).replace('-', '/');

/** '2026-08-15' → '2026-08-15 (금)' */
export function longDate(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return `${iso} (${WEEKDAYS[d.getDay()]})`;
}

/** ISO 타임스탬프 → '08-17 00:09' */
export function stamp(iso) {
  if (!iso) return '기록 없음';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 11 → '11시' */
export const hourLabel = (h) => `${h}시`;
