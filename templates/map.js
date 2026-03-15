// Dotted World Map — matches WorldMap React component style
(async function () {
  const wrapper = document.querySelector('.bg-map');
  if (!wrapper || typeof topojson === 'undefined') return;

  /* ── Match container size exactly ── */
  const rect   = wrapper.getBoundingClientRect();
  const W      = Math.max(rect.width,  600);
  const H      = Math.max(rect.height, 400);

  /* ── EU-focused projection ── */
  const LON_MIN = -30, LON_MAX = 48;
  const LAT_MIN = 12,  LAT_MAX = 72;
  const project = (lng, lat) => ({
    x: (lng - LON_MIN) / (LON_MAX - LON_MIN) * W,
    y: (LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * H
  });

  /* ── EU27 member state ISO numeric IDs ── */
  const EU_IDS = new Set([
    40,56,100,191,196,203,208,233,246,250,
    276,300,348,372,380,428,440,442,470,528,
    616,620,642,703,705,724,752
  ]);

  /* ── Canvas ── */
  const canvas = document.createElement('canvas');
  canvas.width  = W;
  canvas.height = H;
  Object.assign(canvas.style, {
    position: 'absolute', inset: '0',
    width: '100%', height: '100%'
  });
  wrapper.appendChild(canvas);
  const ctx = canvas.getContext('2d');

  /* ── Load world topology ── */
  let world;
  try {
    world = await fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json').then(r => r.json());
  } catch (e) { return; }

  /* ── Render land to offscreen canvas ── */
  const off  = document.createElement('canvas');
  off.width  = W;
  off.height = H;
  const oCtx = off.getContext('2d');
  oCtx.fillStyle = '#fff';

  const countries = topojson.feature(world, world.objects.countries);
  countries.features.filter(f => EU_IDS.has(+f.id)).forEach(({ geometry: geo }) => {
    if (!geo) return;
    const polys = geo.type === 'Polygon'      ? [geo.coordinates]
                : geo.type === 'MultiPolygon' ?  geo.coordinates
                : [];
    polys.forEach(poly => {
      oCtx.beginPath();
      poly.forEach(ring => {
        ring.forEach(([lng, lat], i) => {
          const { x, y } = project(lng, lat);
          i === 0 ? oCtx.moveTo(x, y) : oCtx.lineTo(x, y);
        });
        oCtx.closePath();
      });
      oCtx.fill();
    });
  });

  /* ── Sample pixels → small dense dots ── */
  const img    = oCtx.getImageData(0, 0, W, H);
  const STEP   = 5;   // dense grid like dotted-map
  const RADIUS = 1.1;

  ctx.fillStyle = 'rgba(255,255,255,0.22)';
  for (let x = STEP / 2; x < W; x += STEP) {
    for (let y = STEP / 2; y < H; y += STEP) {
      const i = (Math.floor(y) * W + Math.floor(x)) * 4;
      if (img.data[i] > 128) {
        ctx.beginPath();
        ctx.arc(x, y, RADIUS, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  /* ── Top/bottom fade ── */
  const fadeV = ctx.createLinearGradient(0, 0, 0, H);
  fadeV.addColorStop(0,    'rgba(13,17,32,1)');
  fadeV.addColorStop(0.05, 'rgba(13,17,32,0)');
  fadeV.addColorStop(0.95, 'rgba(13,17,32,0)');
  fadeV.addColorStop(1,    'rgba(13,17,32,1)');
  ctx.fillStyle = fadeV;
  ctx.fillRect(0, 0, W, H);

  /* ── Left fade — covers search card area ── */
  const searchCardFrac = 480 / W;  // cover search card area
  const fadeH = ctx.createLinearGradient(0, 0, W * (searchCardFrac + 0.10), 0);
  fadeH.addColorStop(0,                      'rgba(13,17,32,1)');
  fadeH.addColorStop(searchCardFrac,         'rgba(13,17,32,0.88)');
  fadeH.addColorStop(searchCardFrac + 0.10,  'rgba(13,17,32,0)');
  ctx.fillStyle = fadeH;
  ctx.fillRect(0, 0, W * (searchCardFrac + 0.12), H);

  /* ── SVG overlay for arcs + city dots ── */
  const NS  = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('preserveAspectRatio', 'none');
  Object.assign(svg.style, {
    position: 'absolute', inset: '0',
    width: '100%', height: '100%',
    pointerEvents: 'none'
  });
  wrapper.appendChild(svg);

  /* arc gradient */
  const defs = document.createElementNS(NS, 'defs');
  defs.innerHTML = `
    <linearGradient id="arc-g" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="white" stop-opacity="0"/>
      <stop offset="5%"   stop-color="#3d5080" stop-opacity="1"/>
      <stop offset="95%"  stop-color="#3d5080" stop-opacity="1"/>
      <stop offset="100%" stop-color="white"   stop-opacity="0"/>
    </linearGradient>`;
  svg.appendChild(defs);

  /* 4 cities: home + 3 target universities */
  const CITIES = [
    { lat: 40.64, lng:  22.94 }, // Thessaloniki (home)
    { lat: 40.42, lng:  -3.70 }, // Madrid (UPM)
    { lat: 52.01, lng:   4.36 }, // Delft (TU Delft)
    { lat: 60.17, lng:  24.94 }, // Espoo (Aalto)
  ];

  /* draw arcs from Thessaloniki to each city */
  CITIES.slice(1).forEach((city, idx) => {
    const s  = project(CITIES[0].lng, CITIES[0].lat);
    const e  = project(city.lng, city.lat);
    const mx = (s.x + e.x) / 2;
    const my = Math.min(s.y, e.y) - 50;

    const path = document.createElementNS(NS, 'path');
    path.setAttribute('d', `M ${s.x} ${s.y} Q ${mx} ${my} ${e.x} ${e.y}`);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', 'url(#arc-g)');
    path.setAttribute('stroke-width', '1');
    path.setAttribute('class', `map-arc arc-${idx}`);
    svg.appendChild(path);
  });

  /* city dots + pulse rings */
  CITIES.forEach(({ lat, lng }, idx) => {
    const { x, y } = project(lng, lat);

    const ring = document.createElementNS(NS, 'circle');
    ring.setAttribute('cx', x); ring.setAttribute('cy', y); ring.setAttribute('r', '2');
    ring.setAttribute('fill', 'none');
    ring.setAttribute('stroke', 'rgba(255,255,255,0.45)');
    ring.setAttribute('stroke-width', '1');
    ring.setAttribute('class', `map-pulse pulse-${idx}`);
    svg.appendChild(ring);

    const dot = document.createElementNS(NS, 'circle');
    dot.setAttribute('cx', x); dot.setAttribute('cy', y); dot.setAttribute('r', '2');
    dot.setAttribute('fill', 'rgba(255,255,255,0.8)');
    svg.appendChild(dot);
  });
})();
