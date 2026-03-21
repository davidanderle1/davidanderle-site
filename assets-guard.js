document.addEventListener('DOMContentLoaded', () => {
  const yearTargets = document.querySelectorAll('[data-current-year]');
  const year = new Date().getFullYear();
  yearTargets.forEach(el => { el.textContent = year; });
});
