(() => {
  const d = document;
  const isTouchLike = window.matchMedia('(pointer: coarse)').matches || 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  const protectedSelector = 'img, .image-protected, .portrait-frame';

  const isProtectedTarget = (target) => {
    return !!(target && target.closest && target.closest(protectedSelector));
  };

  // Compatibility-first deterrence only.
  // No devtools detection, no lock screens, no viewport heuristics.

  d.addEventListener('dragstart', (event) => {
    if (isProtectedTarget(event.target)) {
      event.preventDefault();
    }
  }, { capture: true });

  d.addEventListener('contextmenu', (event) => {
    if (isProtectedTarget(event.target)) {
      event.preventDefault();
    }
  }, { capture: true });

  // Keep keyboard interference minimal and desktop-only.
  if (!isTouchLike) {
    d.addEventListener('keydown', (event) => {
      const key = (event.key || '').toLowerCase();
      const blocked = [
        (event.ctrlKey || event.metaKey) && (key === 's' || key === 'u'),
        key === 'f12'
      ].some(Boolean);

      if (blocked) {
        event.preventDefault();
        event.stopPropagation();
      }
    }, { capture: true });
  }
})();
