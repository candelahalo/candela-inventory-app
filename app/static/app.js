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
// The categories used on halolights.uk. Products and datasheets pick from
// this list so the spelling stays consistent everywhere.
const PRODUCT_CATEGORIES = [
  'Recessed Invisible', 'Recessed Visible', 'Semi Recessed', 'Low Voltage Track',
  'Suspended', 'Led Flex', 'Surface Mounted', 'Accessories',
];

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

// Preview / PDF / Excel buttons for a page header.
// opts.label puts a small caption in front (for pages with two reports).
// opts.noPreview leaves out the Preview button.
// opts.extra is a JS expression evaluated on click, returning extra query
// parameters (e.g. the Projects tab currently showing).
function reportButtons(kind, opts = {}) {
  const extra = opts.extra ? `, ${opts.extra}` : '';
  const label = opts.label ? `<span class="report-label">${opts.label}</span>` : '';
  return `
    <div class="report-actions">${label}
      ${opts.noPreview ? '' : `<button type="button" class="btn btn-ghost btn-sm" title="Open the PDF in a new tab" onclick="downloadReport('${kind}','preview'${extra})">Preview</button>`}
      <button type="button" class="btn btn-ghost btn-sm" title="Download as PDF" onclick="downloadReport('${kind}','pdf'${extra})">PDF</button>
      <button type="button" class="btn btn-ghost btn-sm" title="Download as Excel" onclick="downloadReport('${kind}','xlsx'${extra})">Excel</button>
    </div>`;
}
