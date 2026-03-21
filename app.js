const curveBase = [
  { shock: 2, loss: 1.8 }, { shock: 4, loss: 3.5 }, { shock: 6, loss: 4.9 },
  { shock: 8, loss: 6.5 }, { shock: 10, loss: 8.1 }, { shock: 12, loss: 9.8 },
  { shock: 14, loss: 11.2 }, { shock: 16, loss: 16.9 }, { shock: 18, loss: 21.7 },
  { shock: 20, loss: 25.8 }, { shock: 22, loss: 27.1 }, { shock: 24, loss: 28.2 },
  { shock: 26, loss: 29.4 }, { shock: 28, loss: 30.5 }, { shock: 30, loss: 34.3 }
];

const nodes = [
  { id: 'Atlas', x: 120, y: 250, r: 24, type: 'fund', exposures: ['CHIP 0.24', 'GRID 0.18', 'PORT 0.12'] },
  { id: 'Vector', x: 245, y: 120, r: 32, type: 'fund', exposures: ['AERO 0.26', 'CHIP 0.20', 'GRID 0.15'] },
  { id: 'North', x: 695, y: 240, r: 28, type: 'fund', exposures: ['AERO 0.20', 'PORT 0.23', 'RAIL 0.17'] },
  { id: 'Summit', x: 545, y: 430, r: 26, type: 'fund', exposures: ['PORT 0.25', 'GRID 0.16', 'RAIL 0.10'] },
  { id: 'Blue', x: 605, y: 130, r: 28, type: 'fund', exposures: ['AERO 0.18', 'PORT 0.17', 'RAIL 0.14'] },
  { id: 'CHIP', x: 370, y: 210, r: 20, type: 'asset' },
  { id: 'AERO', x: 470, y: 120, r: 20, type: 'asset' },
  { id: 'PORT', x: 500, y: 285, r: 20, type: 'asset' },
  { id: 'GRID', x: 330, y: 405, r: 20, type: 'asset' },
  { id: 'RAIL', x: 830, y: 470, r: 20, type: 'asset' }
];

const links = [
  ['Atlas', 'CHIP'], ['Atlas', 'GRID'], ['Atlas', 'PORT'],
  ['Vector', 'CHIP'], ['Vector', 'AERO'], ['Vector', 'GRID'], ['Vector', 'PORT'],
  ['North', 'AERO'], ['North', 'PORT'], ['North', 'RAIL'], ['North', 'GRID'],
  ['Summit', 'PORT'], ['Summit', 'GRID'], ['Summit', 'RAIL'], ['Summit', 'AERO'],
  ['Blue', 'AERO'], ['Blue', 'PORT'], ['Blue', 'RAIL'], ['Blue', 'CHIP']
].map(([a, b]) => ({ source: a, target: b }));

function interpLoss(shock) {
  for (let i = 0; i < curveBase.length - 1; i++) {
    const a = curveBase[i];
    const b = curveBase[i + 1];
    if (shock >= a.shock && shock <= b.shock) {
      const t = (shock - a.shock) / (b.shock - a.shock);
      return a.loss + t * (b.loss - a.loss);
    }
  }
  return curveBase[curveBase.length - 1].loss;
}

function distressedCount(shock, leverage = 2.4, liquidity = 0.62) {
  const score = shock * leverage * (1.2 - liquidity);
  if (score < 10) return 0;
  if (score < 15) return 1;
  if (score < 19) return 2;
  if (score < 23) return 3;
  return 4;
}

function createSVG(tag, attrs = {}) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  return el;
}

function buildCurve(svgId, activeShock, lossScaleMultiplier = 1) {
  const svg = document.getElementById(svgId);
  if (!svg) return;
  svg.innerHTML = '';
  const width = svg.viewBox.baseVal.width || 520;
  const height = svg.viewBox.baseVal.height || 240;
  const pad = { l: 36, r: 20, t: 16, b: 26 };
  const maxLoss = 38;
  const x = s => pad.l + ((s - 2) / 28) * (width - pad.l - pad.r);
  const y = l => height - pad.b - ((l * lossScaleMultiplier) / maxLoss) * (height - pad.t - pad.b);

  const defs = createSVG('defs');
  const grad = createSVG('linearGradient', { id: 'curveGradient', x1: '0%', x2: '100%', y1: '0%', y2: '0%' });
  grad.append(createSVG('stop', { offset: '0%', 'stop-color': '#4ea0ff' }));
  grad.append(createSVG('stop', { offset: '100%', 'stop-color': '#9ee8ff' }));
  defs.append(grad);
  svg.append(defs);

  [0, 10, 20, 30].forEach(val => {
    svg.append(createSVG('line', { x1: x(2), x2: x(30), y1: y(val), y2: y(val), class: 'grid-line' }));
  });

  const pts = curveBase.map(d => [x(d.shock), y(d.loss)]);
  const dPath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p[0]} ${p[1]}`).join(' ');
  const areaPath = `${dPath} L ${x(30)} ${height - pad.b} L ${x(2)} ${height - pad.b} Z`;
  svg.append(createSVG('path', { d: areaPath, class: 'curve-area' }));
  svg.append(createSVG('path', { d: dPath, class: 'curve-line' }));

  const loss = interpLoss(activeShock) * lossScaleMultiplier;
  const activeX = x(activeShock);
  const activeY = y(loss / lossScaleMultiplier);
  svg.append(createSVG('line', { x1: activeX, x2: activeX, y1: pad.t, y2: height - pad.b, class: 'grid-line' }));
  svg.append(createSVG('circle', { cx: activeX, cy: activeY, r: 5.5, class: 'curve-dot' }));

  const label = createSVG('text', { x: activeX + 10, y: activeY - 10, class: 'curve-text' });
  label.textContent = `${activeShock}% → ${loss.toFixed(1)}%`;
  svg.append(label);
}

function buildMiniNetwork(svgId, shock) {
  const svg = document.getElementById(svgId);
  if (!svg) return;
  svg.innerHTML = '';
  const miniNodes = [
    { id: 'F1', x: 100, y: 118, type: 'fund' },
    { id: 'F2', x: 200, y: 54, type: 'fund' },
    { id: 'A1', x: 248, y: 110, type: 'asset' },
    { id: 'A2', x: 330, y: 66, type: 'asset' },
    { id: 'F3', x: 395, y: 132, type: 'fund' },
    { id: 'F4', x: 302, y: 194, type: 'fund' },
  ];
  const miniLinks = [['F1','A1'],['F2','A1'],['F2','A2'],['F3','A1'],['F3','A2'],['F4','A1'],['F4','A2']];
  miniLinks.forEach(([a,b], idx) => {
    const na = miniNodes.find(n => n.id === a);
    const nb = miniNodes.find(n => n.id === b);
    const active = idx < Math.max(2, Math.floor((shock - 2) / 5));
    svg.append(createSVG('line', {
      x1: na.x, y1: na.y, x2: nb.x, y2: nb.y,
      class: `edge ${active ? 'active' : ''}`
    }));
  });
  miniNodes.forEach((n, idx) => {
    const state = shock < 14 ? 'stable' : shock < 20 ? (idx < 2 ? 'stressed' : 'stable') : (idx < 3 ? 'failed' : 'stressed');
    svg.append(createSVG('circle', { cx: n.x, cy: n.y, r: n.type === 'asset' ? 14 : 18, class: `node ${n.type === 'asset' ? 'asset' : state}` }));
    const t = createSVG('text', { x: n.x, y: n.y + 34, 'text-anchor': 'middle', class: 'node-label' });
    t.textContent = n.id;
    svg.append(t);
  });
}

function updateHero() {
  const slider = document.getElementById('heroShock');
  const shock = Number(slider.value);
  const loss = interpLoss(shock);
  const funds = distressedCount(shock);
  document.getElementById('heroShockValue').textContent = `${shock}%`;
  document.getElementById('heroLossValue').textContent = `${loss.toFixed(1)}%`;
  document.getElementById('heroFundsValue').textContent = `${funds}`;
  buildCurve('heroCurve', shock);
  buildMiniNetwork('heroNetwork', shock);
}

function buildFlagship() {
  const svg = document.getElementById('flagshipNetwork');
  const tooltip = document.getElementById('networkTooltip');
  const breakSequence = document.getElementById('breakSequence');
  if (!svg) return;
  svg.innerHTML = '';
  breakSequence.innerHTML = '';

  const failedOrder = ['CHIP', 'Atlas', 'North', 'RAIL'];
  const lookup = Object.fromEntries(nodes.map(n => [n.id, n]));

  links.forEach(link => {
    const a = lookup[link.source];
    const b = lookup[link.target];
    const failed = failedOrder.includes(link.source) || failedOrder.includes(link.target);
    svg.append(createSVG('line', {
      x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      class: `edge ${failed ? 'failed' : 'active'}`
    }));
  });

  nodes.forEach((n, i) => {
    const state = n.type === 'asset'
      ? 'asset'
      : failedOrder.includes(n.id) ? 'failed' : (['Vector', 'Summit', 'Blue'].includes(n.id) ? 'stressed' : 'stable');

    const ring = createSVG('circle', { cx: n.x, cy: n.y, r: n.r + 12, class: 'node ring' });
    svg.append(ring);

    const c = createSVG('circle', { cx: n.x, cy: n.y, r: n.r, class: `node ${state}` });
    c.dataset.id = n.id;
    svg.append(c);

    const t = createSVG('text', {
      x: n.x,
      y: n.y + n.r + 24,
      'text-anchor': 'middle',
      class: 'node-label'
    });
    t.textContent = n.id;
    svg.append(t);

    if (n.exposures) {
      c.addEventListener('mouseenter', () => {
        tooltip.hidden = false;
        tooltip.innerHTML = `<strong>${n.id}</strong><br>${n.exposures.join('<br>')}`;
      });
      c.addEventListener('mousemove', e => {
        const rect = svg.getBoundingClientRect();
        tooltip.style.left = `${e.clientX - rect.left + 18}px`;
        tooltip.style.top = `${e.clientY - rect.top + 18}px`;
      });
      c.addEventListener('mouseleave', () => { tooltip.hidden = true; });
    }
  });

  failedOrder.forEach(name => {
    const pill = document.createElement('span');
    pill.textContent = name;
    breakSequence.append(pill);
  });

  buildCurve('flagshipCurve', 18);
}

function buildSimulatorNetwork(result) {
  const svg = document.getElementById('simNetwork');
  if (!svg) return;
  svg.innerHTML = '';
  const lookup = Object.fromEntries(nodes.map(n => [n.id, n]));

  links.forEach(link => {
    const a = lookup[link.source];
    const b = lookup[link.target];
    const aState = result.states[link.source] || 'stable';
    const bState = result.states[link.target] || 'stable';
    const cls = (aState === 'failed' || bState === 'failed') ? 'failed' : ((aState === 'stressed' || bState === 'stressed') ? 'active' : 'edge');
    svg.append(createSVG('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: `edge ${cls}` }));
  });

  nodes.forEach(n => {
    const state = n.type === 'asset' ? 'asset' : (result.states[n.id] || 'stable');
    svg.append(createSVG('circle', { cx: n.x, cy: n.y, r: n.r + 12, class: 'node ring' }));
    svg.append(createSVG('circle', { cx: n.x, cy: n.y, r: n.r, class: `node ${state}` }));
    const t = createSVG('text', { x: n.x, y: n.y + n.r + 24, 'text-anchor': 'middle', class: 'node-label' });
    t.textContent = n.id;
    svg.append(t);
  });
}

function runSimulator() {
  const lev = Number(document.getElementById('levRange').value);
  const shock = Number(document.getElementById('shockRange').value);
  const liq = Number(document.getElementById('liqRange').value);

  document.getElementById('levValue').textContent = `${lev.toFixed(1)}x`;
  document.getElementById('shockValue').textContent = `${shock}%`;
  document.getElementById('liqValue').textContent = liq.toFixed(2);

  const rawLoss = interpLoss(shock);
  const loss = rawLoss * (0.65 + lev * 0.18) * (1.18 - liq * 0.55);
  const distress = distressedCount(shock, lev, liq);

  let mode = 'Localized stress';
  let commentary = 'Forced selling remains containable. The system is stressed, not broken.';
  if (loss > 19 || distress >= 3) {
    mode = 'Cascade ignition';
    commentary = 'Margin breaches now amplify price moves. The second-order effects matter as much as the initial shock.';
  }
  if (loss > 28 || distress >= 4) {
    mode = 'Systemic damage';
    commentary = 'Liquidity is no longer cushioning the network. Loss is propagating through overlapping balance sheets.';
  }

  document.getElementById('simLoss').textContent = `${loss.toFixed(1)}%`;
  document.getElementById('simDistress').textContent = `${distress}`;
  document.getElementById('simMode').textContent = mode;
  document.getElementById('simCommentary').textContent = commentary;

  const fundNames = ['Atlas', 'Vector', 'North', 'Summit', 'Blue'];
  const states = {};
  fundNames.forEach((name, idx) => {
    const threshold = 10 + idx * 2.7 - lev * 1.8 + liq * 3.2;
    const failThreshold = threshold + 6.3 - liq * 2.1;
    const pressure = shock + lev * 3.6 + (1 - liq) * 9.5 + idx * 0.8;
    states[name] = pressure > failThreshold ? 'failed' : pressure > threshold ? 'stressed' : 'stable';
  });
  ['CHIP', 'AERO', 'PORT', 'GRID', 'RAIL'].forEach((asset, idx) => {
    states[asset] = shock > (12 + idx * 2.5) ? 'asset' : 'asset';
  });

  buildSimulatorNetwork({ states });
  buildCurve('simCurve', Math.min(30, shock + lev * 2.5), 0.92 + (1 - liq) * 0.2);
}

function init() {
  updateHero();
  buildFlagship();
  runSimulator();

  document.getElementById('heroShock')?.addEventListener('input', updateHero);
  document.getElementById('levRange')?.addEventListener('input', runSimulator);
  document.getElementById('shockRange')?.addEventListener('input', runSimulator);
  document.getElementById('liqRange')?.addEventListener('input', runSimulator);
}

document.addEventListener('DOMContentLoaded', init);
