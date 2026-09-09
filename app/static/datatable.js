// Generic table renderer: click-to-sort columns, drag-to-reorder columns
// (persisted per table), and a consistent trailing actions column.
// Used by every list page (Products, Stock, Customers, Quotations, Projects...)
// so table behavior is identical everywhere instead of hand-rolled per page.

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
      return `<th draggable="true" data-key="${col.key}" class="${sortable ? 'th-sortable' : ''}" style="${col.width ? 'width:' + col.width + ';' : ''}">${col.label}<span class="sort-arrow">${arrow}</span></th>`;
    }).join('') + (actions ? '<th class="th-actions"></th>' : '');

    const bodyHtml = sortedRows.length
      ? sortedRows.map(row => {
          const cells = columns.map(col => `<td class="${col.numeric ? 'num' : ''}">${col.render(row)}</td>`).join('');
          return `<tr>${cells}${actions ? `<td class="row-actions">${actions(row)}</td>` : ''}</tr>`;
        }).join('')
      : `<tr><td colspan="${columns.length + (actions ? 1 : 0)}"><div class="empty-state"><p>${emptyMessage || 'Nothing here yet.'}</p></div></td></tr>`;

    container.innerHTML = `<div class="table-scroll"><table class="dt"><thead><tr>${thHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`;

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

  return { render };
})();
