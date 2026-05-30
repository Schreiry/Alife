// Top-level controller. Owns the WebSocket, dispatches snapshots into
// the renderer / charts / topbar, fetches history + events at lower
// frequencies, handles the inspector panel and tab switching.

(async () => {
  let catalogByCategory = null;
  let lastSelected = null;
  const tweens = new Map();          // id -> eased numeric display state
  const pulse = { rate: 60, color: [108, 168, 255], state: "calm", raf: 0 };
  let wsMsgCount = 0;
  let wsHzLastT = performance.now();
  let wsHz = 0;

  Charts.init();
  Renderer.init();
  Controls.init();
  Panels.init();
  initTabs();
  initLayers();

  Renderer.setOnSelect((cid) => {
    lastSelected = cid;
    openPanel("creature");
    refreshInspector();
  });
  Renderer.setOnHover((cid) => {
    const el = document.getElementById("hover-info");
    el.textContent = cid ? `· hover #${cid}` : "";
  });

  try {
    catalogByCategory = await groupCatalog();
  } catch (e) {
    console.warn("catalog fetch failed", e);
  }

  setInterval(refreshHistory, 1500);
  setInterval(() => {
    if (lastSelected) refreshInspector();
  }, 800);
  setInterval(updatePerfCounters, 1000);
  refreshHistory();

  API.liveSocket(onSnapshot, () => {
    document.getElementById("m-status").textContent = "disconnected";
  });

  function onSnapshot(snap) {
    wsMsgCount++;
    Renderer.update(snap);
    Controls.reflectState(snap);
    updateTopbar(snap);
    updateProfilerTable(snap.profiler);
  }

  function updatePerfCounters() {
    const now = performance.now();
    const dt = now - wsHzLastT;
    if (dt > 0) {
      wsHz = Math.round((wsMsgCount * 1000) / dt);
      wsMsgCount = 0;
      wsHzLastT = now;
    }
    document.getElementById("m-wsfps").textContent = wsHz;
    document.getElementById("m-clientfps").textContent = Renderer.getFps();
  }

  // Ease a numeric metric toward its target so values glide instead of jumping.
  function tweenNum(id, target, fmt) {
    const el = document.getElementById(id);
    if (!el) return;
    let st = tweens.get(id);
    if (!st) { st = { val: 0, target, raf: 0 }; tweens.set(id, st); }
    st.target = target;
    if (st.raf) return;
    const start = st.val, t0 = performance.now(), dur = 380;
    const step = (now) => {
      const k = Math.min(1, (now - t0) / dur);
      const e = 1 - Math.pow(1 - k, 3);
      st.val = start + (st.target - start) * e;
      el.textContent = fmt(Math.round(st.val));
      if (k < 1) { st.raf = requestAnimationFrame(step); }
      else { st.val = st.target; el.textContent = fmt(st.target); st.raf = 0; }
    };
    st.raf = requestAnimationFrame(step);
  }

  function updateTopbar(s) {
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set("m-tick", s.tick.toLocaleString());
    tweenNum("m-pop", s.population, (v) => `${v}/${s.max_population}`);
    tweenNum("m-food", s.food_count, String);
    tweenNum("m-species", s.species_count, String);
    tweenNum("m-clans", s.clan_count, String);
    tweenNum("m-hybrids", s.hybrids, String);
    tweenNum("m-gen", s.generation_max, String);
    tweenNum("m-births", s.births, (v) => v.toLocaleString());
    tweenNum("m-deaths", s.deaths, (v) => v.toLocaleString());
    set("m-tickms", s.profiler.tick_ms.toFixed(1));
    const hot = topSection(s.profiler.sections);
    set("m-hot", hot ? `${hot.name}:${hot.ms.toFixed(1)}` : "-");
    set("m-status", s.paused ? "paused" : "running");
  }

  function topSection(sections) {
    let best = null;
    for (const [name, ms] of Object.entries(sections || {})) {
      if (name === "tick" || name === "render") continue;
      if (!best || ms > best.ms) best = { name, ms };
    }
    return best;
  }

  function updateProfilerTable(p) {
    const tbl = document.getElementById("prof-table");
    const rows = Object.entries(p.sections || {})
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);
    tbl.innerHTML = rows
      .map(([k, v]) => `<tr><td>${k}</td><td>${v.toFixed(2)}</td></tr>`)
      .join("");
  }

  async function refreshHistory() {
    try {
      const h = await API.history("population,food,births_delta,deaths_delta,species,clans,avg_aggression,avg_intelligence", 300);
      Charts.setHistory(h);
    } catch (e) { /* server bouncing */ }
  }

  async function refreshInspector() {
    if (!lastSelected) return;
    try {
      const c = await API.creature(lastSelected);
      renderInspector(c);
    } catch (e) {
      lastSelected = null;
      Renderer.clearSelection();
      document.getElementById("inspector-content").hidden = true;
      document.getElementById("inspector-empty").hidden = false;
      document.getElementById("inspector-empty").textContent =
        "(creature is no longer alive)";
    }
  }

  const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

  function renderInspector(c) {
    document.getElementById("inspector-empty").hidden = true;
    document.getElementById("inspector-content").hidden = false;

    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set("ic-id", c.id);
    const arch = document.getElementById("ic-archetype");
    if (arch) { arch.textContent = c.archetype ?? "—"; arch.dataset.arch = (c.archetype || "").toLowerCase(); }
    set("ic-age", `${c.age} / ${c.lifespan}`);
    set("ic-gen", c.generation);
    set("ic-species", c.species_id);
    set("ic-clan", c.clan_id ?? "—");
    set("ic-sex", c.sex === 0 ? "♀ female" : "♂ male");
    set("ic-hybrid", c.is_hybrid ? "yes" : "no");
    set("ic-energy", `${c.energy.toFixed(0)} / ${c.max_energy.toFixed(0)}`);
    set("ic-health", `${c.health.toFixed(0)} / ${c.max_health.toFixed(0)}`);
    const eb = document.getElementById("ic-energy-bar");
    if (eb) eb.style.width = `${clamp01(c.energy / c.max_energy) * 100}%`;
    const hb = document.getElementById("ic-health-bar");
    if (hb) hb.style.width = `${clamp01(c.health / c.max_health) * 100}%`;
    set("ic-action", c.last_action);
    set("ic-parents", `${c.parent_a ?? "—"} × ${c.parent_b ?? "—"}`);
    if (c.pulse) setPulse(c.pulse);

    const root = document.getElementById("ic-genome");
    set("ic-gene-count", `(${Object.keys(c.genome).length})`);
    if (!catalogByCategory) { root.textContent = "(catalog loading…)"; return; }
    let html = "";
    for (const [cat, genes] of catalogByCategory) {
      html += `<div class="cat-header">${cat}</div>`;
      for (const g of genes) {
        const v = c.genome[g.name];
        if (v === undefined) continue;
        const cls = g.active ? "g" : "g dormant";
        html += `<div class="${cls}"><span class="nm">${g.name}</span><span class="v">${v.toFixed(3)}</span></div>`;
      }
    }
    root.innerHTML = html;
  }

  // ---- pulse (ECG-style vital signal) ----
  function setPulse(p) {
    pulse.rate = p.rate; pulse.color = p.color; pulse.state = p.state;
    const rate = document.getElementById("ic-pulse-rate");
    if (rate) rate.textContent = p.rate;
    const st = document.getElementById("ic-pulse-state");
    if (st) {
      st.textContent = p.state;
      st.style.color = `rgb(${p.color[0]},${p.color[1]},${p.color[2]})`;
    }
    if (!pulse.raf) pulse.raf = requestAnimationFrame(drawPulse);
  }

  // One heartbeat waveform over phase p∈[0,1): P-wave, QRS spike, T-wave.
  function beat(p) {
    const g = (c, w, a) => Math.exp(-(((p - c) / w) ** 2)) * a;
    return g(0.07, 0.022, 0.13) + g(0.165, 0.013, 1.0) - g(0.13, 0.013, 0.28)
         - g(0.205, 0.016, 0.4) + g(0.42, 0.05, 0.24);
  }

  function drawPulse(now) {
    const cv = document.getElementById("pulse-canvas");
    if (!cv || cv.offsetParent === null) { pulse.raf = 0; return; }   // panel hidden
    const dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth || 240, h = cv.clientHeight || 56;
    if (cv.width !== Math.floor(w * dpr)) { cv.width = Math.floor(w * dpr); cv.height = Math.floor(h * dpr); }
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const [r, g, b] = pulse.color;
    const mid = h * 0.6, amp = h * 0.46;
    const beatsVisible = Math.max(2.2, Math.min(9, pulse.rate / 20));
    const pxPerBeat = w / beatsVisible;
    const rightPhase = (now / 1000) * (pulse.rate / 60);
    ctx.strokeStyle = `rgb(${r},${g},${b})`;
    ctx.shadowColor = `rgba(${r},${g},${b},0.9)`;
    ctx.shadowBlur = 11;
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let x = 0; x <= w; x++) {
      const phase = rightPhase - (w - x) / pxPerBeat;
      const y = mid - beat(phase - Math.floor(phase)) * amp;
      if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
    pulse.raf = requestAnimationFrame(drawPulse);
  }

  async function groupCatalog() {
    const cat = await API.catalog();
    const groups = new Map();
    for (const g of cat.genes) {
      if (!groups.has(g.category)) groups.set(g.category, []);
      groups.get(g.category).push(g);
    }
    return groups;
  }

  // ---- sliding inspector panel ----
  // The panel is hidden until summoned. The three launcher buttons on the map
  // (and the in-panel tabs) open it to a given tab. Opening "creature" with no
  // selection just shows the centered map hint instead of an empty panel.
  let panelOpen = false;
  const PANEL_TITLES = { creature: "Creature", clans: "Clans", species: "Species" };

  function updateHint() {
    const hint = document.getElementById("map-hint");
    if (hint) hint.hidden = panelOpen || !!lastSelected;
  }
  function setLauncherActive(name) {
    document.querySelectorAll("#panel-launcher .pl-btn").forEach((b) =>
      b.classList.toggle("active", panelOpen && b.dataset.tab === name));
  }
  function openPanel(name) {
    if (name === "creature" && !lastSelected) {
      closePanel();              // nothing to show yet → invite via centered hint
      return;
    }
    panelOpen = true;
    document.getElementById("inspector").classList.add("open");
    const t = document.getElementById("panel-title");
    if (t) t.textContent = PANEL_TITLES[name] || "Inspector";
    setTab(name);
    setLauncherActive(name);
    updateHint();
  }
  function closePanel() {
    panelOpen = false;
    document.getElementById("inspector").classList.remove("open");
    setLauncherActive(null);
    updateHint();
  }

  function initTabs() {
    document.querySelectorAll(".tabs .tab").forEach((btn) => {
      btn.addEventListener("click", () => openPanel(btn.dataset.tab));
    });
    document.querySelectorAll("#panel-launcher .pl-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        // Clicking the already-open tab closes the panel (toggle).
        if (panelOpen && btn.classList.contains("active")) closePanel();
        else openPanel(btn.dataset.tab);
      });
    });
    const closeBtn = document.getElementById("panel-close");
    if (closeBtn) closeBtn.addEventListener("click", closePanel);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePanel(); });
    updateHint();
  }

  // Map view layers. Pure observation: these only change how the renderer
  // reads the snapshot — they never call into the simulation.
  function initLayers() {
    document.querySelectorAll(".layer-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".layer-btn").forEach((b) =>
          b.classList.toggle("active", b === btn));
        Renderer.setColorMode(btn.dataset.mode);
      });
    });
    document.querySelectorAll(".layer-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        const ov = btn.dataset.overlay;
        const on = !btn.classList.contains("active");
        btn.classList.toggle("active", on);
        Renderer.setOverlay(ov, on);
        // Fetch the field grid immediately so the layer appears now. Glow is
        // computed from the live snapshot, so it needs no fetch.
        if (on && ov === "ecology") refreshEcology();
        else if (on && (ov === "territory" || ov === "borders")) refreshTerritory();
      });
    });
    document.querySelectorAll(".zoom-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const k = btn.dataset.zoom;
        if (k === "in") Renderer.zoomBy(1.3);
        else if (k === "out") Renderer.zoomBy(1 / 1.3);
        else Renderer.resetView();
      });
    });

    // Reflect the view state the renderer restored from localStorage so the
    // filter buttons match what's actually drawn after a Map<->Analytics
    // reload, and fetch the field grids for any restored-on layers.
    const mode = Renderer.getColorMode();
    document.querySelectorAll(".layer-btn").forEach((b) =>
      b.classList.toggle("active", b.dataset.mode === mode));
    document.querySelectorAll(".layer-toggle").forEach((b) =>
      b.classList.toggle("active", Renderer.getOverlay(b.dataset.overlay)));
    if (Renderer.getOverlay("territory") || Renderer.getOverlay("borders")) refreshTerritory();
    if (Renderer.getOverlay("ecology")) refreshEcology();

    // Poll the field grids only while their layer is on.
    const isOn = (ov) =>
      document.querySelector(`.layer-toggle[data-overlay="${ov}"]`).classList.contains("active");
    setInterval(() => {
      if (isOn("territory") || isOn("borders")) refreshTerritory();
      if (isOn("ecology")) refreshEcology();
    }, 1500);
  }

  async function refreshTerritory() {
    try { Renderer.setTerritory(await API.territory(5)); }
    catch (e) { /* server bouncing */ }
  }

  async function refreshEcology() {
    try { Renderer.setEcology(await API.ecology()); }
    catch (e) { /* server bouncing */ }
  }

  function setTab(name) {
    document.querySelectorAll(".tabs .tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === name);
    });
    document.querySelectorAll(".tab-pane").forEach((p) => {
      p.hidden = p.dataset.pane !== name;
    });
  }
})();
