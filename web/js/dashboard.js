/**
 * 대시보드 조율 — 기간 필터를 바꾸면 모든 위젯을 함께 갱신한다 (FN-201).
 * 위젯 자체의 로직은 각 widgets/ 모듈에 있다. 여기엔 두지 않는다.
 */

import { api, redirectOnUnauthorized } from './api.js';
import { stamp } from './format.js';
import { dailyWidget } from './widgets/daily.js';
import { hourlyWidget } from './widgets/hourly.js';
import { kpiWidget } from './widgets/kpi.js';
import { menuWidget } from './widgets/menu.js';
import { weekdayWidget } from './widgets/weekday.js';

const iso = (date) => date.toISOString().slice(0, 10);
const shift = (date, days) => new Date(date.getTime() + days * 86_400_000);

/** 어제까지를 기준으로 삼는다 — 오늘 데이터는 마감 전이라 아직 없다. */
function presetPeriod(preset) {
  const yesterday = shift(new Date(), -1);
  switch (preset) {
    case 'today':  return { from: iso(yesterday), to: iso(yesterday) };
    case 'week':   return { from: iso(shift(yesterday, -6)), to: iso(yesterday) };
    case 'month':  return { from: iso(shift(yesterday, -29)), to: iso(yesterday) };
    case 'mtd': {
      const first = new Date(yesterday.getFullYear(), yesterday.getMonth(), 1);
      return { from: iso(first), to: iso(yesterday) };
    }
    default:       return { from: iso(shift(yesterday, -6)), to: iso(yesterday) };
  }
}

const widgets = [kpiWidget(), dailyWidget(), weekdayWidget(), hourlyWidget(), menuWidget()];

function refreshAll(period) {
  // 개별 호출로 띄운다 — 하나가 느려도 나머지가 먼저 그려진다 (FN-260)
  widgets.forEach((widget) => widget.refresh(period));
}

async function paintStatusBadge() {
  try {
    const data = await api.status();
    const badge = document.getElementById('status-badge');
    const labels = { ok: '정상', delayed: '지연', failed: '수집 실패' };
    badge.className = `badge ${data.status}`;
    badge.querySelector('[data-text]').textContent =
      `${labels[data.status] ?? data.status} · ${stamp(data.lastCollectedAt)}`;
    const range = document.getElementById('data-range');
    if (range && data.dataRange.from) {
      range.textContent = `보유 데이터 ${data.dataRange.from} ~ ${data.dataRange.to}`;
    }
  } catch (error) {
    redirectOnUnauthorized(error);
  }
}

function bindFilters() {
  const chips = document.querySelectorAll('[data-preset]');
  const custom = document.getElementById('custom-range');
  const inputFrom = document.getElementById('range-from');
  const inputTo = document.getElementById('range-to');

  chips.forEach((chip) => {
    chip.addEventListener('click', () => {
      chips.forEach((c) => c.classList.toggle('active', c === chip));
      if (chip.dataset.preset === 'custom') {
        custom.classList.add('show');
        return;
      }
      custom.classList.remove('show');
      refreshAll(presetPeriod(chip.dataset.preset));
    });
  });

  document.getElementById('apply-range').addEventListener('click', () => {
    if (!inputFrom.value || !inputTo.value) return;
    if (inputTo.value < inputFrom.value) {           // FN-202
      alert('종료일이 시작일보다 빠릅니다.');
      return;
    }
    refreshAll({ from: inputFrom.value, to: inputTo.value });
  });
}

async function start() {
  try {
    const session = await api.session();
    document.getElementById('store-name').textContent = session.user.storeName;
  } catch (error) {
    if (redirectOnUnauthorized(error)) return;
  }

  document.getElementById('logout').addEventListener('click', async () => {
    await api.logout().catch(() => {});
    location.href = '/';
  });

  bindFilters();
  paintStatusBadge();
  refreshAll(presetPeriod('week'));
}

start();
