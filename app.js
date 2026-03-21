(() => {
  const root = document.documentElement;
  const progress = document.querySelector('.progress-bar');
  const navLinks = [...document.querySelectorAll('.nav a[href^="#"], .nav a[href*="index.html#"]')];
  const revealTargets = [...document.querySelectorAll('.hero-card, .hero-summary-card, .panel, .project-card, .writing-card, .timeline-item, .quote-box, .article-header, .article-body, .author-bio, .visual-panel')];

  const setProgress = () => {
    const scrollTop = window.scrollY;
    const scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
    const pct = scrollHeight > 0 ? `${(scrollTop / scrollHeight) * 100}%` : '0%';
    root.style.setProperty('--scroll-progress', pct);
    if (progress) progress.style.width = pct;
  };

  revealTargets.forEach((el, i) => {
    el.classList.add('reveal');
    el.style.transitionDelay = `${Math.min(i * 35, 240)}ms`;
  });

  const io = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) entry.target.classList.add('is-visible');
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });

  revealTargets.forEach(el => io.observe(el));

  const sectionIds = ['about', 'flagship', 'work', 'writing', 'timeline', 'contact'];
  const sections = sectionIds
    .map(id => document.getElementById(id))
    .filter(Boolean);

  if (sections.length && navLinks.length) {
    const sectionObserver = new IntersectionObserver((entries) => {
      const visible = entries
        .filter(entry => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      navLinks.forEach(link => {
        const href = link.getAttribute('href') || '';
        const active = href.endsWith(`#${visible.target.id}`);
        link.classList.toggle('is-active', active);
      });
    }, { threshold: 0.45, rootMargin: '-10% 0px -40% 0px' });

    sections.forEach(section => sectionObserver.observe(section));
  }

  setProgress();
  window.addEventListener('scroll', setProgress, { passive: true });
  window.addEventListener('resize', setProgress);
})();
