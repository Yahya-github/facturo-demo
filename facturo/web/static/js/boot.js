// Loaded last: initial data load and first render.

document.addEventListener('DOMContentLoaded', async () => {
  await Promise.all([loadData(), checkCapabilities(), loadSyncStatus(), loadVersionInfo()]);
  // Once, on a root render() never replaces — see the note above the widget.
  bindAutocomplete();
  navigate(initialPage());
  // Fire and forget: at most one GitHub check per session, never blocks startup.
  backgroundUpdateCheck();
  if (!state.pdfAvailable) {
    toast("Export PDF désactivé : installez LibreOffice (gratuit) pour l'activer. L'export Excel fonctionne normalement.", 'error');
  }
});
