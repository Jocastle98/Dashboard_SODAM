/** 시간대별 매출 (FN-240). 데이터가 없으면 위젯을 숨긴다 (TC-13). */

import { api } from '../api.js';
import { hourlyChart } from '../charts.js';
import { createWidget } from './widget.js';

export function hourlyWidget() {
  return createWidget({
    root: 'hourly',
    load: (period) => api.hourly(period),
    render: (data) => {
      hourlyChart('hourly-chart', data.data, data.peakHours);
      const hint = document.querySelector('#hourly .hint');
      if (hint && data.peakHours.length) {
        hint.textContent = `피크타임 ${data.peakHours.map((h) => `${h}시`).join(', ')}`;
      }
    },
    isEmpty: (data) => !data.available,
  });
}
