/** 메뉴별 매출 TOP (FN-250). */

import { api } from '../api.js';
import { QTY, shortWon } from '../format.js';
import { createWidget } from './widget.js';

let sortBy = 'sales';

export function menuWidget() {
  const widget = createWidget({
    root: 'menu',
    load: (period) => api.menuRanking(period, 10, sortBy),
    render: (data) => {
      const body = document.querySelector('#menu [data-body]');
      const max = Math.max(...data.data.map((row) => row.sales), 1);
      body.innerHTML = `<div class="menu-list">${data.data.map((row) => `
        <div class="menu-row">
          <div class="menu-rank">${row.rank}</div>
          <div>
            <div class="menu-name">${escapeHtml(row.menuName)}<span class="grade ${row.abcGrade}">${row.abcGrade}</span></div>
            <div class="menu-meta">${escapeHtml(row.category ?? '')} · ${QTY(row.quantity)} · ${row.share}%</div>
            <div class="menu-bar"><span style="width:${(row.sales / max * 100).toFixed(1)}%"></span></div>
          </div>
          <div class="menu-amount">${shortWon(row.sales)}</div>
        </div>`).join('')}</div>`;
    },
    isEmpty: (data) => !data.data.length,
  });

  document.querySelectorAll('#menu [data-sort]').forEach((button) => {
    button.addEventListener('click', () => {
      sortBy = button.dataset.sort;
      document.querySelectorAll('#menu [data-sort]').forEach((b) => b.classList.toggle('active', b === button));
      widget.refresh(currentPeriod);
    });
  });

  let currentPeriod = null;
  return {
    refresh: (period) => { currentPeriod = period; return widget.refresh(period); },
  };
}

/** 메뉴명은 POS에서 온 문자열이다 — 그대로 innerHTML에 넣지 않는다 (NFR-SEC-05). */
function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
