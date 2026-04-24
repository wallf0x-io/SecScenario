/* FX layer: button ripple + subtle interactive polish. */
(function () {
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  function addRipple(e) {
    var target = e.currentTarget;
    var rect = target.getBoundingClientRect();
    var ripple = document.createElement('span');
    ripple.className = 'ripple';
    var size = Math.max(rect.width, rect.height) * 1.4;
    ripple.style.width = ripple.style.height = size + 'px';
    ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
    ripple.style.top  = (e.clientY - rect.top  - size / 2) + 'px';
    target.appendChild(ripple);
    setTimeout(function () { ripple.remove(); }, 650);
  }

  function wire() {
    document.querySelectorAll(
      '.btn, .btn-primary, .source-tab, .stat-tile, .theme-toggle'
    ).forEach(function (el) {
      if (el.dataset.rippleWired) return;
      el.dataset.rippleWired = '1';
      el.addEventListener('pointerdown', addRipple);
    });
  }
  wire();
  // Re-wire after dynamic content (source-tab switches etc.)
  var mo = new MutationObserver(wire);
  mo.observe(document.body, { childList: true, subtree: true });
})();
