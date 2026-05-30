// brainviz.js — dependency-free pseudo-3D neural-network renderer.
//
// Renders a brain graph {nodes:[{id,label,layer,group,act}], edges:[{s,t,w}]}
// as a rotating, glowing 3-layer network: sensors (front) -> cognition (middle)
// -> actions (back). Node size grows with activation, edges brighten with
// weight — so a stronger genome literally lights up more connections. Drag to
// rotate, scroll to zoom; auto-rotates when idle. No WebGL, no libraries.
const BrainViz = (() => {
  const GROUP_COLOR = {
    perception: [120, 170, 255],
    intellect:  [255, 150, 60],
    instinct:   [255, 92, 76],
    social:     [120, 210, 130],
    action:     [245, 235, 212],
  };
  const DZ = 220, RING = 200;

  let cv, ctx, dpr = 1, W = 0, H = 0;
  let net = null, layout = [];
  let yaw = 0.6, pitch = -0.35, zoom = 1, autorot = true;
  let dragging = false, lastX = 0, lastY = 0, raf = 0;
  let t0 = performance.now();

  function init(canvas) {
    cv = canvas;
    ctx = cv.getContext("2d");
    resize();
    window.addEventListener("resize", resize);
    cv.addEventListener("mousedown", (e) => {
      dragging = true; autorot = false; lastX = e.clientX; lastY = e.clientY;
    });
    window.addEventListener("mouseup", () => { dragging = false; });
    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      yaw += (e.clientX - lastX) * 0.008;
      pitch += (e.clientY - lastY) * 0.008;
      pitch = Math.max(-1.3, Math.min(1.3, pitch));
      lastX = e.clientX; lastY = e.clientY;
    });
    cv.addEventListener("wheel", (e) => {
      e.preventDefault();
      zoom = Math.max(0.45, Math.min(2.6, zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
    }, { passive: false });
    cv.addEventListener("dblclick", () => { autorot = true; zoom = 1; });
    if (!raf) raf = requestAnimationFrame(loop);
  }

  function resize() {
    if (!cv) return;
    dpr = window.devicePixelRatio || 1;
    const r = cv.getBoundingClientRect();
    W = r.width; H = r.height || 460;
    cv.width = Math.max(1, Math.floor(W * dpr));
    cv.height = Math.max(1, Math.floor(H * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // Stable 3D layout: layers along z, nodes spread on rings within each layer.
  function relayout() {
    layout = [];
    if (!net) return;
    const byLayer = [[], [], []];
    net.nodes.forEach((n, i) => byLayer[n.layer].push(i));
    const place = (ids, z, rad) => {
      const m = ids.length;
      ids.forEach((idx, k) => {
        const a = (k / Math.max(1, m)) * Math.PI * 2;
        // jitter z by node order so the middle layer reads as a cloud, not a disc
        const zz = z + (net.nodes[idx].layer === 1 ? (k % 3 - 1) * 46 : 0);
        layout[idx] = { x: Math.cos(a) * rad, y: Math.sin(a) * rad, z: zz };
      });
    };
    place(byLayer[0], -DZ, RING);
    place(byLayer[1], 0, RING * 0.72);
    place(byLayer[2], DZ, RING);
  }

  function setNet(n) { net = n; relayout(); }

  function project(p, cx, cy, s, cosY, sinY, cosP, sinP) {
    // rotate around Y then X, then perspective project
    let x = p.x * cosY - p.z * sinY;
    let z = p.x * sinY + p.z * cosY;
    let y = p.y * cosP - z * sinP;
    z = p.y * sinP + z * cosP;
    const f = 620;
    const sc = (f / (f + z)) * s;
    return { sx: cx + x * sc, sy: cy + y * sc, depth: z, sc };
  }

  function loop() {
    raf = requestAnimationFrame(loop);
    const now = performance.now();
    ctx.clearRect(0, 0, W, H);
    if (!net || !net.nodes.length) {
      ctx.fillStyle = "rgba(180,180,190,0.4)";
      ctx.font = "13px 'JetBrains Mono', monospace";
      ctx.textAlign = "center";
      ctx.fillText("awaiting minds…", W / 2, H / 2);
      return;
    }
    if (autorot) yaw += 0.0035;

    const cx = W / 2, cy = H / 2;
    const s = Math.min(W, H) / 540 * zoom;
    const cosY = Math.cos(yaw), sinY = Math.sin(yaw);
    const cosP = Math.cos(pitch), sinP = Math.sin(pitch);

    const proj = layout.map((p) => project(p, cx, cy, s, cosY, sinY, cosP, sinP));
    const pulse = 0.5 + 0.5 * Math.sin((now - t0) / 700);

    // edges (additive glow) — sorted back-to-front
    ctx.globalCompositeOperation = "lighter";
    const es = net.edges.slice().sort((a, b) =>
      (proj[a.s].depth + proj[a.t].depth) - (proj[b.s].depth + proj[b.t].depth));
    for (const e of es) {
      const a = proj[e.s], b = proj[e.t];
      const w = Math.min(1, e.w);
      const col = GROUP_COLOR[net.nodes[e.s].group] || [200, 200, 200];
      ctx.strokeStyle = `rgba(${col[0]},${col[1]},${col[2]},${0.07 + 0.45 * w})`;
      ctx.lineWidth = (0.4 + 1.8 * w) * (0.7 + 0.3 * pulse);
      ctx.beginPath(); ctx.moveTo(a.sx, a.sy); ctx.lineTo(b.sx, b.sy); ctx.stroke();
    }

    // nodes — sorted back-to-front, glow + core + label for the strong ones
    const order = net.nodes.map((_, i) => i).sort((i, j) => proj[i].depth - proj[j].depth);
    for (const i of order) {
      const n = net.nodes[i], p = proj[i];
      const col = GROUP_COLOR[n.group] || [200, 200, 200];
      const r = (3 + 9 * n.act) * p.sc * 0.9 + 1.5;
      const halo = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, r * 3.2);
      halo.addColorStop(0, `rgba(${col[0]},${col[1]},${col[2]},${0.28 + 0.4 * n.act})`);
      halo.addColorStop(1, `rgba(${col[0]},${col[1]},${col[2]},0)`);
      ctx.fillStyle = halo;
      ctx.beginPath(); ctx.arc(p.sx, p.sy, r * 3.2, 0, 6.283); ctx.fill();
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = `rgb(${col[0]},${col[1]},${col[2]})`;
      ctx.beginPath(); ctx.arc(p.sx, p.sy, r, 0, 6.283); ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      ctx.beginPath(); ctx.arc(p.sx, p.sy, r * 0.4, 0, 6.283); ctx.fill();
      ctx.globalCompositeOperation = "lighter";
      if (n.act > 0.45 || n.layer !== 1) {
        ctx.globalCompositeOperation = "source-over";
        ctx.fillStyle = `rgba(${col[0]},${col[1]},${col[2]},${0.5 + 0.5 * n.act})`;
        ctx.font = `${Math.max(8, Math.round(9 * p.sc))}px 'JetBrains Mono', monospace`;
        ctx.textAlign = "center";
        ctx.fillText(n.label, p.sx, p.sy - r - 3);
        ctx.globalCompositeOperation = "lighter";
      }
    }
    ctx.globalCompositeOperation = "source-over";
  }

  return { init, setNet, resize };
})();
