// Minimal multi-series line chart on Canvas2D. Reads timeseries from the
// SQLite-backed /api/history endpoint: each series is [{tick, value}, …].

const Charts = (() => {
  const charts = [];

  function init() {
    document.querySelectorAll("canvas.chart").forEach((cv) => {
      charts.push({
        cv,
        ctx: cv.getContext("2d"),
        // data-series is comma-separated metric keys recognized by /api/history
        series: (cv.dataset.series || "").split(",").filter(Boolean),
        colors: (cv.dataset.colors || "#7ab7ff").split(","),
        data: {},  // key -> [{tick, value}]
      });
    });
    window.addEventListener("resize", resizeAll);
    resizeAll();
  }

  function resizeAll() {
    const dpr = window.devicePixelRatio || 1;
    for (const c of charts) {
      const rect = c.cv.getBoundingClientRect();
      c.cv.width = Math.max(1, Math.floor(rect.width * dpr));
      c.cv.height = Math.max(1, Math.floor(rect.height * dpr));
      c.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw(c);
    }
  }

  // history: { keys: [...], series: { key: [{tick, value}, …] } }
  function setHistory(history) {
    const series = (history && history.series) || {};
    for (const c of charts) {
      c.data = {};
      for (const key of c.series) c.data[key] = series[key] || [];
      draw(c);
    }
  }

  function draw(c) {
    const dpr = window.devicePixelRatio || 1;
    const w = c.cv.width / dpr;
    const h = c.cv.height / dpr;
    const ctx = c.ctx;
    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = "rgba(255,255,255,0.05)";
    ctx.lineWidth = 1;
    for (let i = 1; i < 4; i++) {
      const y = (h / 4) * i;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }

    let hasData = false;
    for (const key of c.series) {
      if ((c.data[key] || []).length >= 2) { hasData = true; break; }
    }
    if (!hasData) {
      ctx.fillStyle = "#535864";
      ctx.font = "11px Consolas, monospace";
      ctx.fillText("collecting…", 4, 12);
      return;
    }

    // Each series uses its own value-axis (so multi-scale plots like
    // species+clans don't suppress one).
    for (let s = 0; s < c.series.length; s++) {
      const key = c.series[s];
      const points = c.data[key] || [];
      if (points.length < 2) continue;
      let max = 1;
      let minTick = Infinity, maxTick = -Infinity;
      for (const p of points) {
        if (p.value > max) max = p.value;
        if (p.tick < minTick) minTick = p.tick;
        if (p.tick > maxTick) maxTick = p.tick;
      }
      const span = Math.max(1, maxTick - minTick);
      ctx.strokeStyle = c.colors[s] || "#7ab7ff";
      ctx.lineWidth = 1.25;
      ctx.beginPath();
      for (let i = 0; i < points.length; i++) {
        const x = (w * (points[i].tick - minTick)) / span;
        const y = h - (points[i].value / max) * (h - 4) - 2;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      const last = points[points.length - 1].value;
      ctx.fillStyle = c.colors[s] || "#7ab7ff";
      ctx.font = "10px Consolas, monospace";
      const labelVal = Number.isInteger(last) ? last : last.toFixed(2);
      ctx.fillText(`${key}: ${labelVal}`, 4, 12 + s * 12);
    }
  }

  return { init, setHistory };
})();
