// Shared helpers used across all pages.

function getUserName() {
  let name = localStorage.getItem('candela_user_name');
  if (!name) {
    name = 'admin';
    localStorage.setItem('candela_user_name', name);
  }
  return name;
}

function setUserName() {
  const current = localStorage.getItem('candela_user_name') || '';
  const name = prompt('Your name (shown in the activity log):', current);
  if (name !== null) {
    localStorage.setItem('candela_user_name', name || 'Unknown');
    updateUserNameLink();
  }
}

function updateUserNameLink() {
  const el = document.getElementById('user-name-link');
  if (el) el.textContent = 'Signed in as ' + getUserName();
}

document.addEventListener('DOMContentLoaded', () => {
  updateUserNameLink();
  const link = document.getElementById('user-name-link');
  if (link) link.addEventListener('click', (e) => { e.preventDefault(); setUserName(); });
});

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', 'X-User-Name': getUserName() },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { const body = await res.json(); detail = body.detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function formToJSON(form) {
  const data = new FormData(form);
  const obj = {};
  for (const [key, value] of data.entries()) {
    if (value === '') continue;
    obj[key] = value;
  }
  return obj;
}

function toast(message, isError = false) {
  let el = document.getElementById('toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast';
    el.style.cssText = 'position:fixed;bottom:24px;right:24px;padding:12px 18px;border-radius:5px;font-family:IBM Plex Sans,sans-serif;font-size:14px;font-weight:500;z-index:999;box-shadow:0 4px 14px rgba(0,0,0,.15);';
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.style.background = isError ? '#C1503D' : '#4C8F63';
  el.style.color = '#fff';
  el.style.display = 'block';
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.display = 'none'; }, 3200);
}

function fmtMoney(n) {
  return 'AED ' + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}
