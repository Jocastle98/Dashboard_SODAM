/**
 * API 호출 래퍼.
 *
 * 여기서만 fetch를 쓴다. 401 처리(FN-263)와 오류 메시지 해석을 한 곳에 모으기 위함이다.
 *
 * 요청 대상은 자기 자신(백엔드)뿐이다. POS에는 직접 요청하지 않으며,
 * 프론트엔드 번들에 POS 주소나 계정이 실려서도 안 된다 (NFR-SEC-03 / TC-18).
 * 이 규칙은 tests/test_api.py 가 검사한다.
 */

const BASE = '';

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(BASE + path, {
      credentials: 'same-origin',           // HttpOnly 세션 쿠키 전달
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
  } catch {
    throw new ApiError(0, 'NETWORK', '서버에 연결하지 못했습니다.');
  }

  let body = null;
  try { body = await response.json(); } catch { /* 본문 없는 응답 */ }

  if (!response.ok) {
    const error = body?.error ?? {};
    throw new ApiError(response.status, error.code ?? 'ERROR',
      error.message ?? '일시적인 오류가 발생했습니다.');
  }
  return body;
}

const query = ({ from, to, ...rest }) =>
  new URLSearchParams({ from, to, ...rest }).toString();

export const api = {
  login: (username, password, remember) =>
    request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password, remember }),
    }),

  logout: () => request('/api/auth/logout', { method: 'POST' }),
  session: () => request('/api/auth/session'),

  summary: (p) => request(`/api/summary?${query(p)}`),
  daily: (p) => request(`/api/sales/daily?${query(p)}`),
  weekday: (p) => request(`/api/sales/weekday?${query(p)}`),
  weeklyCompare: (p) => request(`/api/sales/weekly-compare?${query(p)}`),
  hourly: (p) => request(`/api/sales/hourly?${query(p)}`),
  heatmap: (p) => request(`/api/sales/heatmap?${query(p)}`),
  menuRanking: (p, limit = 10, sortBy = 'sales') =>
    request(`/api/menu/ranking?${query({ ...p, limit, sortBy })}`),
  menuTrend: (code, p) => request(`/api/menu/${encodeURIComponent(code)}/trend?${query(p)}`),
  status: () => request('/api/system/status'),

  // 수동 수집 (FN-205) — POS에 직접 가지 않는다. 백엔드가 대신 판단하고 실행한다.
  collectStatus: () => request('/api/system/collect/status'),
  collectNow: () => request('/api/system/collect', { method: 'POST' }),
};

/** 세션이 끊기면 로그인 화면으로 (FN-263). */
export function redirectOnUnauthorized(error) {
  if (error instanceof ApiError && error.status === 401) {
    location.href = '/';
    return true;
  }
  return false;
}
