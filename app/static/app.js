// Shared helpers used across all pages.

function getToken() {
  return localStorage.getItem('candela_token');
}

function getSession() {
  try { return JSON.parse(localStorage.getItem('candela_user') || 'null'); }
  catch (e) { return null; }
}

function signOut() {
  localStorage.removeItem('candela_token');
  localStorage.removeItem('candela_user');
  location.href = '/login';
}

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const token = getToken();
  if (token) headers['Authorization'] = 'Bearer ' + token;

  const res = await fetch(path, { ...options, headers });

  // An expired or missing session sends you back to sign in rather than
  // failing silently with an unexplained error on every panel.
  if (res.status === 401) {
    signOut();
    throw new Error('Your session has expired — please sign in again.');
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { const body = await res.json(); detail = body.detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

// Attaches the session token to a raw fetch (file uploads, which send
// FormData and must not set a JSON content-type).
function authHeaders() {
  const token = getToken();
  return token ? { 'Authorization': 'Bearer ' + token } : {};
}

document.addEventListener('DOMContentLoaded', () => {
  const session = getSession();
  const el = document.getElementById('user-name-link');
  if (el && session) el.textContent = session.full_name || session.username;
  const out = document.getElementById('sign-out-link');
  if (out) out.addEventListener('click', (e) => { e.preventDefault(); signOut(); });

  // Hide nav items this user may not open
  if (session && session.screens) {
    document.querySelectorAll('.nav a[data-screen]').forEach(a => {
      if (!session.screens.includes(a.dataset.screen)) a.style.display = 'none';
    });
  }
});

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
