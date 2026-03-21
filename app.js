(() => {
  const doc = document.documentElement;
  const progress = document.querySelector('.scroll-progress-bar');
  const cursor = document.querySelector('.cursor-glow');
  const revealTargets = document.querySelectorAll(
    '.hero-card, .panel, .project-card, .writing-card, .timeline-item, .quote-box, .hero-summary-card, .article-header, .article-body, .author-bio, .visual-panel'
  );

  const navLinks = [...document.querySelectorAll('.nav a[href^="#"], .nav a[href*="index.html#"]')];
  const sections = [...document.querySelectorAll('main section[id]')];

  const updateProgress = () => {
    const h = doc.scrollHeight - window.innerHeight;
    const ratio = h > 0 ? window.scrollY / h : 0;
    if (progress) progress.style.transform = `scaleX(${Math.min(1, Math.max(0, ratio))})`;
  };

  const updateActiveNav = () => {
    const y = window.scrollY + 140;
    let activeId = '';
    for (const section of sections) {
      if (section.offsetTop <= y) activeId = section.id;
    }
    navLinks.forEach(link => {
      const href = link.getAttribute('href') || '';
      const id = href.includes('#') ? href.split('#')[1] : '';
      link.classList.toggle('is-active', !!activeId && id === activeId);
    });
  };

  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      }
    }, { threshold: 0.14, rootMargin: '0px 0px -8% 0px' });

    revealTargets.forEach((el, i) => {
      el.classList.add('reveal');
      el.style.setProperty('--reveal-delay', `${(i % 8) * 35}ms`);
      observer.observe(el);
    });
  } else {
    revealTargets.forEach(el => el.classList.add('is-visible'));
  }

  let mx = window.innerWidth * 0.5;
  let my = window.innerHeight * 0.25;
  let tx = mx;
  let ty = my;
  const loop = () => {
    mx += (tx - mx) * 0.08;
    my += (ty - my) * 0.08;
    if (cursor) cursor.style.transform = `translate(${mx - 260}px, ${my - 260}px)`;
    requestAnimationFrame(loop);
  };
  loop();

  window.addEventListener('pointermove', (e) => {
    tx = e.clientX;
    ty = e.clientY;
  }, { passive: true });

  window.addEventListener('scroll', () => {
    updateProgress();
    updateActiveNav();
  }, { passive: true });

  updateProgress();
  updateActiveNav();
})();
