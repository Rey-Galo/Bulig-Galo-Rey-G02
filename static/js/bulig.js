// Small progressive enhancements. Every page works the same with this file missing.
(() => {
  // Busy state on submit: stops double posts and shows the request is going.
  document.querySelectorAll('button[data-busy-label]').forEach((btn) => {
    const idle = btn.innerHTML;
    btn.form.addEventListener('submit', () => {
      btn.disabled = true;
      btn.setAttribute('aria-busy', 'true');
      btn.innerHTML = '<span class="spinner-border" aria-hidden="true"></span>' + btn.dataset.busyLabel;
    });
    // Restore when the page comes back from the back/forward cache.
    addEventListener('pageshow', (e) => {
      if (e.persisted) {
        btn.disabled = false;
        btn.removeAttribute('aria-busy');
        btn.innerHTML = idle;
      }
    });
  });
})();
