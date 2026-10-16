/**
 * 신메뉴 매출 (FN-252) + 기준 설정 패널 (FN-253 / FR-DASH-15).
 *
 * 「메뉴별 매출 TOP 10」 바로 위에 둔다. 새로 들인 메뉴는 아직 양이 적어
 * 순위표에 올라오지 않는데, 정작 사장님이 가장 궁금해하는 숫자이기 때문이다.
 *
 * ⚠ 함수·상수 이름에 `newMenu` 접두사를 붙인다.
 *   단일 HTML 내보내기(server/export.py)가 모든 위젯 모듈을 **한 스코프로** 합치므로
 *   `escapeHtml` 같은 평범한 이름을 쓰면 다른 위젯과 부딪친다.
 */

import { api } from '../api.js';
import { QTY, WON, shortWon } from '../format.js';
import { createWidget } from './widget.js';

const NEW_MENU_PRESETS = [1, 3, 6, 12];

export function newMenuWidget() {
  const root = document.getElementById('new-menu');
  if (!root) return { refresh: async () => {} };

  const panel = root.querySelector('[data-panel]');
  const toggle = root.querySelector('[data-settings-toggle]');
  let currentPeriod = null;
  let criteria = null;
  let searchKeyword = '';        // 패널을 다시 그려도 찾던 메뉴가 사라지지 않게

  const widget = createWidget({
    root: 'new-menu',
    // 기준(criteria)은 신메뉴가 하나도 없을 때도 화면에 떠 있어야 한다.
    // render 는 빈 상태에서 호출되지 않으므로 여기서 받아 둔다.
    load: async (period) => {
      const data = await api.newMenu(period);
      criteria = data.criteria;
      newMenuPaintHint(root, data);
      return data;
    },
    render: (data, period) => newMenuPaintList(root, data, period),
    isEmpty: (data) => !data.data.length,
    emptyMessage: '이 기준에 해당하는 신메뉴가 없습니다. [기준 설정]에서 분류를 추가하거나 '
                + '기간을 늘리거나, 메뉴를 직접 지정할 수 있습니다.',
  });

  async function refresh(period) {
    currentPeriod = period;
    await widget.refresh(period);
    if (panel && !panel.classList.contains('hidden')) await openPanel();
  }

  async function openPanel() {
    panel.innerHTML = '<div class="skeleton" style="height:120px"></div>';
    panel.classList.remove('hidden');
    try {
      const catalog = await api.newMenuCatalog(currentPeriod);
      criteria = catalog.criteria;
      panel.innerHTML = newMenuPanelHtml(criteria, catalog.data, catalog.categories);
      bindPanel();
      applySearch();
    } catch (error) {
      panel.innerHTML = `<p class="nm-note">${newMenuEscape(error.message ?? '설정을 불러오지 못했습니다.')}</p>`;
    }
  }

  function bindPanel() {
    // 기간을 바꿔도 분류 선택은 유지한다 — 따로 거는 조건이다
    panel.querySelectorAll('[data-months]').forEach((button) => {
      button.addEventListener('click', () => applyCriteria(
        { mode: 'months', months: Number(button.dataset.months),
          categories: criteria.categories }));
    });

    const custom = panel.querySelector('[data-since]');
    panel.querySelector('[data-apply-since]')?.addEventListener('click', () => {
      if (!custom.value) return;
      applyCriteria({ mode: 'since', since: custom.value, categories: criteria.categories });
    });

    panel.querySelector('[data-category-all]')?.addEventListener('click', () =>
      applyCriteria(newMenuWithCategories(criteria, null)));
    panel.querySelectorAll('[data-category]').forEach((button) => {
      button.addEventListener('click', () => applyCriteria(
        newMenuWithCategories(criteria, newMenuToggle(criteria.categories, button.dataset.category))));
    });

    const search = panel.querySelector('[data-search]');
    search?.addEventListener('input', () => {
      searchKeyword = search.value.trim().toLowerCase();
      applySearch();
    });

    panel.querySelectorAll('[data-override]').forEach((select) => {
      select.addEventListener('change', async () => {
        const value = select.value;
        const isNew = value === 'auto' ? null : value === 'new';
        select.disabled = true;
        try {
          await api.setNewMenuOverride(select.dataset.override, isNew);
          await refresh(currentPeriod);
        } catch (error) {
          alert(error.message ?? '설정을 저장하지 못했습니다.');
          select.disabled = false;
        }
      });
    });
  }

  function applySearch() {
    const search = panel.querySelector('[data-search]');
    if (search) search.value = searchKeyword;
    panel.querySelectorAll('.nm-pick').forEach((row) => {
      row.classList.toggle('hidden', !row.dataset.search.includes(searchKeyword));
    });
  }

  async function applyCriteria(next) {
    try {
      await api.saveNewMenuCriteria(currentPeriod, next);
      await refresh(currentPeriod);
    } catch (error) {
      alert(error.message ?? '기준을 저장하지 못했습니다.');
    }
  }

  toggle?.addEventListener('click', () => {
    if (panel.classList.contains('hidden')) openPanel();
    else panel.classList.add('hidden');
  });

  return { refresh };
}

/** 날짜 조건은 그대로 두고 분류만 갈아 끼운 저장 payload. */
function newMenuWithCategories(criteria, categories) {
  const base = criteria.mode === 'since'
    ? { mode: 'since', since: criteria.since }
    : { mode: 'months', months: criteria.months };
  return { ...base, categories };
}

/**
 * 분류 칩 토글. `null` 은 '전체'다.
 *
 * 전체 상태에서 하나를 누르면 그것만 남는다 — '전체에서 하나 뺀다'가 아니라
 * '그것만 본다'가 사장님이 기대하는 동작이다. 전부 끄면 다시 전체로 돌아간다.
 */
function newMenuToggle(current, name) {
  const next = current ? current.filter((item) => item !== name) : [];
  if (!current || next.length === current.length) next.push(name);
  return next.length ? next : null;
}

/** 기준을 한 줄로 — 신메뉴가 없을 때도 "무슨 기준으로 없는지"가 보여야 한다. */
function newMenuPaintHint(root, data) {
  const hint = root.querySelector('.hint');
  if (!hint) return;
  const categories = data.criteria.categories;
  hint.textContent = `${newMenuCriteriaLabel(data.criteria)} · ${data.criteria.since} 이후 첫 판매`
    + ` · ${categories ? categories.join(', ') : '분류 전체'}`;
}

function newMenuCriteriaLabel(criteria) {
  return criteria.mode === 'since' ? '기준일 직접 지정' : `최근 ${criteria.months}개월`;
}

function newMenuPaintList(root, data, period) {
  const body = root.querySelector('[data-body]');
  const max = Math.max(...data.data.map((row) => row.sales), 1);

  // 합계는 매출이 발생한 신메뉴만 더한 값이다 (service/new_menu.py `_totals`).
  // `count` 와 `soldCount` 를 함께 보여 줘야 "23개 중 10개만 팔렸다"가 읽힌다 —
  // 섞어서 한 숫자로 내보내면 0원 옵션 수천 개가 판매량인 것처럼 보인다.
  const totals = data.totals;
  body.innerHTML = `
    <div class="nm-total">
      <span>신메뉴 <b>${totals.count}</b>개 중 <b>${totals.soldCount}</b>개 판매</span>
      <span><b>${QTY(totals.quantity)}</b></span>
      <span class="nm-total-amt" title="${WON(totals.sales)}">${shortWon(totals.sales)}</span>
      <span class="nm-total-share">전체 메뉴 매출의 ${totals.share}%</span>
    </div>
    <div class="menu-list">${data.data.map((row) => newMenuRow(row, max, period)).join('')}</div>`;
}

function newMenuRow(row, max, period) {
  // 오른쪽 칸은 세 가지다. 뭉뚱그리면 "안 팔린 신메뉴"와 "원래 0원인 옵션"이
  // 같은 0원으로 보여서, 사장님이 신메뉴가 실패한 줄 알게 된다.
  //   매출 있음        → 금액
  //   수량만 있음      → 옵션 항목(인원 구분·육수 선택 등. 원래 0원이다)
  //   수량도 0         → 이 기간엔 안 팔렸다
  const amount = row.sales > 0
    ? `<span title="${WON(row.sales)}">${shortWon(row.sales)}</span>`
    : (row.quantity > 0
        ? '<span class="nm-zero">옵션</span>'
        : '<span class="nm-zero">판매 없음</span>');
  const badge = row.source === 'manual'
    ? '<span class="nm-badge">직접 지정</span>'
    : `<span class="nm-badge auto">신규 ${newMenuAgeLabel(row.firstSoldAt, period)}</span>`;

  return `
    <div class="menu-row nm-row">
      <div class="nm-date">${newMenuShortDate(row.firstSoldAt)}</div>
      <div>
        <div class="menu-name">${newMenuEscape(row.menuName)}${badge}</div>
        <div class="menu-meta">${newMenuEscape(row.category ?? '')} · ${QTY(row.quantity)} · ${row.share}%</div>
        <div class="menu-bar"><span style="width:${(row.sales / max * 100).toFixed(1)}%"></span></div>
      </div>
      <div class="menu-amount">${amount}</div>
    </div>`;
}

/**
 * 첫 판매일로부터 얼마나 지났나 — '3일째' / '2개월째'. 날짜만으로는 감이 안 온다.
 *
 * '지금'이 아니라 **조회 기간 종료일** 기준이다. 서버의 판정 기준과 같은 날을 써야
 * 화면 안에서 숫자가 어긋나지 않고, 단일 HTML 스냅샷에서도 값이 흘러가지 않는다.
 */
function newMenuAgeLabel(iso, period) {
  if (!iso) return '';
  const until = new Date(`${period?.to ?? iso}T00:00:00`).getTime();
  const days = Math.round((until - new Date(`${iso}T00:00:00`).getTime()) / 86400000);
  if (days <= 0) return '오늘';
  if (days < 31) return `${days}일째`;
  return `${Math.floor(days / 30)}개월째`;
}

const newMenuShortDate = (iso) => (iso ? iso.slice(2).replace(/-/g, '.') : '—');

// ── 기준 설정 패널 (FN-253) ───────────────────────────────

function newMenuPanelHtml(criteria, items, categories) {
  const preset = (months) => `
    <button class="chip ${criteria.mode === 'months' && criteria.months === months ? 'active' : ''}"
            data-months="${months}">${months}개월</button>`;

  // 분류 칩은 여러 개를 켤 수 있다. `토마토샤브` 는 120g 이 월남쌈샤브샤브,
  // 70g 이 점심특선이라 하나만 켜면 같은 신메뉴의 반쪽이 사라진다.
  const categoryChip = (name) => `
    <button class="chip ${criteria.categories?.includes(name) ? 'active' : ''}"
            data-category="${newMenuEscape(name)}">${newMenuEscape(name)}</button>`;

  return `
    <div class="nm-panel-inner">
      <p class="nm-label">볼 분류</p>
      <div class="nm-chips">
        <button class="chip ${criteria.categories ? '' : 'active'}" data-category-all>전체</button>
        ${(categories ?? []).map(categoryChip).join('')}
      </div>
      <p class="nm-note">
        POS <b>기타</b> 분류에는 메뉴가 아니라 옵션(<b>성인</b>·<b>반반</b>·<b>목심</b>)이 들어 있어
        기본에서 빼 두었습니다. 같은 신메뉴라도 120g은 <b>월남쌈샤브샤브</b>,
        70g은 <b>점심특선</b>으로 들어가니 둘 다 켜 두시면 빠짐없이 보입니다.
      </p>

      <p class="nm-label">신메뉴로 볼 기간</p>
      <div class="nm-chips">
        ${NEW_MENU_PRESETS.map(preset).join('')}
        <span class="nm-since">
          <input type="date" data-since value="${criteria.since}">
          <button class="chip ${criteria.mode === 'since' ? 'active' : ''}" data-apply-since>기준일로</button>
        </span>
      </div>
      <p class="nm-note">
        첫 판매일이 <b>${criteria.since}</b> 이후인 메뉴를 신메뉴로 봅니다.
        POS는 메뉴 등록일을 주지 않아 <b>첫 판매일</b>로 가늠한 값입니다 —
        어긋나면 아래에서 직접 지정하세요.
      </p>

      <p class="nm-label">메뉴 직접 지정</p>
      <input class="nm-search" type="search" data-search placeholder="메뉴 이름으로 찾기">
      <div class="nm-picks">${items.map(newMenuPickRow).join('')}</div>
    </div>`;
}

function newMenuPickRow(item) {
  const value = item.override === null || item.override === undefined
    ? 'auto' : (item.override ? 'new' : 'exclude');
  const search = `${item.menuName} ${item.category ?? ''}`.toLowerCase();

  return `
    <label class="nm-pick${item.isNew ? ' is-new' : ''}" data-search="${newMenuEscape(search)}">
      <span class="nm-pick-name">${newMenuEscape(item.menuName)}</span>
      <span class="nm-pick-date">${newMenuShortDate(item.firstSoldAt)} 첫 판매</span>
      <select data-override="${newMenuEscape(item.menuCode)}">
        <option value="auto"${value === 'auto' ? ' selected' : ''}>자동${item.auto ? ' (신메뉴)' : ''}</option>
        <option value="new"${value === 'new' ? ' selected' : ''}>신메뉴</option>
        <option value="exclude"${value === 'exclude' ? ' selected' : ''}>제외</option>
      </select>
    </label>`;
}

/** 메뉴명은 POS에서 온 문자열이다 — 그대로 innerHTML에 넣지 않는다 (NFR-SEC-05). */
function newMenuEscape(text) {
  return String(text).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
