/** 일별 매출 추이 (FN-220). */

import { api } from '../api.js';
import { dailyChart } from '../charts.js';
import { shortDate } from '../format.js';
import { createWidget } from './widget.js';

export function dailyWidget() {
  return createWidget({
    root: 'daily',
    load: (period) => api.daily(period),
    render: (data) => {
      const rows = data.data.map((row) => ({
        label: shortDate(row.date),
        sales: row.sales,           // null 이면 선이 끊긴다 (미수집/휴무)
        orders: row.orders,
        avgTicket: row.avgTicket,
        isClosed: row.isClosed,
      }));
      dailyChart('daily-chart', rows);

      const closed = data.data.filter((row) => row.isClosed).length;
      const missing = data.data.filter((row) => row.sales == null && !row.isClosed).length;
      const hint = document.querySelector('#daily .hint');
      if (hint) {
        const notes = [];
        if (closed) notes.push(`휴무 ${closed}일`);
        if (missing) notes.push(`미수집 ${missing}일`);
        hint.textContent = notes.join(' · ');
      }
    },
    isEmpty: (data) => data.data.every((row) => row.sales == null),
  });
}
