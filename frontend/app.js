// Top-level controller. Owns the WebSocket, dispatches snapshots into
// the renderer / charts / topbar, fetches history + events at lower
// frequencies, handles the inspector panel and tab switching.

(async () => {
  let catalogByCategory = null;
  let lastSelected = null;
  let wsMsgCount = 0;
  let wsHzLastT = performance.now();
  let wsHz = 0;

  Charts.init();
  Renderer.init();
  Controls.init();
  Panels.init();
  initTabs();

  Renderer.setOnSelect((cid) => {
    lastSelected = cid;
    setTab("creature");
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
  setInterval(refreshEvents, 1500);
  setInterval(() => {
    if (lastSelected) refreshInspector();
  }, 800);
  setInterval(updatePerfCounters, 1000);
  refreshHistory();
  refreshEvents();

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

  function updateTopbar(s) {
    const set = (id, v) => { document.getElementById(id).textContent = v; };
    set("m-tick", s.tick);
    set("m-pop", `${s.population}/${s.max_population}`);
    set("m-food", s.food_count);
    set("m-species", s.species_count);
    set("m-clans", s.clan_count);
    set("m-hybrids", s.hybrids);
    set("m-gen", s.generation_max);
    set("m-births", s.births);
    set("m-deaths", s.deaths);
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

  async function refreshEvents() {
    try {
      const e = await API.events(40);
      const lines = (e.events || []).map((ev) => {
        const p = ev.payload ? " " + JSON.stringify(ev.payload) : "";
        return `t=${ev.tick} ${ev.kind}${p}`;
      });
      document.getElementById("event-log").textContent = lines.join("\n");
      const counts = e.counts || {};
      const top = Object.entries(counts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 4)
        .map(([k, v]) => `${k}:${v}`).join(" ");
      document.getElementById("ev-counts").textContent = top ? `(${top})` : "";
    } catch (e) { /* ignore */ }
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

  function renderInspector(c) {
    document.getElementById("inspector-empty").hidden = true;
    document.getElementById("inspector-content").hidden = false;

    const set = (id, v) => { document.getElementById(id).textContent = v; };
    set("ic-id", c.id);
    set("ic-archetype", c.archetype ?? "—");
    set("ic-age", `${c.age} / ${c.lifespan}`);
    set("ic-gen", c.generation);
    set("ic-species", c.species_id);
    set("ic-clan", c.clan_id ?? "—");
    set("ic-sex", c.sex === 0 ? "♀" : "♂");
    set("ic-hybrid", c.is_hybrid ? "yes" : "no");
    set("ic-energy", `${c.energy.toFixed(1)} / ${c.max_energy.toFixed(1)}`);
    set("ic-health", `${c.health.toFixed(1)} / ${c.max_health.toFixed(1)}`);
    set("ic-action", c.last_action);
    set("ic-parents", `${c.parent_a ?? "—"} × ${c.parent_b ?? "—"}`);

    const root = document.getElementById("ic-genome");
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

  async function groupCatalog() {
    const cat = await API.catalog();
    const groups = new Map();
    for (const g of cat.genes) {
      if (!groups.has(g.category)) groups.set(g.category, []);
      groups.get(g.category).push(g);
    }
    return groups;
  }

  function initTabs() {
    document.querySelectorAll(".tabs .tab").forEach((btn) => {
      btn.addEventListener("click", () => setTab(btn.dataset.tab));
    });
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
