/**
 * 위젯 공통 골격.
 *
 * FN-260 — 위젯별로 개별 로딩한다. 하나가 느려도 전체가 막히지 않는다.
 * FN-261 — 실패한 위젯만 "다시 시도"를 보여준다.
 * FN-262 — 데이터가 없으면 빈 상태 문구를 보여준다.
 */

import { redirectOnUnauthorized } from '../api.js';

export function createWidget({ root, load, render, isEmpty }) {
  const element = document.getElementById(root);
  if (!element) return { refresh: async () => {} };

  const body = element.querySelector('[data-body]');
  const state = element.querySelector('[data-state]');

  function show(mode, message = '') {
    if (mode === 'ready') {
      body.classList.remove('hidden');
      state.classList.add('hidden');
      return;
    }
    body.classList.add('hidden');
    state.classList.remove('hidden');
    state.innerHTML = mode === 'loading'
      ? '<div class="skeleton" style="height:200px"></div>'
      : `<div>${message}</div>${mode === 'error' ? '<button data-retry>다시 시도</button>' : ''}`;
    if (mode === 'error') {
      state.querySelector('[data-retry]').addEventListener('click', () => refresh(lastPeriod));
    }
  }

  let lastPeriod = null;

  async function refresh(period) {
    lastPeriod = period;
    show('loading');
    try {
      const data = await load(period);
      if (isEmpty && isEmpty(data)) {
        show('empty', '선택한 기간에 데이터가 없습니다.');
        return;
      }
      render(data, period);
      show('ready');
    } catch (error) {
      if (redirectOnUnauthorized(error)) return;
      show('error', error.message ?? '데이터를 불러오지 못했습니다.');
    }
  }

  return { refresh };
}
