/**
 * 연도별 매출 (FN-236). 기간 필터와 무관하게 **마감된 해만** 그린다.
 * 진행 중인 해는 이듬해 첫 수집 때 서버가 isComplete 로 바꿔 주므로 손댈 것이 없다.
 */

import { api } from '../api.js';
import { yearlyChart } from '../charts.js';
import { createWidget } from './widget.js';

const completedYears = (data) => data.data.filter((row) => row.isComplete && row.sales);

export function yearlyWidget() {
  return createWidget({
    root: 'yearly',
    load: () => api.yearly(),
    render: (data) => {
      const rows = completedYears(data);
      yearlyChart('yearly-chart', rows);
      const hint = document.querySelector('#yearly .hint');
      const ongoing = data.data.find((row) => !row.isComplete);
      if (hint) {
        hint.textContent = `${rows[0].year}~${rows[rows.length - 1].year}년`
          + (ongoing ? ` · ${ongoing.year}년은 연말 마감 후 추가` : '');
      }
    },
    isEmpty: (data) => completedYears(data).length === 0,
    emptyMessage: '마감된 연도의 매출 데이터가 없습니다.',
  });
}
