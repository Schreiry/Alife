// Clan and species inspectors. Hooked into the inspector tabs.

const Panels = (() => {
  let lastClansRender = 0;
  let lastSpeciesRender = 0;

  async function refreshClans() {
    try {
      const data = await API.clans();
      const root = document.getElementById("clan-list");
      if (!root) return;
      root.innerHTML = (data.clans || []).slice(0, 30).map((c) => {
        const [r, g, b] = c.color;
        const rels = Object.entries(c.relations)
          .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
          .slice(0, 3)
          .map(([id, v]) => `${id}:${v > 0 ? "+" : ""}${v.toFixed(2)}`)
          .join(" ");
        return `<div class="entity">
          <span class="swatch" style="background:rgb(${r},${g},${b})"></span>
          <span class="name">${c.name}</span>
          <span class="meta">${c.members} members · terr ${c.territory} · agg ${c.aggression}</span>
          <span class="rels">${rels || "—"}</span>
        </div>`;
      }).join("") || "<div class='empty'>no clans yet</div>";
      lastClansRender = Date.now();
    } catch (e) { /* server transient */ }
  }

  async function refreshSpecies() {
    try {
      const data = await API.species();
      const root = document.getElementById("species-list");
      if (!root) return;
      root.innerHTML = (data.species || []).slice(0, 30).map((s) => {
        const [r, g, b] = s.color;
        return `<div class="entity">
          <span class="swatch" style="background:rgb(${r},${g},${b})"></span>
          <span class="name">${s.name}</span>
          <span class="meta">pop ${s.population} · founder #${s.founder} · since t=${s.created_tick}</span>
        </div>`;
      }).join("") || "<div class='empty'>no species yet</div>";
      lastSpeciesRender = Date.now();
    } catch (e) { /* ignore */ }
  }

  function init() {
    setInterval(refreshClans, 2000);
    setInterval(refreshSpecies, 2500);
    refreshClans();
    refreshSpecies();
  }

  return { init };
})();
