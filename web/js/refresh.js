/**
 * 수동 수집 버튼 (FN-205 / FR-COL-07).
 *
 * 브라우저 새로고침(F5)은 이미 DB의 최신 데이터를 다시 그린다 — dashboard.js 가 한다.
 * 이 버튼은 그보다 한 걸음 더 가서 **POS에서 지금 받아온다**.
 *
 * 수집은 30초~1분 걸리므로 요청 하나로 끝나지 않는다:
 *   누름 → POST /api/system/collect → 끝날 때까지 상태를 물어봄 → 끝나면 화면 재조회
 *
 * 누가 실제로 수집하는지(이 서버냐 GitHub Actions냐)는 서버가 판단한다.
 * 여기서는 `available` / `running` / `retryAfterSec` 세 값만 보고 그린다.
 */

import { api, redirectOnUnauthorized } from './api.js';

const POLL_INTERVAL_MS = 3_000;
const POLL_GRACE_MS = 20_000;      // 방금 부탁한 건이 아직 안 잡히는 구간
const POLL_TIMEOUT_MS = 300_000;   // 5분이면 포기하고 안내한다

export function collectButton({ onFinished }) {
  const button = document.getElementById('collect-now');
  const message = document.getElementById('collect-message');
  if (!button) return { start: async () => {} };

  let polling = false;
  let cooldownTimer = null;
  let elapsedTimer = null;

  function paint(state) {
    clearTimeout(cooldownTimer);
    stopElapsed();
    button.hidden = !state.available;
    if (!state.available) {
      message.textContent = '';
      return;
    }

    if (state.running) {
      button.disabled = true;
      button.textContent = '수집 중…';
      startElapsed(state.startedAt);
      return;
    }

    button.textContent = '지금 수집';
    if (state.retryAfterSec > 0) {
      // 방금 수집했다 — POS에 연달아 요청하지 않는다
      button.disabled = true;
      message.textContent = `방금 수집했습니다 · ${minutes(state.retryAfterSec)} 후 가능`;
      cooldownTimer = setTimeout(() => refreshState(), state.retryAfterSec * 1_000 + 1_000);
      return;
    }

    button.disabled = false;
    message.textContent = state.ok === false ? state.message : '';
  }

  /**
   * 얼마나 걸릴지는 GitHub Actions 대기열에 따라 달라진다 — 예상 시간을 적어 두면
   * 또 어긋나므로 시작 시각부터 흐른 시간을 그대로 보여준다.
   * 시작 시각은 서버가 준다 (local은 스레드 시작, github은 run의 created_at).
   */
  function startElapsed(startedAt) {
    const base = Date.parse(startedAt ?? '') || Date.now();
    const draw = () => {
      // 브라우저 시계가 조금 앞서 있어도 음수가 보이지 않게 한다
      const seconds = Math.max(0, Math.round((Date.now() - base) / 1_000));
      message.textContent = `POS에서 받아오는 중입니다 (${elapsed(seconds)} 경과)`;
    };
    draw();
    elapsedTimer = setInterval(draw, 1_000);
  }

  function stopElapsed() {
    clearInterval(elapsedTimer);
    elapsedTimer = null;
  }

  async function refreshState() {
    try {
      paint(await api.collectStatus());
    } catch (error) {
      if (redirectOnUnauthorized(error)) return;
      button.hidden = true;                 // 상태를 모르면 누르게 하지 않는다
    }
  }

  /**
   * 끝날 때까지 상태를 물어본다.
   * 시작 직후 `running:false` 는 믿지 않는다 — GitHub Actions는 dispatch 직후
   * 몇 초간 실행 목록에 뜨지 않아서, 그대로 믿으면 "끝났다"고 오해한다.
   */
  async function poll() {
    if (polling) return;
    polling = true;
    const since = Date.now();

    while (polling) {
      await sleep(POLL_INTERVAL_MS);
      let state;
      try {
        state = await api.collectStatus();
      } catch (error) {
        if (redirectOnUnauthorized(error)) return;
        continue;                            // 일시적 오류로 폴링을 끊지 않는다
      }

      const waited = Date.now() - since;
      if (!state.running && waited > POLL_GRACE_MS) {
        polling = false;
        paint(state);
        message.textContent = state.ok === false
          ? state.message
          : '수집을 마쳤습니다. 화면을 새로 그렸습니다.';
        onFinished();
        return;
      }
      if (waited > POLL_TIMEOUT_MS) {
        polling = false;
        stopElapsed();
        button.disabled = false;
        button.textContent = '지금 수집';
        message.textContent = '확인이 오래 걸립니다. 잠시 후 새로고침해 주세요.';
        return;
      }
    }
  }

  button.addEventListener('click', async () => {
    button.disabled = true;
    button.textContent = '수집 중…';
    message.textContent = '수집을 요청했습니다…';
    try {
      paint(await api.collectNow());
      poll();
    } catch (error) {
      if (redirectOnUnauthorized(error)) return;
      // 429(최소 간격)·409(이미 진행 중)는 정상 동작이다 — 서버 문구를 그대로 보여준다
      message.textContent = error.message;
      refreshState();
    }
  });

  return { start: refreshState };
}

function elapsed(seconds) {
  if (seconds < 60) return `${seconds}초`;
  const rest = seconds % 60;
  return rest === 0
    ? `${Math.floor(seconds / 60)}분`
    : `${Math.floor(seconds / 60)}분 ${rest}초`;
}

function minutes(seconds) {
  return seconds >= 60 ? `약 ${Math.ceil(seconds / 60)}분` : `${seconds}초`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
