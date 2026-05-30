// Canvas2D renderer for the world map.
//
// Smoothness: the WebSocket delivers snapshots at ~20-30 Hz, irregularly. We
// run a continuous requestAnimationFrame loop (up to the display refresh, e.g.
// 144 Hz) and INTERPOLATE creature positions between the two latest snapshots,
// so motion stays smooth even if data arrives in bursts.
//
// Camera: a single transform (baseScale * zoom, plus a screen-space cam
// offset) maps world tiles -> screen pixels. Everything (creatures, food,
// territory overlay, hit-testing) goes through it, so zoom + pan are
// consistent. Zoom eases toward a target and stays anchored under the cursor;
// pan is drag. None of this touches the simulation.

const Renderer = (() => {
  const cv = document.getElementById("map");
  const ctx = cv.getContext("2d");

  // Double-buffered snapshots for interpolation.
  let prevSnap = null;
  let curSnap = null;
  let prevT = 0;
  let curT = 0;
  let interval = 50;
  let prevPosById = new Map();
  let clanColorById = new Map();

  // ---- view layers (observation only) ----
  let colorMode = "default";                 // default | clan | species | hunger
  const overlays = { territory: false, borders: false, ecology: false };
  let territory = null;
  let ecology = null;
  const offscreen = document.createElement("canvas");
  const offctx = offscreen.getContext("2d");
  // Scratch layer for territory: crisp clan blocks are drawn here, then blitted
  // back blurred+additive (the glowing "captured zone" aura) and crisp on top.
  const terrLayer = document.createElement("canvas");
  const terrCtx = terrLayer.getContext("2d");
  let territoryDirty = false;

  // ---- clan-cohesion glow ----
  // Same-clan creatures that cluster together "create light": each clan member
  // stamps a soft radial sprite tinted with its clan color using additive
  // ('lighter') compositing, so a lone creature is barely visible while a tight
  // group sums up into a bright halo. Sprites are cached per clan (a handful)
  // and blitted, so this stays O(N) with no per-frame gradient builds.
  let glowEnabled = true;
  const glowSprites = new Map();             // clanId -> { key, canvas }
  const GLOW_SPRITE_PX = 48;
  const GLOW_MAX_CREATURES = 9000;           // perf guard: skip glow above this

  // ---- transient event signals (war / new clan / new species / alliance) ----
  let signals = [];
  const SIGNAL_TTL = 1500;                   // ticks; matches config.SIGNAL_TTL_TICKS
  const SIGN_STYLES = {
    war_declared:    { sym: "⚔", color: "255,72,60",  ring: true },   // ⚔
    war_ended:       { sym: "☮", color: "120,200,255", ring: false },  // ☮
    alliance_formed: { sym: "☭", color: "120,230,140", ring: true },   // ☭-ish union
    clan_created:    { sym: "✦", color: "245,205,90",  ring: true },   // ✦
    species_emerged: { sym: "✻", color: "130,222,222", ring: true },   // ❋
  };

  // ---- camera ----
  let dpr = 1;
  let baseScale = 1, baseOffX = 0, baseOffY = 0;  // fit-to-window
  let zoom = 1, zoomTarget = 1;                    // eased zoom
  let camX = 0, camY = 0;                          // screen px of world (0,0)
  let camInit = false;
  // Zoom anchor (kept fixed under cursor while zoom eases).
  let azWX = 0, azWY = 0, azSX = 0, azSY = 0;
  const MIN_ZOOM = 0.6, MAX_ZOOM = 24;

  // ---- pan drag ----
  let dragging = false, dragMoved = false;
  let dragSX = 0, dragSY = 0, dragCamX = 0, dragCamY = 0;

  let selectedId = null;
  let hoveredId = null;
  let onSelect = () => {};
  let onHover = () => {};

  let frameCount = 0, lastFpsT = performance.now(), lastFps = 0;

  const effScale = () => baseScale * zoom;

  function cssSize() {
    const r = cv.getBoundingClientRect();
    return { w: r.width, h: r.height, rect: r };
  }

  function resize() {
    dpr = window.devicePixelRatio || 1;
    const { w, h } = cssSize();
    // Preserve the world point currently at screen center across the resize.
    let centerWX = null, centerWY = null;
    if (camInit) {
      centerWX = (w / 2 - camX) / effScale();
      centerWY = (h / 2 - camY) / effScale();
    }
    cv.width = Math.max(1, Math.floor(w * dpr));
    cv.height = Math.max(1, Math.floor(h * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    recomputeBase();
    if (centerWX !== null) {
      camX = w / 2 - centerWX * effScale();
      camY = h / 2 - centerWY * effScale();
      clampCam();
    }
    territoryDirty = true;
  }

  function recomputeBase() {
    if (!curSnap) return;
    const { w, h } = cssSize();
    const ww = curSnap.world.width;
    const wh = curSnap.world.height;
    baseScale = Math.max(1, Math.floor(Math.min(w / ww, h / wh)));
    baseOffX = Math.floor((w - ww * baseScale) / 2);
    baseOffY = Math.floor((h - wh * baseScale) / 2);
    if (!camInit) {
      camX = baseOffX; camY = baseOffY; camInit = true;
    } else {
      clampCam();   // keep a restored camera inside bounds for this viewport
    }
  }

  function clampCam() {
    if (!curSnap) return;
    const { w, h } = cssSize();
    const wpx = curSnap.world.width * effScale();
    const hpx = curSnap.world.height * effScale();
    // If the world is smaller than the viewport, center it; else keep it
    // covering the viewport (can't pan past the edges).
    camX = wpx <= w ? (w - wpx) / 2 : Math.min(0, Math.max(w - wpx, camX));
    camY = hpx <= h ? (h - hpx) / 2 : Math.min(0, Math.max(h - hpx, camY));
  }

  // ---- zoom controls ----
  function zoomAt(sx, sy, factor) {
    const wx = (sx - camX) / effScale();
    const wy = (sy - camY) / effScale();
    zoomTarget = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoomTarget * factor));
    azWX = wx; azWY = wy; azSX = sx; azSY = sy;
  }

  function zoomBy(factor) {
    const { w, h } = cssSize();
    zoomAt(w / 2, h / 2, factor);
    persistView();
  }

  function resetView() {
    zoomTarget = 1; zoom = 1;
    camInit = false;
    recomputeBase();
    clampCam();
    territoryDirty = true;
    persistView();
  }

  function setColorMode(m) { colorMode = m; persistView(); }
  function setOverlay(name, on) {
    if (name === "glow") { glowEnabled = !!on; persistView(); return; }   // dynamic, not offscreen
    if (name in overlays) { overlays[name] = !!on; territoryDirty = true; persistView(); }
  }
  function isGlowOn() { return glowEnabled; }
  function getColorMode() { return colorMode; }
  function getOverlay(name) { return name === "glow" ? glowEnabled : !!overlays[name]; }

  // ---- persistent view state ----
  // Filters + camera survive the full page reload that happens when the user
  // navigates Map <-> Analytics (separate pages). This is the "functional
  // luxury" of not losing your context every time you check the charts.
  const VIEW_KEY = "lambdalife.view.v1";
  function persistView() {
    try {
      localStorage.setItem(VIEW_KEY, JSON.stringify({
        colorMode, overlays, glow: glowEnabled,
        zoom: zoomTarget, camX, camY,
      }));
    } catch (e) { /* storage disabled — feature simply off */ }
  }
  function restoreView() {
    let v;
    try { v = JSON.parse(localStorage.getItem(VIEW_KEY) || "null"); }
    catch (e) { return; }
    if (!v) return;
    if (typeof v.colorMode === "string") colorMode = v.colorMode;
    if (v.overlays) for (const k of Object.keys(overlays)) overlays[k] = !!v.overlays[k];
    if (typeof v.glow === "boolean") glowEnabled = v.glow;
    if (Number.isFinite(v.zoom) && Number.isFinite(v.camX) && Number.isFinite(v.camY)) {
      zoom = zoomTarget = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.zoom));
      camX = v.camX; camY = v.camY; camInit = true;
    }
    territoryDirty = true;
  }
  function anyOverlay() { return overlays.territory || overlays.borders || overlays.ecology; }
  function setTerritory(data) { territory = data; territoryDirty = true; }
  function setEcology(data) { ecology = data; territoryDirty = true; }

  function renderTerritory() {
    territoryDirty = false;
    offscreen.width = cv.width;
    offscreen.height = cv.height;
    offctx.setTransform(1, 0, 0, 1, 0, 0);
    offctx.clearRect(0, 0, offscreen.width, offscreen.height);
    if (!curSnap || !anyOverlay()) return;

    const es = effScale() * dpr;
    const ox = camX * dpr;
    const oy = camY * dpr;

    // Resource-ecology heatmap (drawn under territory): green = available food
    // biomass, red tint = over-grazing depletion.
    if (overlays.ecology && ecology) {
      const e = ecology;
      const zpx = e.zone * es;
      for (let ix = 0; ix < e.cols; ix++) {
        for (let iy = 0; iy < e.rows; iy++) {
          const idx = ix * e.rows + iy;
          const cur = e.current_ratio[idx];
          const dep = e.depletion[idx];
          const g = Math.round(40 + 180 * cur);
          const r = Math.round(40 + 160 * dep);
          offctx.fillStyle = `rgba(${r},${g},60,${0.10 + 0.35 * Math.max(cur, dep)})`;
          offctx.fillRect(ox + ix * zpx, oy + iy * zpx, zpx + 1, zpx + 1);
        }
      }
    }

    if (!territory) return;
    const t = territory;
    const bpx = t.block * es;
    const { cols, rows, owner, strength, assimilation, conflict, clans } = t;
    const colOf = (o) => clans[o] || [150, 150, 150];

    if (overlays.territory) {
      // 1) Paint crisp, saturated clan blocks onto the scratch layer.
      terrLayer.width = offscreen.width;
      terrLayer.height = offscreen.height;
      terrCtx.setTransform(1, 0, 0, 1, 0, 0);
      terrCtx.clearRect(0, 0, terrLayer.width, terrLayer.height);
      for (let ix = 0; ix < cols; ix++) {
        for (let iy = 0; iy < rows; iy++) {
          const o = owner[ix * rows + iy];
          if (o < 0) continue;
          const c = colOf(o);
          const s = strength ? strength[ix * rows + iy] : 1;
          terrCtx.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${0.45 + 0.45 * s})`;
          terrCtx.fillRect(ox + ix * bpx, oy + iy * bpx, bpx + 1.2, bpx + 1.2);
        }
      }
      // 2) Blurred, additive underlay — soft merged zones that glow where a clan
      //    holds dense, contiguous ground (the "shader" look, GPU-blurred once).
      offctx.save();
      offctx.globalCompositeOperation = "lighter";
      offctx.globalAlpha = 0.6;
      offctx.filter = `blur(${Math.max(4, bpx * 1.1)}px)`;
      offctx.drawImage(terrLayer, 0, 0);
      offctx.filter = "none";
      offctx.restore();
      // 3) Crisp tint on top so the body of the territory stays readable.
      offctx.save();
      offctx.globalAlpha = 0.38;
      offctx.drawImage(terrLayer, 0, 0);
      offctx.restore();
    }

    if (overlays.borders) {
      for (let ix = 0; ix < cols; ix++) {
        for (let iy = 0; iy < rows; iy++) {
          const idx = ix * rows + iy;
          const o = owner[idx];
          if (o < 0) continue;
          const x0 = ox + ix * bpx;
          const y0 = oy + iy * bpx;
          const assim = assimilation ? assimilation[idx] : 1;
          const conf = conflict ? conflict[idx] : 0;
          drawEdge(o, owner[(ix + 1) * rows + iy] ?? -1, x0 + bpx, y0, x0 + bpx, y0 + bpx, colOf, assim, conf);
          drawEdge(o, (iy + 1 < rows) ? owner[ix * rows + (iy + 1)] : -1, x0, y0 + bpx, x0 + bpx, y0 + bpx, colOf, assim, conf);
        }
      }
      offctx.setLineDash([]);
    }
  }

  // Border style encodes maturation: contested (dashed amber), stable (solid
  // bold clan colour), assimilating (faint solid), occupied (short-dashed).
  function drawEdge(o, nb, ax, ay, bx, by, colOf, assim, conf) {
    if (nb === o) return;
    const c = colOf(o);
    let dash, style, width;
    if (nb >= 0) {
      dash = [5, 4]; style = "rgba(255,205,90,0.95)"; width = Math.max(1, dpr);
    } else if (conf > 0.4) {
      dash = [5, 4]; style = "rgba(255,140,90,0.95)"; width = Math.max(1, dpr);
    } else if (assim >= 0.75) {
      dash = []; style = `rgba(${c[0]},${c[1]},${c[2]},0.95)`; width = Math.max(1.5, dpr * 1.5);
    } else if (assim >= 0.33) {
      dash = []; style = `rgba(${c[0]},${c[1]},${c[2]},0.55)`; width = Math.max(1, dpr);
    } else {
      dash = [3, 3]; style = `rgba(${c[0]},${c[1]},${c[2]},0.85)`; width = Math.max(1, dpr);
    }
    offctx.setLineDash(dash);
    offctx.strokeStyle = style;
    offctx.lineWidth = width;
    offctx.beginPath();
    offctx.moveTo(ax, ay);
    offctx.lineTo(bx, by);
    offctx.stroke();
  }

  function creatureFill(cr, i) {
    if (colorMode === "clan") {
      const cid = cr.clan[i];
      if (cid >= 0 && clanColorById.has(cid)) {
        const c = clanColorById.get(cid);
        return `rgb(${c[0]},${c[1]},${c[2]})`;
      }
      return "#4a5161";
    }
    if (colorMode === "species") {
      return `hsl(${(cr.species[i] * 47) % 360},58%,58%)`;
    }
    if (colorMode === "hunger") {
      const ef = (cr.ef && cr.ef[i] != null) ? cr.ef[i] : 1;
      return `hsl(${Math.round(ef * 120)},72%,50%)`;  // red=starving -> green=full
    }
    return `rgb(${cr.r[i]},${cr.g[i]},${cr.b[i]})`;
  }

  function update(snapshot) {
    const firstSnap = curSnap === null;
    prevSnap = curSnap;
    prevT = curT;
    curSnap = snapshot;
    curT = performance.now();

    if (prevSnap) {
      const dt = curT - prevT;
      if (dt > 5 && dt < 1000) interval = interval * 0.7 + dt * 0.3;
      prevPosById = new Map();
      const p = prevSnap.creatures;
      for (let i = 0; i < p.ids.length; i++) {
        prevPosById.set(p.ids[i], { x: p.x[i], y: p.y[i] });
      }
    }

    clanColorById = new Map();
    for (const cl of snapshot.clans) clanColorById.set(cl.id, cl.color);

    signals = snapshot.signals || [];

    if (firstSnap) recomputeBase();
  }

  // Soft radial sprite tinted by the clan color, cached + rebuilt only if the
  // clan's color changes. Additive blitting of this is what makes clusters glow.
  function glowSpriteFor(clanId) {
    const c = clanColorById.get(clanId) || [150, 150, 170];
    const key = c[0] + "," + c[1] + "," + c[2];
    const cached = glowSprites.get(clanId);
    if (cached && cached.key === key) return cached.canvas;
    const s = GLOW_SPRITE_PX;
    const cvs = document.createElement("canvas");
    cvs.width = s; cvs.height = s;
    const g = cvs.getContext("2d");
    const grad = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
    grad.addColorStop(0.0, `rgba(${c[0]},${c[1]},${c[2]},0.42)`);
    grad.addColorStop(0.45, `rgba(${c[0]},${c[1]},${c[2]},0.12)`);
    grad.addColorStop(1.0, `rgba(${c[0]},${c[1]},${c[2]},0)`);
    g.fillStyle = grad;
    g.fillRect(0, 0, s, s);
    // Bound the cache so a long run with lots of clan churn can't leak.
    if (glowSprites.size > 256) glowSprites.clear();
    glowSprites.set(clanId, { key, canvas: cvs });
    return cvs;
  }

  // Cheap "shader" primitives: pre-rendered radial sprites blitted additively,
  // and a cached vignette. No per-frame gradient builds, no shadowBlur.
  let _whiteGlow = null, _foodGlow = null, _vig = null, _vigW = 0, _vigH = 0;
  function radialSprite(size, r, g, b, peak) {
    const cvs = document.createElement("canvas");
    cvs.width = size; cvs.height = size;
    const c = cvs.getContext("2d");
    const grad = c.createRadialGradient(size/2, size/2, 0, size/2, size/2, size/2);
    grad.addColorStop(0.0, `rgba(${r},${g},${b},${peak})`);
    grad.addColorStop(0.5, `rgba(${r},${g},${b},${peak * 0.25})`);
    grad.addColorStop(1.0, `rgba(${r},${g},${b},0)`);
    c.fillStyle = grad; c.fillRect(0, 0, size, size);
    return cvs;
  }
  function whiteGlow() { return _whiteGlow || (_whiteGlow = radialSprite(40, 255, 238, 214, 0.34)); }
  function foodGlow()  { return _foodGlow  || (_foodGlow  = radialSprite(28, 130, 205, 110, 0.5)); }
  function vignette(w, h) {
    if (_vig && _vigW === w && _vigH === h) return _vig;
    const cvs = document.createElement("canvas");
    cvs.width = Math.max(1, w); cvs.height = Math.max(1, h);
    const c = cvs.getContext("2d");
    const grad = c.createRadialGradient(w/2, h*0.46, Math.min(w,h)*0.22, w/2, h*0.5, Math.max(w,h)*0.72);
    grad.addColorStop(0.0, "rgba(0,0,0,0)");
    grad.addColorStop(0.7, "rgba(0,0,0,0.18)");
    grad.addColorStop(1.0, "rgba(6,6,9,0.62)");
    c.fillStyle = grad; c.fillRect(0, 0, w, h);
    _vig = cvs; _vigW = w; _vigH = h;
    return cvs;
  }

  function setOnSelect(cb) { onSelect = cb; }
  function setOnHover(cb) { onHover = cb; }
  function getFps() { return lastFps; }
  function getZoom() { return zoom; }

  function tickFps(now) {
    frameCount++;
    if (now - lastFpsT >= 1000) {
      lastFps = Math.round((frameCount * 1000) / (now - lastFpsT));
      frameCount = 0;
      lastFpsT = now;
    }
  }

  function easeZoom() {
    if (Math.abs(zoom - zoomTarget) < 1e-3) {
      if (zoom !== zoomTarget) zoom = zoomTarget; else return;
    } else {
      zoom += (zoomTarget - zoom) * 0.22;
    }
    // Keep the anchor point fixed under the cursor as zoom changes.
    camX = azSX - azWX * effScale();
    camY = azSY - azWY * effScale();
    clampCam();
    territoryDirty = true;
  }

  function loop() {
    const now = performance.now();
    tickFps(now);
    easeZoom();
    draw(now);
    requestAnimationFrame(loop);
  }

  function draw(now) {
    const { w, h } = cssSize();
    ctx.fillStyle = "#0a0b0e";
    ctx.fillRect(0, 0, w, h);
    if (!curSnap) return;

    const es = effScale();
    ctx.strokeStyle = "rgba(255,170,110,0.07)";
    ctx.lineWidth = 1;
    ctx.strokeRect(camX + 0.5, camY + 0.5, curSnap.world.width * es, curSnap.world.height * es);

    if (anyOverlay()) {
      if (territoryDirty) renderTerritory();
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      // Breathing glow: the baked territory layer gently pulses so captured
      // ground feels alive (no per-frame rebuild — just the blit alpha).
      if (overlays.territory) ctx.globalAlpha = 0.9 + 0.1 * Math.sin(now / 900);
      ctx.drawImage(offscreen, 0, 0);
      ctx.restore();
    }

    let alpha = 1;
    if (prevSnap) {
      alpha = (now - curT) / Math.max(1, interval);
      if (alpha < 0) alpha = 0;
      if (alpha > 1) alpha = 1;
    }

    const food = curSnap.food;
    if (food.x.length <= 4000) {
      const fg = es * 2.0;
      const sp = foodGlow();
      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      for (let i = 0; i < food.x.length; i++) {
        ctx.drawImage(sp, camX + food.x[i] * es + es / 2 - fg,
                          camY + food.y[i] * es + es / 2 - fg, fg * 2, fg * 2);
      }
      ctx.restore();
    }
    ctx.fillStyle = "#8fd06a";
    const fs = Math.max(2, es - 1);
    for (let i = 0; i < food.x.length; i++) {
      ctx.fillRect(camX + food.x[i] * es, camY + food.y[i] * es, fs, fs);
    }

    const cr = curSnap.creatures;
    const radius = Math.max(2, Math.floor(es * 0.8));

    // Glow pass under the dots: a warm "life-light" for every creature (the
    // per-object shader), plus the clan-cohesion color glow (toggle) that sums
    // up in clusters. All additive blits of cached sprites — O(N), no blur.
    if (cr.ids.length <= GLOW_MAX_CREATURES) {
      const wgr = Math.max(4, es * 2.1);
      const gr = Math.max(5, es * 3.5);
      const wsp = whiteGlow();
      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      for (let i = 0; i < cr.ids.length; i++) {
        let wx = cr.x[i], wy = cr.y[i];
        if (prevSnap) {
          const prev = prevPosById.get(cr.ids[i]);
          if (prev !== undefined) {
            wx = prev.x + (wx - prev.x) * alpha;
            wy = prev.y + (wy - prev.y) * alpha;
          }
        }
        const gx = camX + wx * es + es / 2;
        const gy = camY + wy * es + es / 2;
        ctx.drawImage(wsp, gx - wgr, gy - wgr, wgr * 2, wgr * 2);
        if (glowEnabled) {
          const cid = cr.clan[i];
          if (cid >= 0 && clanColorById.has(cid)) {
            ctx.drawImage(glowSpriteFor(cid), gx - gr, gy - gr, gr * 2, gr * 2);
          }
        }
      }
      ctx.restore();
    }

    for (let i = 0; i < cr.ids.length; i++) {
      let wx = cr.x[i];
      let wy = cr.y[i];
      if (prevSnap) {
        const prev = prevPosById.get(cr.ids[i]);
        if (prev !== undefined) {
          wx = prev.x + (wx - prev.x) * alpha;
          wy = prev.y + (wy - prev.y) * alpha;
        }
      }
      const cx = camX + wx * es + es / 2;
      const cy = camY + wy * es + es / 2;
      ctx.fillStyle = creatureFill(cr, i);
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
        ctx.strokeStyle = "#ff8a34";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(cx, cy, radius + 4, 0, Math.PI * 2);
        ctx.stroke();
      } else if (cr.ids[i] === hoveredId) {
        ctx.strokeStyle = "rgba(255,138,52,0.6)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(cx, cy, radius + 3, 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    ctx.drawImage(vignette(w, h), 0, 0, w, h);
    drawSignals(now);
  }

  // Transient positioned markers for world "emotions": ⚔ where a war is
  // declared, ✦ where a clan is born, etc. Each fades out over its TTL and the
  // ringed ones pulse to draw the eye to the spot where it happened.
  function drawSignals(now) {
    if (!signals.length) return;
    const es = effScale();
    const tickNow = curSnap.tick;
    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const sg of signals) {
      const style = SIGN_STYLES[sg.kind];
      if (!style) continue;
      const age = tickNow - sg.tick;
      if (age < 0 || age > SIGNAL_TTL) continue;
      const life = 1 - age / SIGNAL_TTL;            // 1 fresh -> 0 expired
      const cx = camX + sg.x * es;
      const cy = camY + sg.y * es;
      const r = Math.max(11, es * 3.0);

      if (style.ring) {
        const pulse = r + 5 * (1 + Math.sin(now / 220 + sg.x * 0.7));
        ctx.lineWidth = 2;
        ctx.strokeStyle = `rgba(${style.color},${0.45 * life})`;
        ctx.beginPath();
        ctx.arc(cx, cy, pulse, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.fillStyle = `rgba(${style.color},${0.16 * life})`;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();

      ctx.font = `${Math.max(14, Math.round(r * 1.25))}px serif`;
      ctx.fillStyle = `rgba(${style.color},${0.35 + 0.6 * life})`;
      ctx.fillText(style.sym, cx, cy);
    }
    ctx.restore();
  }

  function pickAt(px, py) {
    if (!curSnap) return -1;
    const es = effScale();
    const wx = (px - camX) / es;
    const wy = (py - camY) / es;
    if (wx < 0 || wy < 0 || wx > curSnap.world.width || wy > curSnap.world.height) {
      return -1;
    }
    // Selection radius in world tiles scales inversely with zoom so it stays
    // an easy ~a-few-px target on screen.
    const tol = Math.max(0.8, 6 / es);
    let best = -1;
    let bestD2 = tol * tol;
    const cr = curSnap.creatures;
    for (let i = 0; i < cr.ids.length; i++) {
      const dx = cr.x[i] + 0.5 - wx;
      const dy = cr.y[i] + 0.5 - wy;
      const d2 = dx * dx + dy * dy;
      if (d2 < bestD2) { bestD2 = d2; best = i; }
    }
    return best;
  }

  // ---- input ----
  function onWheel(ev) {
    ev.preventDefault();
    const { rect } = cssSize();
    const sx = ev.clientX - rect.left;
    const sy = ev.clientY - rect.top;
    const factor = ev.deltaY < 0 ? 1.18 : 1 / 1.18;
    zoomAt(sx, sy, factor);
    persistView();
  }

  function onDown(ev) {
    const { rect } = cssSize();
    dragging = true;
    dragMoved = false;
    dragSX = ev.clientX - rect.left;
    dragSY = ev.clientY - rect.top;
    dragCamX = camX;
    dragCamY = camY;
    cv.style.cursor = "grabbing";
  }

  function onMove(ev) {
    const { rect } = cssSize();
    const sx = ev.clientX - rect.left;
    const sy = ev.clientY - rect.top;
    if (dragging) {
      const ddx = sx - dragSX;
      const ddy = sy - dragSY;
      if (Math.abs(ddx) + Math.abs(ddy) > 3) dragMoved = true;
      camX = dragCamX + ddx;
      camY = dragCamY + ddy;
      clampCam();
      territoryDirty = true;
      return;
    }
    const i = pickAt(sx, sy);
    const newId = i >= 0 ? curSnap.creatures.ids[i] : null;
    if (newId !== hoveredId) {
      hoveredId = newId;
      onHover(newId);
    }
  }

  function onUp(ev) {
    if (!dragging) return;
    dragging = false;
    cv.style.cursor = "grab";
    persistView();
    if (dragMoved || !curSnap) return;        // a drag, not a click
    const { rect } = cssSize();
    const i = pickAt(ev.clientX - rect.left, ev.clientY - rect.top);
    if (i >= 0) {
      selectedId = curSnap.creatures.ids[i];
      onSelect(selectedId);
    }
  }

  function clearSelection() { selectedId = null; }

  function init() {
    restoreView();
    window.addEventListener("resize", resize);
    cv.addEventListener("wheel", onWheel, { passive: false });
    cv.addEventListener("mousedown", onDown);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    cv.addEventListener("mouseleave", () => { hoveredId = null; onHover(null); });
    cv.style.cursor = "grab";
    resize();
    requestAnimationFrame(loop);
  }

  return {
    init, update, setOnSelect, setOnHover, clearSelection, getFps, getZoom,
    setColorMode, setOverlay, anyOverlay, setTerritory, setEcology,
    zoomBy, resetView, isGlowOn, getColorMode, getOverlay,
  };
})();
