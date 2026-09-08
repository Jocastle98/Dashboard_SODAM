/** 요일별 평균 매출 (FN-230). */

import { api } from '../api.js';
import { weekdayChart } from '../charts.js';
import { createWidget } from './widget.js';

export function weekdayWidget() {
  return createWidget({
    root: 'weekday',
    load: (period) => api.weekday(period),
    render: (data) => weekdayChart('weekday-chart', data.data),
    isEmpty: (data) => data.data.every((row) => !row.avgSales),
  });
}
