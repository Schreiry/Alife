// Wires the topbar buttons + speed selector. App.js feeds back paused
// state so Pause/Resume label is always accurate.

const Controls = (() => {
  const SPEED_LEVELS = [1, 2, 3, 5, 8, 12];

  function init() {
    const sel = document.getElementById("sel-speed");
    SPEED_LEVELS.forEach((lv, i) => {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = "x" + lv;
      sel.appendChild(opt);
    });

    document.getElementById("btn-pause").addEventListener("click", () => API.toggle());
    document.getElementById("btn-step").addEventListener("click", () => API.step());
    document.getElementById("btn-reset").addEventListener("click", () => {
      if (confirm("Reset the world?")) API.reset();
    });
    document.getElementById("btn-save").addEventListener("click", () => API.save());
    document.getElementById("btn-load").addEventListener("click", () => API.load());
    sel.addEventListener("change", (ev) => API.speed(Number(ev.target.value)));
  }

  function reflectState(snap) {
    document.getElementById("btn-pause").textContent = snap.paused ? "Resume" : "Pause";
    const sel = document.getElementById("sel-speed");
    const wanted = SPEED_LEVELS.indexOf(snap.speed);
    if (wanted >= 0 && sel.value !== String(wanted)) {
      sel.value = String(wanted);
    }
  }

  return { init, reflectState };
})();
