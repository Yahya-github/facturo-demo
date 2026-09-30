// Loaded last: initial data load and first render.

document.addEventListener('DOMContentLoaded', async () => {
  // Accueil-shaped skeleton while data loads (a History deep link keeps the spinner).
  const main = document.getElementById('main-content');
  if (main && !location.hash) main.innerHTML = renderHomeSkeleton();
  await Promise.all([loadData(), checkCapabilities(), loadSyncStatus(), loadVersionInfo()]);
  // Once, on a root render() never replaces — see the note above the widget.
  bindAutocomplete();
  navigate(initialPage());
  // Fire and forget: at most one GitHub check per session, never blocks startup.
  backgroundUpdateCheck();
  if (!state.pdfAvailable) {
    toast(ui.i18n.t('boot.pdf_disabled'), 'error');
  }
});
