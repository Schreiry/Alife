// cursor.js — custom HUD cursor + glowing trail (shared by Map & Analytics).
// Fusion: Google Books precision dot · macOS eased ring · Half-Life 2 HUD
// corner brackets. Dependency-free, single full-window additive canvas.
(function () {
  // Skip on touch / coarse pointers — a custom cursor there is pointless.
  if (window.matchMedia && window.matchMedia("(pointer: coarse)").matches) return;

  const root = document.documentElement;
  root.classList.add("custom-cursor");

  const cvs = document.createElement("canvas");
  cvs.id = "cursor-fx";
  document.body.appendChild(cvs);
  const ctx = cvs.getContext("2d");
  let dpr = 1, W = 0, H = 0;
  function resize() {
    dpr = Math.max(1, window.devicePixelRatio || 1);
    W = window.innerWidth; H = window.innerHeight;
    cvs.width = W * dpr; cvs.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  window.addEventListener("resize", resize); resize();

  // pointer target (exact) + eased ring position
  let tx = W / 2, ty = H / 2, rx = tx, ry = ty;
  let visible = false, pressed = false, overUI = false, overMap = false;
  let ringR = 15, brk = 0, spin = 0;       // ring radius, bracket spread, slow rotation
  const ACCENT = [255, 138, 52];
  const trail = [];                         // {x,y,t}

  const ACC = (a) => `rgba(${ACCENT[0]},${ACCENT[1]},${ACCENT[2]},${a})`;

  function onMove(e) {
    tx = e.clientX; ty = e.clientY; visible = true;
    const el = e.target;
    overMap = !!(el && el.id === "map");
    overUI = !!(el && el.closest &&
      el.closest("button,a,select,input,label,.tab,.layer-btn,.layer-toggle,.zoom-btn,.info-card,.entity"));
    const last = trail[trail.length - 1];
    if (!last || (tx - last.x) ** 2 + (ty - last.y) ** 2 > 9) {
      trail.push({ x: tx, y: ty, t: performance.now() });
      if (trail.length > 22) trail.shift();
    }
  }
  window.addEventListener("mousemove", onMove, { passive: true });
  window.addEventListener("mousedown", () => (pressed = true));
  window.addEventListener("mouseup", () => (pressed = false));
  document.addEventListener("mouseleave", () => (visible = false));
  window.addEventListener("blur", () => (visible = false));

  function bracket(cx, cy, r, spread, rot, alpha) {
    // four HL2-style corner brackets on the ring's diagonals, rotating by `rot`
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(rot);
    ctx.strokeStyle = ACC(alpha);
    ctx.lineWidth = 1.6;
    ctx.lineCap = "round";
    const d = r + spread;
    const arm = 0.34;                       // angular half-width of each bracket
    for (let k = 0; k < 4; k++) {
      const a = k * Math.PI / 2 + Math.PI / 4;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a - arm) * d, Math.sin(a - arm) * d);
      ctx.lineTo(Math.cos(a) * d, Math.sin(a) * d);
      ctx.lineTo(Math.cos(a + arm) * d, Math.sin(a + arm) * d);
      ctx.stroke();
    }
    ctx.restore();
  }

  function frame() {
    requestAnimationFrame(frame);
    ctx.clearRect(0, 0, W, H);
    if (!visible) return;

    // ease ring toward target (macOS-style smooth lag)
    rx += (tx - rx) * 0.28; ry += (ty - ry) * 0.28;
    const targetR = (overUI ? 24 : 15) - (pressed ? 4 : 0);
    ringR += (targetR - ringR) * 0.2;
    brk += ((overUI ? 7 : 3) - brk) * 0.2;
    spin += overUI ? 0.045 : 0.012;

    const now = performance.now();

    // ---- glowing trail (additive) ----
    ctx.globalCompositeOperation = "lighter";
    const tIntensity = overMap ? 1 : 0.5;
    for (let i = 1; i < trail.length; i++) {
      const p = trail[i], q = trail[i - 1];
      const age = (now - p.t) / 520;
      if (age >= 1) continue;
      const a = (1 - age) * 0.5 * tIntensity * (i / trail.length);
      ctx.strokeStyle = ACC(a);
      ctx.lineWidth = (1 - age) * (overMap ? 5 : 3);
      ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(q.x, q.y); ctx.lineTo(p.x, p.y); ctx.stroke();
    }
    // soft halo at the ring
    const halo = ctx.createRadialGradient(rx, ry, 0, rx, ry, ringR * 2.4);
    halo.addColorStop(0, ACC(overMap ? 0.22 : 0.13));
    halo.addColorStop(1, ACC(0));
    ctx.fillStyle = halo;
    ctx.beginPath(); ctx.arc(rx, ry, ringR * 2.4, 0, 6.283); ctx.fill();

    // ---- ring + HUD brackets ----
    ctx.strokeStyle = ACC(0.85);
    ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.arc(rx, ry, ringR, 0, 6.283); ctx.stroke();
    bracket(rx, ry, ringR, brk, spin, 0.9);

    ctx.globalCompositeOperation = "source-over";
    // ---- precise center dot (exact hotspot, no lag) ----
    ctx.fillStyle = "#fff6ec";
    ctx.beginPath(); ctx.arc(tx, ty, pressed ? 1.6 : 2.4, 0, 6.283); ctx.fill();
    ctx.fillStyle = ACC(0.9);
    ctx.beginPath(); ctx.arc(tx, ty, pressed ? 3.6 : 4.4, 0, 6.283); ctx.fill();
  }
  requestAnimationFrame(frame);
})();
