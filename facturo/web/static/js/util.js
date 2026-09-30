// Pure helpers shared by every page script: HTML escaping, attribute-safe
// values, API error normalisation. No DOM. Loaded first as a plain <script>
// (attaches globals) and importable from Node for tests/js/util.test.mjs.

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    Object.assign(root, factory());
  }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const HTML_ENTITIES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

  /**
   * Escape text for HTML content or a quoted attribute value.
   * null/undefined/'' -> ''; numeric 0 -> '0'.
   * @param {*} value
   * @returns {string}
   */
  function esc(value) {
    if (value === null || value === undefined) return '';
    return String(value).replace(/[&<>"']/g, ch => HTML_ENTITIES[ch]);
  }

  /** Same escaping, named for use inside attributes. */
  function escAttr(value) {
    return esc(value);
  }

  /** A finite number as text for value="..."; anything else becomes ''. */
  function numAttr(value) {
    if (value === null || value === undefined) return '';
    if (typeof value === 'string' && value.trim() === '') return '';
    const n = Number(value);
    return Number.isFinite(n) ? String(n) : '';
  }

  /** A YYYY-MM-DD date for value="..."; anything else becomes ''. */
  function dateAttr(value) {
    return typeof value === 'string' && ISO_DATE.test(value) ? value : '';
  }

  /**
   * Active-language text when the engine is loaded; the French fallback keeps
   * this file usable on its own (Node tests, a page without i18n.js).
   */
  function localized(key, fallback) {
    const i18n = typeof globalThis !== 'undefined' && globalThis.ui && globalThis.ui.i18n;
    return i18n && i18n.has(key) ? i18n.t(key) : fallback;
  }

  /**
   * Human message from a FastAPI error body. `detail` is a string for
   * HTTPException and an array of {msg, loc} for 422 validation errors.
   * @param {{detail?: string|Array<{msg?: string}>}|null} body
   * @returns {string}
   */
  function errorMessage(body) {
    const detail = body && body.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (Array.isArray(detail)) {
      const msgs = detail.map(d => (d && d.msg) || (typeof d === 'string' ? d : '')).filter(Boolean);
      if (msgs.length) return msgs.join(' ; ');
    }
    return localized('error.server', 'Erreur serveur');
  }

  /** fetch() rejects with TypeError when the server cannot be reached. */
  function networkErrorMessage(err) {
    if (err instanceof TypeError) return localized('error.network', 'Connexion au serveur impossible');
    return (err && err.message) || localized('error.generic', 'Erreur');
  }

  const isBlank = v => v === null || v === undefined || String(v).trim() === '';
  const isNotNumber = v => isBlank(v) || !Number.isFinite(Number(v));

  /**
   * Labels (N° billet, or the 1-based position when it has none) of billets
   * whose quantite or taux is blank. 0 is a valid value.
   * @param {Array<{numero_billet?: string, quantite?: *, taux?: *}>} billets
   * @returns {string[]}
   */
  function incompleteBillets(billets) {
    const out = [];
    billets.forEach((b, i) => {
      if (isNotNumber(b.quantite) || isNotNumber(b.taux)) {
        out.push(isBlank(b.numero_billet) ? String(i + 1) : String(b.numero_billet).trim());
      }
    });
    return out;
  }

  return { esc, escAttr, numAttr, dateAttr, errorMessage, networkErrorMessage, incompleteBillets };
});
