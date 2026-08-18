/**
 * Chart.js 래퍼 — 공통 옵션과 색상을 여기 한 곳에 둔다.
 * 위젯은 데이터만 넘기고 스타일은 신경 쓰지 않는다.
 */

import { axisWon, WON, COUNT } from './format.js';

export const COLORS = {
  primary: '#C8102E',
  primarySoft: 'rgba(200,16,46,.12)',
  secondary: '#2D3E50',
  muted: '#ADB5BD',
  grid: '#F1F3F5',
};

const charts = new Map();

/** 같은 캔버스에 다시 그릴 때 이전 차트를 파기한다 (기간 필터 변경 시). */
function mount(canvasId, config) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;
  charts.get(canvasId)?.destroy();
  const chart = new Chart(canvas, config);
  charts.set(canvasId, chart);
  return chart;
}

const baseOptions = (tooltipLabel) => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: 'rgba(45,62,80,.95)',
      padding: 10,
      titleFont: { size: 12 },
      bodyFont: { size: 12 },
      callbacks: tooltipLabel ? { label: tooltipLabel } : {},
    },
  },
  scales: {
    x: { grid: { display: false }, ticks: { font: { size: 11 }, maxRotation: 0 } },
    y: {
      beginAtZero: true,
      grid: { color: COLORS.grid },
      ticks: { font: { size: 11 }, callback: (v) => axisWon(v) },
    },
  },
});

/** 일별 매출 추이 (FN-220). 7일 이하는 막대, 그 이상은 선. */
export function dailyChart(canvasId, rows) {
  const labels = rows.map((r) => r.label);
  const values = rows.map((r) => r.sales);
  const useBar = rows.length <= 7;
  const average = values.filter((v) => v != null);
  const mean = average.length ? average.reduce((a, b) => a + b, 0) / average.length : 0;

  return mount(canvasId, {
    type: useBar ? 'bar' : 'line',
    data: {
      labels,
      datasets: [
        {
          data: values,
          borderColor: COLORS.primary,
          backgroundColor: useBar ? COLORS.primary : COLORS.primarySoft,
          borderWidth: 2,
          fill: !useBar,
          tension: .3,
          pointRadius: rows.length > 60 ? 0 : 2,
          spanGaps: false,          // 미수집일은 선을 끊는다 (FN-220)
          borderRadius: 4,
        },
        {
          data: values.map(() => mean),          // 기간 평균 보조선
          borderColor: COLORS.muted,
          borderDash: [4, 4],
          borderWidth: 1,
          pointRadius: 0,
          fill: false,
          type: 'line',
        },
      ],
    },
    options: baseOptions((ctx) => {
      if (ctx.datasetIndex === 1) return `기간 평균 ${WON(Math.round(mean))}`;
      const row = rows[ctx.dataIndex];
      if (row.isClosed) return '휴무';
      if (row.sales == null) return '미수집';
      return [`매출 ${WON(row.sales)}`, `결제 ${COUNT(row.orders)}`,
              `객단가 ${WON(row.avgTicket)}`];
    }),
  });
}

/** 요일별 평균 매출 (FN-230). 최고 요일을 강조한다. */
export function weekdayChart(canvasId, rows) {
  const values = rows.map((r) => r.avgSales ?? 0);
  const peak = Math.max(...values);

  return mount(canvasId, {
    type: 'bar',
    data: {
      labels: rows.map((r) => r.dayOfWeek),
      datasets: [{
        data: values,
        backgroundColor: values.map((v) => (v === peak && v > 0 ? COLORS.primary : '#FFC9C9')),
        borderRadius: 5,
      }],
    },
    options: baseOptions((ctx) => {
      const row = rows[ctx.dataIndex];
      return [`평균 ${WON(row.avgSales)}`, `평균 ${COUNT(row.avgOrders)}`,
              `표본 ${row.sampleDays}일`];
    }),
  });
}

/** 시간대별 매출 (FN-240). 피크 시간대를 강조한다. */
export function hourlyChart(canvasId, rows, peakHours = []) {
  return mount(canvasId, {
    type: 'bar',
    data: {
      labels: rows.map((r) => `${r.hour}시`),
      datasets: [{
        data: rows.map((r) => r.sales),
        backgroundColor: rows.map((r) => (peakHours.includes(r.hour) ? COLORS.primary : '#FFC9C9')),
        borderRadius: 5,
      }],
    },
    options: baseOptions((ctx) => {
      const row = rows[ctx.dataIndex];
      return [`매출 ${WON(row.sales)}`, `결제 ${COUNT(row.orders)}`];
    }),
  });
}

export function destroyAll() {
  charts.forEach((chart) => chart.destroy());
  charts.clear();
}
