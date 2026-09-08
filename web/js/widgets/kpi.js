/** KPI 카드 4종 (FN-210). */

import { api } from '../api.js';
import { COUNT, WON, delta, shortWon, stamp } from '../format.js';
import { createWidget } from './widget.js';

const CARDS = [
  { key: 'totalSales', label: '총 매출', render: shortWon, exact: WON },
  { key: 'orderCount', label: '결제건수', render: COUNT },
  { key: 'avgTicket', label: '객단가', render: WON },
  { key: 'dailyAvg', label: '일평균 매출', render: shortWon, exact: WON },
];

export function kpiWidget() {
  return createWidget({
    root: 'kpi',
    load: (period) => api.summary(period),
    render: (data) => {
      const body = document.querySelector('#kpi [data-body]');
      body.innerHTML = CARDS.map((card) => {
        const value = data.current[card.key];
        const change = delta(data.change[card.key]);
        const exact = card.exact ? card.exact(value) : '';
        return `
          <div class="kpi">
            <div class="label">${card.label}</div>
            <div class="value" title="${exact}">${card.render(value)}</div>
            <div class="delta ${change.cls}">${change.text}</div>
          </div>`;
      }).join('');

      const meta = document.getElementById('period-meta');
      if (meta) {
        meta.textContent =
          `${data.period.from} ~ ${data.period.to} · 영업일 ${data.period.businessDays}일`;
      }
      const updated = document.getElementById('last-updated');
      if (updated) updated.textContent = `최종 갱신 ${stamp(data.lastUpdated)}`;
    },
    isEmpty: (data) => !data.current.orderCount,
  });
}
