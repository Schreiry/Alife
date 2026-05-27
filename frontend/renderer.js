// Canvas2D renderer for the world map. Receives the live snapshot from
// app.js and draws creatures, food, and a click->select hit test.

const Renderer = (() => {
  const cv = document.getElementById("map");
  const ctx = cv.getContext("2d");

  let state = null;
  let scale = 1;          // tile->px
  let offsetX = 0;
  let offsetY = 0;
  let dpr = 1;
  let selectedId = null;
  let hoveredId = null;
  let onSelect = () => {};
  let onHover = () => {};
  let frameCount = 0;
  let lastFpsT = performance.now();
  let lastFps = 0;

  function resize() {
    dpr = window.devicePixelRatio || 1;
    const rect = cv.getBoundingClientRect();
    cv.width = Math.max(1, Math.floor(rect.width * dpr));
    cv.height = Math.max(1, Math.floor(rect.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    recomputeScale();
    draw();
  }

  function recomputeScale() {
    if (!state) return;
    const rect = cv.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    const ww = state.world.width;
    const wh = state.world.height;
    scale = Math.max(1, Math.floor(Math.min(w / ww, h / wh)));
    offsetX = Math.floor((w - ww * scale) / 2);
    offsetY = Math.floor((h - wh * scale) / 2);
  }

  function update(snapshot) {
    const firstSnap = state === null;
    state = snapshot;
    if (firstSnap) recomputeScale();
    draw();
  }

  function setOnSelect(cb) { onSelect = cb; }
  function setOnHover(cb) { onHover = cb; }

  function getFps() { return lastFps; }

  function draw() {
    frameCount++;
    const now = performance.now();
    if (now - lastFpsT >= 1000) {
      lastFps = Math.round((frameCount * 1000) / (now - lastFpsT));
      frameCount = 0;
      lastFpsT = now;
    }

    const rect = cv.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    ctx.fillStyle = "#06080d";
    ctx.fillRect(0, 0, w, h);
    if (!state) return;

    // World border
    ctx.strokeStyle = "rgba(255,255,255,0.06)";
    ctx.lineWidth = 1;
    ctx.strokeRect(
      offsetX + 0.5, offsetY + 0.5,
      state.world.width * scale, state.world.height * scale,
    );

    // Food: small green squares.
    const food = state.food;
    ctx.fillStyle = "#5ac85a";
    const fs = Math.max(2, scale - 1);
    for (let i = 0; i < food.x.length; i++) {
      const x = offsetX + food.x[i] * scale;
      const y = offsetY + food.y[i] * scale;
      ctx.fillRect(x, y, fs, fs);
    }

    // Creatures: filled circle + optional clan ring.
    const cr = state.creatures;
    const radius = Math.max(2, Math.floor(scale * 0.75));
    const clanColorById = new Map();
    for (const cl of state.clans) clanColorById.set(cl.id, cl.color);

    for (let i = 0; i < cr.ids.length; i++) {
      const cx = offsetX + cr.x[i] * scale + scale / 2;
      const cy = offsetY + cr.y[i] * scale + scale / 2;
      ctx.fillStyle = `rgb(${cr.r[i]},${cr.g[i]},${cr.b[i]})`;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fill();

      const clanId = cr.clan[i];
      if (clanId >= 0 && clanColorById.has(clanId)) {
        const [r, g, b] = clanColorById.get(clanId);
        ctx.strokeStyle = `rgb(${r},${g},${b})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(cx, cy, radius + 1.5, 0, Math.PI * 2);
        ctx.stroke();
      }

      if (cr.ids[i] === selectedId) {
        ctx.strokeStyle = "#f0c864";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(cx, cy, radius + 4, 0, Math.PI * 2);
        ctx.stroke();
      } else if (cr.ids[i] === hoveredId) {
        ctx.strokeStyle = "rgba(240,200,100,0.6)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(cx, cy, radius + 3, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
  }

  function pickAt(px, py) {
    if (!state) return -1;
    const wx = (px - offsetX) / scale;
    const wy = (py - offsetY) / scale;
    if (wx < 0 || wy < 0 || wx > state.world.width || wy > state.world.height) {
      return -1;
    }
    let best = -1;
    let bestD2 = (1.8 * 1.8);
    const cr = state.creatures;
    for (let i = 0; i < cr.ids.length; i++) {
      const dx = cr.x[i] + 0.5 - wx;
      const dy = cr.y[i] + 0.5 - wy;
      const d2 = dx * dx + dy * dy;
      if (d2 < bestD2) { bestD2 = d2; best = i; }
    }
    return best;
  }

  function handleMove(ev) {
    const rect = cv.getBoundingClientRect();
    const px = ev.clientX - rect.left;
    const py = ev.clientY - rect.top;
    const i = pickAt(px, py);
    const newId = i >= 0 ? state.creatures.ids[i] : null;
    if (newId !== hoveredId) {
      hoveredId = newId;
      onHover(newId);
      draw();
    }
  }

  function handleClick(ev) {
    if (!state) return;
    const rect = cv.getBoundingClientRect();
    const i = pickAt(ev.clientX - rect.left, ev.clientY - rect.top);
    if (i >= 0) {
      selectedId = state.creatures.ids[i];
      onSelect(selectedId);
      draw();
    }
  }

  function clearSelection() { selectedId = null; draw(); }

  function init() {
    window.addEventListener("resize", resize);
    cv.addEventListener("click", handleClick);
    cv.addEventListener("mousemove", handleMove);
    cv.addEventListener("mouseleave", () => { hoveredId = null; onHover(null); draw(); });
    resize();
  }

  return { init, update, setOnSelect, setOnHover, clearSelection, getFps };
})();
