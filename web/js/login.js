/** 로그인 화면 (SCR-01). */

import { api, ApiError } from './api.js';

const form = document.getElementById('login-form');
const username = document.getElementById('username');
const password = document.getElementById('password');
const remember = document.getElementById('remember');
const submit = document.getElementById('submit');
const message = document.getElementById('message');

/** FN-108 — 유효 세션이 있으면 바로 대시보드로. */
api.session().then(() => { location.href = '/dashboard'; }).catch(() => {});

/** FN-102 — 입력이 비어 있으면 버튼 비활성화. */
function validate() {
  submit.disabled = !username.value.trim() || !password.value;
}
username.addEventListener('input', validate);
password.addEventListener('input', validate);

document.getElementById('toggle-password').addEventListener('click', () => {
  password.type = password.type === 'password' ? 'text' : 'password';
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  setState('loading');

  try {
    await api.login(username.value.trim(), password.value, remember.checked);
    location.href = '/dashboard';                       // FN-104
  } catch (error) {
    // FN-105 — 사유를 세분화하지 않는다. 서버 메시지를 그대로 보여준다.
    setState('error', error instanceof ApiError ? error.message : '로그인에 실패했습니다.');
  }
});

function setState(state, text = '') {
  const loading = state === 'loading';
  submit.disabled = loading;
  submit.textContent = loading ? '확인 중…' : '로그인';
  username.disabled = password.disabled = loading;
  message.textContent = text;
  document.querySelectorAll('.field').forEach((field) =>
    field.classList.toggle('error', state === 'error'));
  if (!loading) validate();
}
