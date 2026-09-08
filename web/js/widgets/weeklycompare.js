/**
 * 요일별 이번 주 vs 지난 주 (FN-235 / FR-DASH-13).
 *
 * "지난주 수요일보다 올랐나?" 를 한 눈에 보기 위한 표다.
 * 어느 수요일인지 헷갈리지 않게 칸마다 날짜를 함께 찍는다.
 */

import { api } from '../api.js';
import { WON, delta, shortDate, shortWon } from '../format.js';
import { createWidget } from './widget.js';

// 함수 이름에 compare 접두사를 붙인다 — 단일 HTML 내보내기가 모듈을 한 스코프로 합친다.

export function weeklyCompareWidget() {
  return createWidget({
    root: 'weekly-compare',
    load: (period) => api.weeklyCompare(period),
    render: (data) => {
      const body = document.querySelector('#weekly-compare [data-body]');
      const hint = document.querySelector('#weekly-compare .hint');
      if (hint) {
        hint.textContent =
          `${shortDate(data.lastWeek.from)}~${shortDate(data.lastWeek.to)} → ` +
          `${shortDate(data.thisWeek.from)}~${shortDate(data.thisWeek.to)}`;
      }

      const total = delta(data.total.change);
      body.innerHTML = `
        <div class="table-scroll">
          <table class="cmp">
            <thead>
              <tr><th>요일</th><th>지난주</th><th>이번주</th><th>증감</th></tr>
            </thead>
            <tbody>${data.data.map(compareRow).join('')}</tbody>
            <tfoot>
              <tr>
                <th>합계</th>
                <td>${compareCell(data.total.lastWeekSales)}</td>
                <td>${compareCell(data.total.thisWeekSales)}</td>
                <td class="delta ${total.cls}">${total.text}</td>
              </tr>
            </tfoot>
          </table>
        </div>
        <p class="hint cmp-note">합계는 양쪽 다 매출이 있는 ${data.total.pairedDays}개 요일만 더한 값입니다.</p>`;
    },
    // 지난주 값이라도 있으면 표를 그린다 — 이번주 칸만 '—'로 두는 편이 정보가 많다
    isEmpty: (data) => data.data.every(
      (row) => row.thisWeek.sales == null && row.lastWeek.sales == null),
  });
}

function compareRow(item) {
  const change = delta(item.change);
  return `
    <tr>
      <th>${item.dayOfWeek}</th>
      <td>${compareDayCell(item.lastWeek)}</td>
      <td>${compareDayCell(item.thisWeek)}</td>
      <td class="delta ${change.cls}">${item.change == null ? '—' : change.text}</td>
    </tr>`;
}

/** 휴무와 미수집을 구분해서 보여준다 — 0원으로 오해하면 안 된다 (FR-DASH-12). */
function compareDayCell(block) {
  const label = block.sales == null
    ? `<span class="cmp-none">${block.isClosed ? '휴무' : '—'}</span>`
    : `<span class="cmp-amt" title="${WON(block.sales)}">${shortWon(block.sales)}</span>`;
  return `${label}<span class="cmp-date">${shortDate(block.date)}</span>`;
}

function compareCell(value) {
  return `<span class="cmp-amt" title="${WON(value)}">${shortWon(value)}</span>`;
}
