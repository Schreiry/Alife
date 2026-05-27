// Thin wrapper around fetch + WebSocket. No abstractions beyond what
// the three other modules genuinely need.

const API = (() => {
  const base = "";  // same-origin

  async function get(path) {
    const res = await fetch(base + path);
    if (!res.ok) throw new Error(path + " -> " + res.status);
    return res.json();
  }

  async function post(path) {
    const res = await fetch(base + path, { method: "POST" });
    if (!res.ok) throw new Error(path + " -> " + res.status);
    return res.json();
  }

  function liveSocket(onMessage, onClose) {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = proto + "://" + location.host + "/ws/live";
    let ws = null;
    let stopped = false;
    let reconnectTimer = null;

    function connect() {
      ws = new WebSocket(url);
      ws.onmessage = (ev) => {
        try { onMessage(JSON.parse(ev.data)); }
        catch (e) { console.warn("ws parse", e); }
      };
      ws.onclose = () => {
        if (onClose) onClose();
        if (!stopped) {
          reconnectTimer = setTimeout(connect, 1000);
        }
      };
      ws.onerror = () => { try { ws.close(); } catch (_) {} };
    }
    connect();

    return {
      close() {
        stopped = true;
        if (reconnectTimer) clearTimeout(reconnectTimer);
        if (ws) try { ws.close(); } catch (_) {}
      },
    };
  }

  return {
    status: () => get("/api/status"),
    metrics: () => get("/api/metrics"),
    config: () => get("/api/config"),
    history: (keys = "", limit = 400) =>
      get("/api/history?limit=" + limit + (keys ? "&keys=" + encodeURIComponent(keys) : "")),
    events: (limit = 80) => get("/api/events?limit=" + limit),
    species: () => get("/api/species"),
    clans: () => get("/api/clans"),
    creature: (id) => get("/api/creature/" + id),
    genome: (id) => get("/api/genome/" + id),
    catalog: () => get("/api/genome_catalog"),
    checkpoints: () => get("/api/checkpoints"),
    pause: () => post("/api/control/pause"),
    resume: () => post("/api/control/resume"),
    toggle: () => post("/api/control/toggle"),
    step: () => post("/api/control/step"),
    speed: (n) => post("/api/control/speed?level=" + n),
    reset: () => post("/api/control/reset"),
    save: () => post("/api/control/save"),
    load: () => post("/api/control/load"),
    liveSocket,
  };
})();
