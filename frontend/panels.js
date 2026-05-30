// Clan and species inspectors — rich, color-coded info cards.

const Panels = (() => {
  async function refreshClans() {
    try {
      const data = await API.clans();
      const root = document.getElementById("clan-list");
      if (!root) return;
      root.innerHTML = (data.clans || []).slice(0, 30).map((c) => {
        const [r, g, b] = c.color;
        const col = `rgb(${r},${g},${b})`;
        const rels = Object.entries(c.relations || {})
          .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
          .slice(0, 4)
          .map(([id, v]) => {
            const cls = v <= -0.5 ? "war" : v >= 0.5 ? "ally" : "neu";
            return `<span class="rel ${cls}">#${id} ${v > 0 ? "+" : ""}${v.toFixed(2)}</span>`;
          })
          .join("");
        const wars = c.wars ? `<span class="tag war">⚔ ${c.wars}</span>` : "";
        const allies = c.allies ? `<span class="tag ally">⚭ ${c.allies}</span>` : "";
        return `<div class="info-card" style="--accent:${col}">
          <div class="ic-head">
            <span class="dotc" style="background:${col}"></span>
            <span class="ic-title" style="color:${col}">${c.name}</span>
            <span class="ic-tags">${wars}${allies}</span>
          </div>
          <div class="ic-grid">
            <span><i>members</i><b>${c.members}</b></span>
            <span><i>territory</i><b>${c.territory}</b></span>
            <span><i>aggression</i><b>${c.aggression}</b></span>
            <span><i>ideology</i><b>${c.ideology}</b></span>
            <span><i>stability</i><b>${c.stability}</b></span>
            <span><i>leader</i><b>#${c.leader}</b></span>
          </div>
          ${rels ? `<div class="ic-rels">${rels}</div>` : ""}
        </div>`;
      }).join("") || "<div class='empty'>no clans yet — they form as leaders gather followers</div>";
    } catch (e) { /* server transient */ }
  }

  async function refreshSpecies() {
    try {
      const data = await API.species();
      const root = document.getElementById("species-list");
      if (!root) return;
      const top = (data.species || [])[0];
      const maxPop = top ? top.population : 1;
      root.innerHTML = (data.species || []).slice(0, 30).map((s) => {
        const [r, g, b] = s.color;
        const col = `rgb(${r},${g},${b})`;
        const frac = Math.max(0.04, s.population / maxPop) * 100;
        return `<div class="info-card" style="--accent:${col}">
          <div class="ic-head">
            <span class="dotc" style="background:${col}"></span>
            <span class="ic-title" style="color:${col}">${s.name}</span>
            <span class="ic-big">${s.population}</span>
          </div>
          <div class="ic-bar"><div class="ic-bar-fill" style="width:${frac}%;background:${col}"></div></div>
          <div class="ic-grid">
            <span><i>founder</i><b>#${s.founder}</b></span>
            <span><i>since tick</i><b>${s.created_tick.toLocaleString()}</b></span>
          </div>
        </div>`;
      }).join("") || "<div class='empty'>no species yet</div>";
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
