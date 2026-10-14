// Generic table renderer: click-to-sort columns, drag-to-reorder columns
// (persisted per table), and a consistent trailing actions column.
// Used by every list page (Products, Stock, Customers, Quotations, Projects...)
// so table behavior is identical everywhere instead of hand-rolled per page.
//
// Optional ticking of rows: pass select: { id: row => row.id, onChange: ids => ... }
// to get a checkbox column (with select-all). DataTable.selected(storageKey)
// returns the ticked ids; DataTable.clearSelection(storageKey) unticks all.

const DataTable = (() => {
  const state = {}; // storageKey -> { sortKey, sortDir, lastArgs }

  function loadColumnOrder(storageKey, columns) {
    try {
      const saved = JSON.parse(localStorage.getItem('cols:' + storageKey) || 'null');
      if (!saved) return columns;
      const byKey = Object.fromEntries(columns.map(c => [c.key, c]));
      const ordered = saved.filter(k => byKey[k]).map(k => byKey[k]);
      const missing = columns.filter(c => !saved.includes(c.key));
      return [...ordered, ...missing];
    } catch (e) {
      return columns;
    }
  }

  function saveColumnOrder(storageKey, columns) {
    localStorage.setItem('cols:' + storageKey, JSON.stringify(columns.map(c => c.key)));
  }

  function compareValues(a, b) {
    const na = parseFloat(a), nb = parseFloat(b);
    const bothNumeric = !isNaN(na) && !isNaN(nb) && String(a).trim() !== '' && String(b).trim() !== '';
    if (bothNumeric) return na - nb;
    return String(a ?? '').localeCompare(String(b ?? ''));
  }

  function render(args) {
    const { containerId, storageKey, columns: rawColumns, rows, actions, emptyMessage } = args;
    state[storageKey] = state[storageKey] || { sortKey: null, sortDir: 1 };
    state[storageKey].lastArgs = args;

    const columns = loadColumnOrder(storageKey, rawColumns);
    const container = document.getElementById(containerId);
    if (!container) return;
    const sel = args.select;
    if (sel) {
      // Keep only ticks for rows still listed (after filtering / deleting)
      const ids = new Set(rows.map(r => String(sel.id(r))));
      state[storageKey].selected = new Set([...(state[storageKey].selected || [])].filter(id => ids.has(id)));
    }

    let sortedRows = rows;
    const s = state[storageKey];
    if (s.sortKey) {
      const col = columns.find(c => c.key === s.sortKey);
      if (col) {
        sortedRows = [...rows].sort((ra, rb) => compareValues(col.value(ra), col.value(rb)) * s.sortDir);
      }
    }

    const thHtml = columns.map(col => {
      const isSorted = s.sortKey === col.key;
      const arrow = isSorted ? (s.sortDir === 1 ? ' \u2191' : ' \u2193') : '';
      const sortable = col.sortable !== false;
      return `<th draggable="true" data-key="${col.key}" class="${sortable ? 'th-sortable' : ''}${col.numeric ? ' num' : ''}" style="${col.width ? 'width:' + col.width + ';' : ''}">${col.label}<span class="sort-arrow">${arrow}</span></th>`;
    }).join('') + (actions ? '<th class="th-actions"></th>' : '');
    const chosen = sel ? state[storageKey].selected : null;
    const allTicked = sel && rows.length && rows.every(r => chosen.has(String(sel.id(r))));
    const thAll = sel ? `<th class="th-check"><input type="checkbox" data-all title="Select all" ${allTicked ? 'checked' : ''}></th>` : '';

    const bodyHtml = sortedRows.length
      ? sortedRows.map(row => {
          const cells = columns.map(col => `<td class="${col.numeric ? 'num' : ''}">${col.render(row)}</td>`).join('');
          const id = sel ? String(sel.id(row)) : null;
          const tick = sel ? `<td class="td-check"><input type="checkbox" data-id="${id}" ${chosen.has(id) ? 'checked' : ''}></td>` : '';
          return `<tr${sel && chosen.has(id) ? ' class="row-selected"' : ''}>${tick}${cells}${actions ? `<td class="row-actions">${actions(row)}</td>` : ''}</tr>`;
        }).join('')
      : `<tr><td colspan="${columns.length + (actions ? 1 : 0) + (sel ? 1 : 0)}"><div class="empty-state"><p>${emptyMessage || 'Nothing here yet.'}</p></div></td></tr>`;

    container.innerHTML = `<div class="table-scroll"><table class="dt"><thead><tr>${thAll}${thHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`;

    if (sel) {
      const notify = () => { if (sel.onChange) sel.onChange([...chosen]); };
      container.querySelectorAll('input[data-id]').forEach(cb => cb.addEventListener('change', () => {
        cb.checked ? chosen.add(cb.dataset.id) : chosen.delete(cb.dataset.id);
        cb.closest('tr').classList.toggle('row-selected', cb.checked);
        const all = container.querySelector('input[data-all]');
        if (all) all.checked = rows.every(r => chosen.has(String(sel.id(r))));
        notify();
      }));
      const all = container.querySelector('input[data-all]');
      if (all) all.addEventListener('change', () => {
        rows.forEach(r => { const id = String(sel.id(r)); all.checked ? chosen.add(id) : chosen.delete(id); });
        render(state[storageKey].lastArgs);
        notify();
      });
      notify();
    }

    // Sorting
    container.querySelectorAll('th.th-sortable').forEach(th => {
      th.addEventListener('click', () => {
        const key = th.dataset.key;
        if (s.sortKey === key) {
          s.sortDir *= -1;
        } else {
          s.sortKey = key;
          s.sortDir = 1;
        }
        render(state[storageKey].lastArgs);
      });
    });

    // Drag-to-reorder columns
    let dragKey = null;
    container.querySelectorAll('th[draggable="true"]').forEach(th => {
      th.addEventListener('dragstart', (e) => {
        dragKey = th.dataset.key;
        e.dataTransfer.effectAllowed = 'move';
        th.classList.add('dragging-col');
      });
      th.addEventListener('dragend', () => th.classList.remove('dragging-col'));
      th.addEventListener('dragover', (e) => e.preventDefault());
      th.addEventListener('drop', (e) => {
        e.preventDefault();
        const dropKey = th.dataset.key;
        if (!dragKey || dragKey === dropKey) return;
        const cols = loadColumnOrder(storageKey, rawColumns);
        const fromIdx = cols.findIndex(c => c.key === dragKey);
        const toIdx = cols.findIndex(c => c.key === dropKey);
        const [moved] = cols.splice(fromIdx, 1);
        cols.splice(toIdx, 0, moved);
        saveColumnOrder(storageKey, cols);
        render(state[storageKey].lastArgs);
      });
    });
  }

  function selected(storageKey) {
    return [...((state[storageKey] && state[storageKey].selected) || [])];
  }
  function clearSelection(storageKey) {
    if (state[storageKey]) state[storageKey].selected = new Set();
  }

  return { render, selected, clearSelection };
})();
