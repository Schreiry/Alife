"""FastAPI app: REST control + WebSocket live snapshots + static frontend.

Endpoints implemented per CLAUDE.md §11:

  GET  /                          → frontend/index.html
  GET  /static/...                → frontend assets
  GET  /api/status                → live snapshot
  GET  /api/config                → active configuration
  GET  /api/metrics               → scalar dump
  GET  /api/species               → live species list
  GET  /api/clans                 → live clans list
  GET  /api/creature/{id}         → full creature detail
  GET  /api/genome/{id}           → just the genome (cheaper than /creature)
  GET  /api/events                → recent telemetry events
  GET  /api/history               → metric timeseries (from SQLite)
  GET  /api/checkpoints           → list save files in cwd
  GET  /api/genome_catalog        → 170-gene catalog with active flag
  POST /api/control/pause | resume | toggle | step
  POST /api/control/speed?level=N
  POST /api/control/reset
  POST /api/checkpoints/save?name=…
  POST /api/checkpoints/load?name=…
  POST /api/control/save | load   → legacy aliases
  WS   /ws/live                   → snapshot stream at OBSERVATORY_WS_HZ
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import config
from observatory.analytics import (
    analytics_snapshot,
    ecology_snapshot,
    gene_distribution,
    gene_names,
    territory_snapshot,
)
from observatory.sim_runner import SimRunner
from observatory.snapshot import (
    clans_list,
    config_snapshot,
    creature_detail,
    live_snapshot,
    metrics_now,
    species_list,
)


_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
_runner: Optional[SimRunner] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _runner
    _runner = SimRunner()
    _runner.start()
    try:
        yield
    finally:
        if _runner is not None:
            _runner.stop()


app = FastAPI(title="ALife Observatory", lifespan=lifespan)


def runner() -> SimRunner:
    if _runner is None:
        raise HTTPException(status_code=503, detail="simulation not ready")
    return _runner


# ---------- static frontend ------------------------------------------
@app.get("/")
async def index():
    return FileResponse(_FRONTEND_DIR / "index.html")


@app.get("/analytics")
async def analytics_page():
    return FileResponse(_FRONTEND_DIR / "analytics.html")


if _FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR)), name="static")


# ---------- read REST ------------------------------------------------
@app.get("/api/status")
async def status():
    r = runner()
    snap = r.get_latest_snapshot()
    if snap is None:
        snap = r.with_snapshot(live_snapshot)
    return JSONResponse(snap)


@app.get("/api/config")
async def get_config():
    return JSONResponse(config_snapshot())


@app.get("/api/metrics")
def metrics():
    return JSONResponse(runner().with_snapshot(metrics_now))


@app.get("/api/species")
def species_endpoint():
    return JSONResponse(runner().with_snapshot(species_list))


@app.get("/api/clans")
def clans_endpoint():
    return JSONResponse(runner().with_snapshot(clans_list))


# NOTE: history/events hit SQLite synchronously. They are declared as plain
# `def` (not async) on purpose so FastAPI runs them in a worker thread instead
# of blocking the asyncio event loop — a blocked loop was a major cause of the
# periodic UI freeze (the WS stream pauses while a query runs).
@app.get("/api/history")
def history(
    keys: str = Query("population,food,births_delta,deaths_delta,avg_aggression,avg_intelligence,species,clans"),
    limit: int = 400,
):
    r = runner()
    tel = r.sim.telemetry
    series: dict = {}
    if tel is not None:
        for key in [k.strip() for k in keys.split(",") if k.strip()]:
            rows = tel.metric_history(key, limit=limit)
            series[key] = [{"tick": t, "value": v} for t, v in rows]
    return JSONResponse({"keys": list(series.keys()), "series": series})


# ---------- analytics (research page) --------------------------------
# All sync `def` -> served in the threadpool so the histogram/aggregation
# work never blocks the event loop or the live stream.
@app.get("/api/analytics")
def api_analytics():
    return JSONResponse(runner().with_snapshot(analytics_snapshot))


@app.get("/api/analytics/genes")
def api_analytics_genes():
    return JSONResponse(gene_names())


@app.get("/api/analytics/gene")
def api_analytics_gene(name: str, bins: int = 24):
    res = runner().with_snapshot(lambda s: gene_distribution(s, name, bins))
    if res is None:
        raise HTTPException(404, "unknown gene")
    return JSONResponse(res)


@app.get("/api/analytics/brain")
def api_analytics_brain(sample: int = 240):
    from behavior import brain_net
    return JSONResponse(runner().with_snapshot(lambda s: brain_net.population_net(s, sample)))


@app.get("/api/territory")
def api_territory(block: int = 5):
    return JSONResponse(runner().with_snapshot(lambda s: territory_snapshot(s, block)))


@app.get("/api/ecology")
def api_ecology():
    return JSONResponse(runner().with_snapshot(ecology_snapshot))


@app.get("/api/events")
def events(limit: int = 80, kind: Optional[str] = None):
    r = runner()
    tel = r.sim.telemetry
    if tel is not None:
        return JSONResponse({
            "events": tel.recent_events(limit=limit, kind=kind),
            "counts": tel.event_counts_by_kind(),
        })
    # Fallback when telemetry not initialized.
    return JSONResponse({"events": [], "counts": {}})


@app.get("/api/creature/{cid}")
def get_creature(cid: int):
    r = runner()
    det = r.with_snapshot(lambda sim: creature_detail(sim, cid))
    if det is None:
        raise HTTPException(404, "no such creature")
    return JSONResponse(det)


@app.get("/api/genome/{cid}")
def get_genome(cid: int):
    r = runner()
    det = r.with_snapshot(lambda sim: creature_detail(sim, cid))
    if det is None:
        raise HTTPException(404, "no such creature")
    return JSONResponse({"id": cid, "genome": det["genome"]})


@app.get("/api/genome_catalog")
async def genome_catalog():
    from genetics.genes import ACTIVE_GENES, GENE_CATALOG
    return JSONResponse({
        "count": len(GENE_CATALOG),
        "active_count": len(ACTIVE_GENES),
        "genes": [
            {"name": g.name, "category": g.category,
             "real_min": g.real_min, "real_max": g.real_max,
             "active": g.name in ACTIVE_GENES}
            for g in GENE_CATALOG
        ],
    })


@app.get("/api/checkpoints")
def list_checkpoints():
    from data.save_load import list_checkpoints as _list
    return JSONResponse({"checkpoints": _list(".")})


# ---------- control endpoints ----------------------------------------
@app.post("/api/control/pause")
async def ctl_pause(): runner().submit("pause"); return {"ok": True}


@app.post("/api/control/resume")
async def ctl_resume(): runner().submit("resume"); return {"ok": True}


@app.post("/api/control/toggle")
async def ctl_toggle(): runner().submit("toggle"); return {"ok": True}


@app.post("/api/control/step")
async def ctl_step(): runner().submit("step"); return {"ok": True}


@app.post("/api/control/speed")
async def ctl_speed(level: int = 0): runner().submit("speed", level); return {"ok": True}


@app.post("/api/control/reset")
async def ctl_reset(): runner().submit("reset"); return {"ok": True}


@app.post("/api/control/save")
async def ctl_save(): runner().submit("save"); return {"ok": True}


@app.post("/api/control/load")
async def ctl_load(): runner().submit("load"); return {"ok": True}


@app.post("/api/checkpoints/save")
async def ckpt_save(name: str = "save_state.json"):
    runner().submit("save_named", name)
    return {"ok": True, "path": name}


@app.post("/api/checkpoints/load")
async def ckpt_load(name: str = "save_state.json"):
    runner().submit("load_named", name)
    return {"ok": True, "path": name}


# ---------- WebSocket live stream ------------------------------------
@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    r = runner()
    interval = 1.0 / max(1.0, config.OBSERVATORY_WS_HZ)
    try:
        while True:
            # Forward the snapshot the sim thread already built+encoded. No
            # sim-lock acquisition and no JSON work on the event loop, so a
            # heavy tick can never stall the stream.
            payload = r.get_latest_snapshot_json()
            if payload is None:
                payload = json.dumps(r.with_snapshot(live_snapshot))
            await ws.send_text(payload)
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        print(f"[ws] disconnect: {exc!r}", file=sys.stderr)
        try:
            await ws.close()
        except Exception:
            pass


# ---------- entry point ----------------------------------------------
def _open_browser_when_ready(host: str, port: int, http_check_path: str = "/") -> None:
    """Wait until the HTTP server actually returns a response (not just
    until the socket accepts connections — a stale process may hold the
    port but never respond, which is what caused the empty-response bug)."""
    import http.client
    for attempt in range(60):  # up to ~6s
        try:
            conn = http.client.HTTPConnection(host, port, timeout=0.4)
            conn.request("GET", http_check_path)
            resp = conn.getresponse()
            # Anything that produced response headers is good enough.
            if 200 <= resp.status < 600:
                conn.close()
                break
            conn.close()
        except (ConnectionRefusedError, OSError):
            pass
        except Exception:
            pass
        time.sleep(0.1)
    else:
        print("[observatory] server didn't respond within 6s — not opening browser",
              file=sys.stderr, flush=True)
        return
    url = f"http://{host}:{port}/"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print(f"[observatory] open in browser: {url}", flush=True)


def _find_free_port(host: str, preferred: int, max_attempts: int = 10) -> int:
    """Return `preferred` if free, otherwise scan upward. Returns -1 if
    nothing in the range is available (caller decides how to surface that)."""
    import socket
    for offset in range(max_attempts):
        port = preferred + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    return -1


def _force_utf8_stdout() -> None:
    """Avoid UnicodeEncodeError on Windows consoles with non-UTF-8 codepages
    (cp1251 etc) when we print symbols like → or ·."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def run_server() -> int:
    import uvicorn

    _force_utf8_stdout()
    host = config.OBSERVATORY_HOST
    preferred_port = config.OBSERVATORY_PORT

    port = _find_free_port(host, preferred_port)
    if port < 0:
        print(
            f"[observatory] no free port in {preferred_port}..{preferred_port + 9}.\n"
            f"  Likely cause: a previous ALife process didn't shut down.\n"
            f"  Fix on Windows:  netstat -ano | findstr :{preferred_port}\n"
            f"                   taskkill /F /PID <pid>",
            file=sys.stderr, flush=True,
        )
        return 3
    if port != preferred_port:
        print(f"[observatory] port {preferred_port} busy — using {port} instead",
              flush=True)

    print("[observatory] starting components:", flush=True)
    print("  - simulation thread     (SimRunner)", flush=True)
    print("  - telemetry writer      (SQLite buffered, 2s flush)", flush=True)
    print("  - FastAPI HTTP + WS     (uvicorn)", flush=True)
    print("  - browser auto-launch", flush=True)
    print(f"[observatory] binding http://{host}:{port}/", flush=True)

    if not os.environ.get("ALIFE_NO_BROWSER"):
        threading.Thread(
            target=_open_browser_when_ready,
            args=(host, port),
            daemon=True,
        ).start()

    try:
        uvicorn.run(
            "observatory.server:app",
            host=host,
            port=port,
            log_level="warning",
            reload=False,
        )
    except OSError as exc:
        # The preflight already filtered the common case; this catches
        # races where another process took the port between check and run.
        print(f"[observatory] bind failed: {exc!r}", file=sys.stderr, flush=True)
        return 4
    return 0
