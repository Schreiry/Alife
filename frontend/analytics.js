// Controller for the /analytics research page. Polls the analytics +
// history + events endpoints and draws histograms / bars on Canvas2D.
// Time-series charts reuse the shared Charts module (canvas.chart elements).

(async () => {
  const HISTORY_KEYS = [
    "population", "food", "births_delta", "deaths_delta",
    "deaths_starvation", "deaths_age", "deaths_combat",
    "avg_energy", "avg_health", "generation_max", "hybrids",
    "species", "clans",
  ].join(",");

  Charts.init();

  // ---- canvas helpers ------------------------------------------------
  function sizeCanvas(cv) {
    const dpr = window.devicePixelRatio || 1;
    const rect = cv.getBoundingClientRect();
    cv.width = Math.max(1, Math.floor(rect.width * dpr));
    cv.height = Math.max(1, Math.floor(rect.height * dpr));
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w: rect.width, h: rect.height };
  }

  // Draw a vertical-bar histogram. `labels` optional (else uses centers).
  function drawHist(id, centers, counts, color, labelFmt) {
    const cv = document.getElementById(id);
    if (!cv) return;
    const { ctx, w, h } = sizeCanvas(cv);
    ctx.clearRect(0, 0, w, h);
    if (!counts || counts.length === 0) return;
    const pad = 18;
    const maxC = Math.max(1, ...counts);
    const n = counts.length;
    const bw = (w - pad) / n;
    ctx.fillStyle = color;
    for (let i = 0; i < n; i++) {
      const bh = (counts[i] / maxC) * (h - pad - 4);
      ctx.fillRect(pad + i * bw + 1, h - pad - bh, Math.max(1, bw - 2), bh);
    }
    // axis baseline
    ctx.strokeStyle = "rgba(255,255,255,0.12)";
    ctx.beginPath(); ctx.moveTo(pad, h - pad); ctx.lineTo(w, h - pad); ctx.stroke();
    // a few x labels
    ctx.fillStyle = "#6b7488";
    ctx.font = "9px Consolas, monospace";
    const ticks = Math.min(5, n);
    for (let t = 0; t < ticks; t++) {
      const i = Math.round((t / (ticks - 1 || 1)) * (n - 1));
      const lbl = labelFmt ? labelFmt(centers[i]) : String(centers[i]);
      ctx.fillText(lbl, pad + i * bw, h - 5);
    }
    // max-count label
    ctx.fillStyle = "#8b93a7";
    ctx.fillText("max " + maxC, pad + 2, 10);
  }

  function renderBars(containerId, rows) {
    // rows: [{label, value, max, color}]
    const el = document.getElementById(containerId);
    if (!el) return;
    const max = Math.max(1, ...rows.map((r) => r.max != null ? r.max : r.value));
    el.innerHTML = rows.map((r) => {
      const pct = Math.min(100, (r.value / max) * 100);
      const col = r.color || "#7ab7ff";
      return `<div class="bar-row"><span class="nm" title="${r.label}">${r.label}</span>`
        + `<span class="track"><span class="fill" style="width:${pct}%;background:${col}"></span></span>`
        + `<span class="val">${r.valLabel != null ? r.valLabel : r.value}</span></div>`;
    }).join("");
  }

  const rgb = (c) => `rgb(${c[0]},${c[1]},${c[2]})`;

  // ---- ecology + lineage poll ---------------------------------------
  async function refreshAnalytics() {
    let a;
    try { a = await fetch("/api/analytics").then(r => r.json()); }
    catch (e) { return; }

    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set("m-tick", a.tick);
    set("m-pop", a.population);
    set("m-food", a.food);
    set("m-species", a.species.length);
    set("m-clans", a.clans.length);
    set("m-hybrids", a.hybrids);
    set("m-gen", a.generation_max);
    set("m-births", a.births_total);
    set("m-deaths", a.deaths_total);

    set("dc-starv", a.death_causes.starvation);
    set("dc-age", a.death_causes.age);
    set("dc-combat", a.death_causes.combat);

    drawHist("hist-age", a.age_hist.centers, a.age_hist.counts, "#7ab7ff", (v) => v.toFixed(1));
    drawHist("hist-energy", a.energy_hist.centers, a.energy_hist.counts, "#f0c864", (v) => v.toFixed(1));
    drawHist("hist-health", a.health_hist.centers, a.health_hist.counts, "#7af2c4", (v) => v.toFixed(1));
    drawHist("hist-gen", a.generations.labels, a.generations.counts, "#c89bff", (v) => "g" + v);

    renderBars("species-bars", a.species.slice(0, 12).map((s) => ({
      label: s.name, value: s.population, color: rgb(s.color),
    })));
    renderBars("clan-bars", a.clans.slice(0, 12).map((c) => ({
      label: c.name, value: c.members, color: rgb(c.color),
    })));

    // species emergence timeline (sorted by founding tick).
    const tl = a.species.slice().sort((x, y) => x.created_tick - y.created_tick).slice(0, 12);
    renderBars("species-timeline", tl.map((s) => ({
      label: s.name, value: s.created_tick, max: a.tick || 1,
      valLabel: "t" + s.created_tick, color: rgb(s.color),
    })));
  }

  // ---- genome explorer ----------------------------------------------
  let geneName = "movement_speed";

  async function loadGeneList() {
    let data;
    try { data = await fetch("/api/analytics/genes").then(r => r.json()); }
    catch (e) { return; }
    const sel = document.getElementById("gene-select");
    let html = "";
    for (const [cat, genes] of Object.entries(data.categories)) {
      html += `<optgroup label="${cat}">`;
      for (const g of genes) {
        const tag = g.active ? "" : " (dormant)";
        html += `<option value="${g.name}">${g.name}${tag}</option>`;
      }
      html += `</optgroup>`;
    }
    sel.innerHTML = html;
    sel.value = geneName;
    sel.addEventListener("change", () => { geneName = sel.value; refreshGene(); });
    document.getElementById("gene-bins").addEventListener("change", refreshGene);
  }

  async function refreshGene() {
    const bins = parseInt(document.getElementById("gene-bins").value, 10) || 24;
    let g;
    try { g = await fetch(`/api/analytics/gene?name=${encodeURIComponent(geneName)}&bins=${bins}`).then(r => r.json()); }
    catch (e) { return; }
    document.getElementById("gene-title").textContent =
      `${g.gene} ${g.active ? "" : "(dormant)"} — distribution`;
    document.getElementById("gene-stat").innerHTML =
      `n=<b>${g.count}</b> mean=<b>${g.mean}</b> std=<b>${g.std}</b>`;
    drawHist("hist-gene", g.hist.centers, g.hist.counts,
      g.active ? "#7af2c4" : "#6b7488", (v) => v.toFixed(2));
    renderBars("gene-species", (g.by_species || []).map((s) => ({
      label: s.name, value: s.mean, max: 1, valLabel: s.mean.toFixed(2), color: rgb(s.color),
    })));
  }

  // ---- collective mind (brain neural-net) ---------------------------
  let mindMode = "collective";
  let mindCreId = null;
  BrainViz.init(document.getElementById("brain-canvas"));

  document.querySelectorAll("#mind-mode button").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#mind-mode button").forEach((x) => x.classList.toggle("active", x === b));
      mindMode = b.dataset.mode;
      document.getElementById("mind-cre-wrap").style.display = mindMode === "creature" ? "" : "none";
      refreshBrain();
    });
  });
  document.getElementById("mind-cre-id").addEventListener("change", (e) => {
    mindCreId = parseInt(e.target.value, 10) || null;
    refreshBrain();
  });

  async function refreshBrain() {
    const stat = document.getElementById("mind-stat");
    const sub = document.getElementById("brain-sub");
    try {
      if (mindMode === "creature" && mindCreId) {
        const c = await API.creature(mindCreId);
        if (c && c.brain) {
          BrainViz.setNet(c.brain);
          stat.innerHTML = `creature <b>#${mindCreId}</b> · <b>${c.archetype || "—"}</b>`;
          if (sub) sub.textContent = `#${mindCreId} · species ${c.species_id}`;
        }
      } else {
        const net = await API.brain(240);
        BrainViz.setNet(net);
        stat.innerHTML = `averaged over <b>${net.sample || 0}</b> of <b>${net.population || 0}</b> minds`;
        if (sub) sub.textContent = "population average";
      }
    } catch (e) { /* server bouncing */ }
  }

  // ---- history + events ---------------------------------------------
  async function refreshHistory() {
    try { Charts.setHistory(await API.history(HISTORY_KEYS, 300)); }
    catch (e) { /* server bouncing */ }
  }

  async function refreshEvents() {
    try {
      const e = await API.events(50);
      const lines = (e.events || []).map((ev) => {
        const p = ev.payload ? " " + JSON.stringify(ev.payload) : "";
        return `t=${ev.tick} ${ev.kind}${p}`;
      });
      document.getElementById("event-log").textContent = lines.join("\n");
      const counts = e.counts || {};
      const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 5)
        .map(([k, v]) => `${k}:${v}`).join(" ");
      document.getElementById("ev-counts").textContent = top ? `(${top})` : "";
    } catch (e) { /* ignore */ }
  }

  // ---- boot ----------------------------------------------------------
  await loadGeneList();
  refreshAnalytics();
  refreshGene();
  refreshHistory();
  refreshEvents();
  refreshBrain();

  setInterval(refreshAnalytics, 1000);
  setInterval(refreshGene, 1500);
  setInterval(refreshHistory, 2000);
  setInterval(refreshEvents, 2500);
  setInterval(refreshBrain, 3000);
  window.addEventListener("resize", () => { refreshAnalytics(); refreshGene(); });
})();
