/**
 * 숫자·날짜 표기 규칙 (docs/02 8.4).
 * 화면 어디서든 같은 규칙을 쓰도록 여기 한 곳에 둔다.
 */

export const WON = (n) => (n == null ? '—' : `${n.toLocaleString('ko-KR')}원`);

/**
 * 금액 표기 — 말로 읽는 단위 (docs/02 8.4). 숫자 자릿수를 세지 않고 바로 읽히게 한다 (사용자 요청).
 * 1천만원 이상은 백만원 단위로 반올림한다. 정확한 값은 툴팁(title)에 둔다.
 *   1,116,960,000원 → 11억 1천7백만원 / 1,000,000,000원 → 10억원
 *      63,220,000원 → 6천3백만원     /     3,456,000원 → 346만원
 */
export function shortWon(n) {
  if (n == null) return '—';
  const sign = n < 0 ? '-' : '';
  const abs = Math.abs(n);
  const millions = Math.round(abs / 1_000_000);
  if (millions >= 10) {
    const eok = Math.floor(millions / 100);
    const cheon = Math.floor((millions % 100) / 10);
    const baek = millions % 10;
    const man = `${cheon ? `${cheon}천` : ''}${baek ? `${baek}백` : ''}`;
    if (!man) return `${sign}${eok}억원`;
    return `${sign}${eok ? `${eok}억 ` : ''}${man}만원`;
  }
  if (abs >= 10_000) return `${sign}${Math.round(abs / 10_000).toLocaleString('ko-KR')}만원`;
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
