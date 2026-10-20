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
  const applyScreens = screens => document.querySelectorAll('.nav a[data-screen]').forEach(a => {
    a.style.display = screens.includes(a.dataset.screen) ? '' : 'none';
  });
  if (session && session.screens) applyScreens(session.screens);
  // Refresh from the server, so a newly added screen (or changed access)
  // shows without having to sign out and in again.
  if (session && getToken()) {
    api('/auth/me').then(me => {
      if (!me || !me.screens) return;
      applyScreens(me.screens);
      try { localStorage.setItem('candela_user', JSON.stringify({ ...session, screens: me.screens })); } catch (e) {}
    }).catch(() => {});
  }
});

// Shrink a photo in the browser before uploading it.
// The web server in front of the app refuses uploads over 1 MB, and phone or
// supplier photos are often 2-10 MB. Resizing here to at most 1600px on the
// longest side (still twice what the app stores) and re-encoding as JPEG gets
// any photo down to a few hundred KB, so it always goes through. The server
// then does the final crop, centring and ~50 KB compression.
const UPLOAD_MAX_SIDE = 1600;
const UPLOAD_MAX_BYTES = 900 * 1024;

async function shrinkImageForUpload(file) {
  if (!file.type.startsWith('image/')) return file;
  let bitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch (e) {
    return file;  // a format this browser can't decode - let the server judge it
  }
  const scale = Math.min(1, UPLOAD_MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  // Small files that are already a reasonable size go up untouched.
  if (scale === 1 && file.size <= UPLOAD_MAX_BYTES) { bitmap.close(); return file; }

  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff';  // transparent PNGs get a white background, matching the server
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();

  let blob = null;
  for (const quality of [0.92, 0.85, 0.75, 0.6]) {
    blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', quality));
    if (blob && blob.size <= UPLOAD_MAX_BYTES) break;
  }
  if (!blob) return file;
  const name = (file.name || 'photo').replace(/\.[^.]+$/, '') + '.jpg';
  return new File([blob], name, { type: 'image/jpeg' });
}

// ---------- Product categories ----------
// One list for products, stock and datasheets, so the spelling stays
// consistent everywhere (keep in step with app/categories.py).
const PRODUCT_CATEGORIES = [
  'Spotlight', 'Downlight', '230V Track Light', '48V Track Light', 'Surface Mounted',
  'Custom Light', 'Semi Recessed Light', 'Strip Light', 'Neon Light', 'Drivers', 'Accessories',
  'Track Accessories',
];

// Category filter kept in the URL (#category=...), so a refresh or shared
// link lands on the same tab. An old-style #Spotlight hash still works.
function readHashFilters() {
  const h = location.hash.slice(1);
  if (!h) return {};
  if (!h.includes('=')) return { category: decodeURIComponent(h) };
  const p = new URLSearchParams(h);
  return { category: p.get('category') || undefined };
}

function writeHashFilters(category) {
  const p = new URLSearchParams();
  if (category && category !== 'all') p.set('category', category);
  const q = p.toString();
  history.replaceState(null, '', q ? '#' + q : location.pathname);
}

function escHtml(s) {
  return String(s).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

// Fills a <select> with the category list. Something still carrying an older
// category keeps it (marked "old category") until someone picks a new one.
function fillCategorySelect(select, current) {
  const opts = ['<option value="">Choose a category</option>'];
  if (current && !PRODUCT_CATEGORIES.includes(current)) {
    opts.push(`<option value="${escHtml(current)}">${escHtml(current)} (old category)</option>`);
  }
  PRODUCT_CATEGORIES.forEach(c => opts.push(`<option value="${c}">${c}</option>`));
  select.innerHTML = opts.join('');
  select.value = current || '';
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
    el.style.cssText = 'position:fixed;bottom:24px;right:24px;padding:12px 18px;border-radius:5px;font-family:Inter,-apple-system,Segoe UI,Arial,sans-serif;font-size:14px;font-weight:500;z-index:999;box-shadow:0 4px 14px rgba(0,0,0,.15);';
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

// Timestamps from the API are UTC but often arrive without a timezone
// marker, which browsers read as local time - so an action logged at
// 16:40 UTC would display as 16:40 local and look four hours early.
function fmtDateTime(iso) {
  if (!iso) return '—';
  const utc = /(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : iso + 'Z';
  const d = new Date(utc);
  return d.toLocaleString(undefined, {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
  });
}

// ---------- Report downloads and previews ----------
// Files open through plain navigation, which can't send the login header, so
// each one carries a short-lived download token in its URL.
//
// mode 'preview' opens the PDF in a new tab. The tab is opened right away,
// inside the click, so the browser's popup blocker allows it; its address is
// filled in once the token comes back. 'pdf' and 'xlsx' download the file
// without leaving the page.
async function withDownloadToken(mode, buildUrl) {
  const tab = mode === 'preview' ? window.open('', '_blank') : null;
  if (tab) {
    tab.document.title = 'Preparing preview…';
    tab.document.body.innerHTML = '<p style="font:14px sans-serif;padding:32px;color:#7A7364">Preparing preview…</p>';
  }
  try {
    const r = await api('/auth/download-token', { method: 'POST' });
    const url = buildUrl(encodeURIComponent(r.token));
    if (mode === 'preview') {
      if (tab) tab.location.replace(url); else window.open(url, '_blank');
    } else {
      const a = document.createElement('a');
      a.href = url;
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
  } catch (err) {
    if (tab) tab.close();
    toast(err.message, true);
  }
}

// kind is a list ('projects') or one record ('project/12', 'product/3').
// fmt is 'preview', 'pdf' or 'xlsx'. extra is appended to the query string.
function downloadReport(kind, fmt, extra = '') {
  const file = fmt === 'preview' ? 'pdf' : fmt;
  return withDownloadToken(fmt, token =>
    `/reports/${kind}.${file}?token=${token}${fmt === 'preview' ? '&preview=1' : ''}${extra || ''}`);
}

// ---------- Export menu ----------
// One "Export" button that opens a small menu, instead of a row of
// Preview / PDF / Excel buttons repeated for every report on a page.
// groups: [{ label?, items: [{ text, onclick }] }] - onclick is JS code.
function exportMenu(groups, buttonText = 'Export') {
  const body = groups.map(g =>
    (g.label ? `<div class="menu-label">${escHtml(g.label)}</div>` : '') +
    g.items.map(i => `<button type="button" class="menu-item" onclick="closeMenus(); ${i.onclick}">${i.text}</button>`).join('')
  ).join('<div class="menu-sep"></div>');
  return `<details class="export-menu"><summary class="btn btn-ghost btn-sm">${buttonText}<span class="caret" aria-hidden="true">▾</span></summary><div class="menu">${body}</div></details>`;
}

function closeMenus(except) {
  document.querySelectorAll('details.export-menu[open]').forEach(d => { if (d !== except) d.open = false; });
}
// Clicking anywhere else closes an open menu.
document.addEventListener('click', e => closeMenus(e.target.closest && e.target.closest('details.export-menu')));

// The menu entries for one report.
// opts.label: section heading (for pages with two reports)
// opts.noPreview: leave out "Preview PDF"
// opts.extra: JS expression evaluated on click, returning extra query
// parameters (e.g. the category tab currently showing)
function reportItems(kind, opts = {}) {
  const extra = opts.extra ? `, ${opts.extra}` : '';
  const items = [];
  if (!opts.noPreview) items.push({ text: 'Preview PDF', onclick: `downloadReport('${kind}','preview'${extra})` });
  items.push({ text: 'Download PDF', onclick: `downloadReport('${kind}','pdf'${extra})` });
  items.push({ text: 'Download Excel', onclick: `downloadReport('${kind}','xlsx'${extra})` });
  return { label: opts.label, items };
}

function reportButtons(kind, opts = {}) {
  return exportMenu([reportItems(kind, opts)]);
}



// ---------- Ticking several rows ----------
// Shows "N selected  [Delete selected] [Clear]" above a table while rows are
// ticked. onDelete(ids) does the deleting; onClear() unticks.
function bulkBar(barId, ids, noun, onDelete, onClear) {
  const bar = document.getElementById(barId);
  if (!bar) return;
  if (!ids.length) { bar.hidden = true; bar.innerHTML = ''; return; }
  bar.hidden = false;
  bar.innerHTML = `<strong>${ids.length}</strong> ${noun}${ids.length === 1 ? '' : 's'} selected
    <button type="button" class="btn btn-sm btn-danger-solid" data-bulk-delete>Delete selected</button>
    <button type="button" class="btn btn-ghost btn-sm" data-bulk-clear>Clear</button>`;
  bar.querySelector('[data-bulk-delete]').onclick = () => onDelete(ids.map(Number));
  bar.querySelector('[data-bulk-clear]').onclick = onClear;
}

// ---------- Product cost in AED, USD or EUR ----------
// Rates (AED for 1 unit) come from Settings. Landed AED cost =
// amount x rate x (1 + landed % / 100); the server works out the same figure on save.
let _ratesPromise = null;
function loadRates() {
  if (!_ratesPromise) {
    _ratesPromise = api('/rates/').then(rows => {
      const m = { AED: 1 };
      rows.forEach(r => { if (r.rate) m[r.currency] = r.rate; });
      return m;
    }).catch(() => ({ AED: 1 }));
  }
  return _ratesPromise;
}

function costToAED(amount, currency, rates, pct) {
  const rate = rates[currency || 'AED'];
  if (rate == null) return null;
  return Math.round((Number(amount) || 0) * rate * (1 + (Number(pct) || 0) / 100) * 100) / 100;
}

function fmtNum(n, dp) {
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

// The line under the cost fields: "= AED 530.64 landed cost (EUR 120.00 × 4.02 + 10%)"
function costNoteText(amount, currency, rates, pct) {
  currency = currency || 'AED';
  pct = Number(pct) || 0;
  if (currency === 'AED' && !pct) return '';
  const aed = costToAED(amount, currency, rates, pct);
  if (aed == null) return `<span class="cost-warn">Set the ${currency} rate in Settings first</span>`;
  const how = [`${currency} ${fmtNum(amount || 0, 2)}`];
  if (currency !== 'AED') how.push(`× ${rates[currency]}`);
  if (pct) how.push(`+ ${pct}%`);
  return `= <strong>${fmtMoney(aed)}</strong> landed cost <span class="cost-how">(${how.join(' ')})</span>`;
}

// Wires the cost amount / currency / landed % inputs of a product form so the
// AED figure updates as you type.
function wireCostFields(form) {
  const note = form.querySelector('.cost-note');
  const update = () => loadRates().then(rates => {
    note.innerHTML = costNoteText(form.cost_amount.value, form.cost_currency.value, rates, form.landed_pct.value);
  });
  ['cost_amount', 'cost_currency', 'landed_pct'].forEach(n => form[n].addEventListener('input', update));
  form._updateCost = update;
  update();
}

// Numbers from the cost inputs, ready to send with a product
function costPayload(payload) {
  payload.cost_currency = payload.cost_currency || 'AED';
  payload.cost_amount = parseFloat(payload.cost_amount || 0);
  payload.landed_pct = parseFloat(payload.landed_pct || 0);
  delete payload.cost_price;
  return payload;
}

// ---------- Message carried to the next page ----------
// e.g. "Product updated" after saving and going back to the list.
function flashNext(message) {
  try { sessionStorage.setItem('flash', message); } catch (e) { /* no storage: skip */ }
}
function showFlash() {
  let msg = null;
  try { msg = sessionStorage.getItem('flash'); sessionStorage.removeItem('flash'); } catch (e) { /* ignore */ }
  if (msg) toast(msg);
}
document.addEventListener('DOMContentLoaded', showFlash);
