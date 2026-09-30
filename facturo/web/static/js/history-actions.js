// ── HISTORY: actions ────────────────────────────────────
// Row "..." menu, right-click menu, deferred delete with a Cancel toast,
// date-range presets, header sorting, paging and the "/" search shortcut.

const HIST_UNDO_MS = 6000;
/** Deletions confirmed by the user and waiting out the undo window: id -> {timer, file}. */
const histPendingDeletes = new Map();

const histFactureById = id => state.factures.find(f => f.id === Number(id));

/** Actions shared by the row button and the right-click menu. */
function histRowItems(f) {
  return [
    { label: ui.i18n.t('action.edit'), icon: 'pencil', onSelect: () => editFacture(f.id) },
    { label: ui.i18n.t('action.download_excel'), icon: 'download', onSelect: () => downloadFacture(f.fichier) },
    { label: ui.i18n.t('action.download_pdf'), icon: 'file-text', onSelect: () => downloadFacturePdf(document.createElement('button'), f.fichier) },
    { separator: true },
    { label: ui.i18n.t(f.paye ? 'action.mark_unpaid' : 'action.mark_paid'), icon: 'circle-check', onSelect: () => togglePaid(f.id, !f.paye) },
    { separator: true },
    { label: ui.i18n.t('action.delete'), icon: 'trash-2', destructive: true, onSelect: () => histDeleteFacture(f.id) },
  ];
}

/** Attach the "..." menus of any row that does not have one yet. */
function bindHistoryRows() {
  document.querySelectorAll('#hist-results [data-row-menu]').forEach(btn => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = '1';
    ui.menu.attach(btn, () => {
      const f = histFactureById(btn.dataset.rowMenu);
      return f ? histRowItems(f) : [];
    });
  });
  const region = document.getElementById('hist-results');
  if (region && !region.dataset.ctxBound) {
    region.dataset.ctxBound = '1';
    ui.contextMenu.attach(region, 'tr[data-facture-id]', row => {
      const f = histFactureById(row.dataset.factureId);
      return f ? histRowItems(f) : null;
    });
  }
}

ui.hydrate.register(bindHistoryRows);

// ── Delete with undo ────────────────────────────────────

function histRefreshViews() {
  if (state.page === 'history' || state.page === 'home') render();
}

async function histCommitDelete(id) {
  const pending = histPendingDeletes.get(id);
  if (!pending) return;
  histPendingDeletes.delete(id);
  try {
    await api('DELETE', `/api/factures/${id}`);
    await loadData();
  } catch (e) {
    pending.restore();
    toast(e.message, 'error');
    return;
  }
  histRefreshViews();
}

/**
 * Confirm, then hide the invoice at once and give the user a few seconds to
 * take it back. The server call (which also deletes the Excel/PDF files, and
 * cannot be undone) only happens once that window closes.
 */
async function histDeleteFacture(id) {
  const f = histFactureById(id);
  if (!f) return;
  const ok = await ui.alertDialog({
    title: ui.i18n.t('history.delete.title'),
    description: ui.i18n.t('history.delete.desc', { number: f.numero }),
    confirmLabel: ui.i18n.t('action.delete'), destructive: true,
  });
  if (!ok) return;
  const index = Math.max(0, state.factures.indexOf(f));
  state.factures = state.factures.filter(x => x.id !== f.id);
  const restore = () => {
    if (!state.factures.some(x => x.id === f.id)) {
      state.factures = [...state.factures.slice(0, index), f, ...state.factures.slice(index)];
    }
    histRefreshViews();
  };
  let handle = null;
  const timer = setTimeout(() => {
    if (handle) handle.dismiss();
    histCommitDelete(f.id);
  }, HIST_UNDO_MS);
  histPendingDeletes.set(f.id, { timer, restore });
  histRefreshViews();
  handle = toast(ui.i18n.t('history.deleted', { number: f.numero }), 'info', {
    duration: HIST_UNDO_MS + 1000,
    action: {
      label: ui.i18n.t('action.cancel'),
      onClick() { clearTimeout(timer); histPendingDeletes.delete(f.id); restore(); },
    },
  });
}

// Leaving the page during the undo window: the user already confirmed, so finish the job.
window.addEventListener('pagehide', () => {
  histPendingDeletes.forEach((_, id) => {
    fetch(`/api/factures/${id}`, { method: 'DELETE', keepalive: true }).catch(() => {});
  });
});

// ── Date presets ────────────────────────────────────────

const pad2 = n => String(n).padStart(2, '0');
const isoOf = d => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

/**
 * Inclusive range for a preset, in local time.
 * @param {'month'|'30d'|'year'|'clear'} kind
 * @param {Date} [now]
 * @returns {{du: string, au: string}}
 */
function histPresetRange(kind, now = new Date()) {
  const y = now.getFullYear();
  const m = now.getMonth();
  if (kind === 'month') return { du: isoOf(new Date(y, m, 1)), au: isoOf(new Date(y, m + 1, 0)) };
  if (kind === '30d') return { du: isoOf(new Date(y, m, now.getDate() - 29)), au: isoOf(now) };
  if (kind === 'year') return { du: isoOf(new Date(y, 0, 1)), au: isoOf(new Date(y, 11, 31)) };
  return { du: '', au: '' };
}

const HIST_PRESETS = ['month', '30d', 'year', 'clear'];

function histApplyPreset(kind) {
  const { du, au } = histPresetRange(kind);
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
  set('flt-du', du);
  set('flt-au', au);
  histOnControlChange();
}

function histOpenPresets(btn) {
  let layer = null;
  const pick = kind => { histApplyPreset(kind); if (layer) layer.close(true); };
  const content = ui.h('div', { class: 'flt-preset-list' },
    HIST_PRESETS.map(kind => ui.h('button', {
      type: 'button', class: 'flt-preset', 'data-preset': kind, onclick: () => pick(kind),
    }, ui.i18n.t(`history.preset.${kind}`))));
  layer = ui.popover.toggle(btn, { content, side: 'bottom', align: 'end', label: ui.i18n.t('history.filter.presets'), className: 'flt-preset-pop' });
}

// ── Sorting, paging, shortcut ───────────────────────────

function histSortBy(tri) {
  const sel = document.getElementById('flt-tri');
  if (!sel) return;
  sel.value = tri;
  histOnControlChange();
}

function histGoPage(page) {
  state.histPage = Number(page) || 1;
  refreshHistoryResults();
  const region = document.getElementById('hist-results');
  if (region) region.scrollIntoView({ block: 'nearest' });
}

/** "/" focuses the search box unless the user is already typing somewhere. */
document.addEventListener('keydown', e => {
  if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey || state.page !== 'history') return;
  const t = e.target;
  if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
  if (document.querySelector('.modal-overlay, .popover, .menu')) return;
  const q = document.getElementById('flt-q');
  if (!q) return;
  e.preventDefault();
  q.focus();
  q.select();
});
