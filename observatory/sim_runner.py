"""Background simulation thread.

Owns the Simulation instance; exposes thread-safe controls and a snapshot
lock so the FastAPI side can extract state without seeing torn arrays.

We run the tick loop in plain Python (no asyncio inside the sim) and let
the FastAPI side drive its own async loop. The two communicate through:
  - `self.sim` (read under `snapshot_lock`)
  - `self.command_queue` (write-only from any thread)
"""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Callable, Optional, Tuple

import config


class SimRunner:
    def __init__(self, telemetry_path: str = "telemetry.db") -> None:
        from core.simulation import Simulation
        from data.telemetry import Telemetry
        self.telemetry = Telemetry(db_path=telemetry_path)
        self.telemetry.start()
        self.sim = Simulation(telemetry=self.telemetry)
        self.snapshot_lock = threading.Lock()
        self.command_queue: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Consecutive tick-error counter. A single transient error no longer
        # silently pauses the whole sim (which looked like a "freeze"); we
        # only give up after many errors in a row.
        self._tick_errors: int = 0

        # Published snapshot (built by the sim thread, read lock-free by the
        # WebSocket / HTTP side). Decouples render from the tick loop so a
        # heavy tick can't stall the stream, and keeps JSON encoding off the
        # asyncio event loop entirely.
        self._latest_snapshot: Optional[dict] = None
        self._latest_snapshot_json: Optional[str] = None
        self._snap_interval: float = 1.0 / max(1.0, getattr(config, "SNAPSHOT_HZ", 30.0))
        self._last_snap_t: float = 0.0
        # In-memory event mirror (kept tiny). Authoritative log lives in
        # SQLite via self.telemetry; this is only for fast UI fallback.
        self.events: list[str] = []
        self.events_lock = threading.Lock()

    # ---------- control surface ------------------------------------
    def submit(self, cmd: str, payload: Any = None) -> None:
        self.command_queue.put((cmd, payload))

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        try:
            self.telemetry.stop()
        except Exception:
            pass

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="alife-sim", daemon=True,
        )
        self._thread.start()

    # ---------- main loop -------------------------------------------
    def _run(self) -> None:
        target_dt = 1.0 / max(1.0, config.OBSERVATORY_SIM_HZ)
        next_t = time.perf_counter()
        self._tune_gc()
        self._publish_snapshot()  # so the UI has data before the first tick
        while not self._stop_event.is_set():
            self._drain_commands()

            now = time.perf_counter()
            if now < next_t:
                # Sleep just long enough; avoid busy-waiting.
                time.sleep(min(0.005, next_t - now))
                # Still refresh the published snapshot while paused/idle so a
                # paused world keeps streaming its (static) state.
                if now - self._last_snap_t >= self._snap_interval:
                    self._publish_snapshot()
                    self._last_snap_t = now
                continue

            # Catch up at most a handful of ticks if we fell behind, so a
            # GC pause or a slow tick doesn't snowball into a runaway loop.
            steps = 1
            if self.sim.paused:
                steps = 0
            else:
                steps = self.sim.steps_per_frame
                steps = min(steps, config.MAX_STEPS_PER_FRAME)

            if steps:
                with self.snapshot_lock:
                    try:
                        for _ in range(steps):
                            self.sim._tick()
                        self._tick_errors = 0
                    except Exception as exc:
                        import sys
                        import traceback
                        self._tick_errors += 1
                        self.sim.profiler.last_exception = repr(exc)
                        self._log_event(f"[error] tick raised: {exc!r}")
                        # Surface the first few loudly so a "freeze" is
                        # diagnosable, but keep ticking — a transient error
                        # must not silently halt the world.
                        if self._tick_errors <= 3:
                            print(f"[sim] tick {self.sim.world.tick} raised: {exc!r}",
                                  file=sys.stderr)
                            traceback.print_exc()
                        if self._tick_errors >= 50:
                            self._log_event("[error] too many tick errors -> pausing")
                            print("[sim] too many consecutive tick errors -> pausing",
                                  file=sys.stderr, flush=True)
                            self.sim.paused = True

            # Republish the snapshot for the stream (sim thread owns this, so
            # it needs no lock against itself and never blocks the WS side).
            now2 = time.perf_counter()
            if now2 - self._last_snap_t >= self._snap_interval:
                self._publish_snapshot()
                self._last_snap_t = now2

            # Advance the schedule by ONE base interval regardless of how many
            # ticks this slot ran. The speed multiplier == ticks-per-slot, so a
            # higher speed runs more ticks per interval (higher tps), instead of
            # the old `* steps` which cancelled out and pinned tps at SIM_HZ for
            # every speed level (x2 looked identical to x1, just choppier).
            next_t += target_dt
            # If we've drifted way behind (heavy ticks) or way ahead (machine
            # was suspended), resync so the loop neither busy-spins nor stalls.
            now3 = time.perf_counter()
            if next_t < now3 - 1.0 or next_t > now3 + 1.0:
                next_t = now3

    # ---------- snapshot publishing ---------------------------------
    def _tune_gc(self) -> None:
        """Reduce GC-induced stutter. The tick loop allocates many short-lived
        objects (per-creature Perception, action enums, temp lists); a gen-2
        collection scanning everything causes periodic ~tens-of-ms pauses that
        hold the GIL and stall the whole process (sim + server). We freeze the
        long-lived startup objects so they're never rescanned, and raise the
        thresholds so collections are far rarer."""
        import gc
        try:
            gc.collect()
            gc.freeze()
            gc.set_threshold(50_000, 500, 1000)
        except Exception:
            pass

    def _publish_snapshot(self) -> None:
        """Build the live snapshot once and stash it (dict + JSON). Runs on the
        sim thread between ticks, so it reads consistent state without locking
        and keeps JSON encoding off the asyncio event loop."""
        from observatory.snapshot import live_snapshot
        try:
            snap = live_snapshot(self.sim)
            self._latest_snapshot = snap
            self._latest_snapshot_json = json.dumps(snap)
        except Exception as exc:
            self._log_event(f"[snapshot error] {exc!r}")

    def get_latest_snapshot(self) -> Optional[dict]:
        return self._latest_snapshot

    def get_latest_snapshot_json(self) -> Optional[str]:
        return self._latest_snapshot_json

    # ---------- commands --------------------------------------------
    def _drain_commands(self) -> None:
        while True:
            try:
                cmd, payload = self.command_queue.get_nowait()
            except queue.Empty:
                return
            self._apply(cmd, payload)

    def _apply(self, cmd: str, payload: Any) -> None:
        sim = self.sim
        if cmd == "pause":
            sim.paused = True
            self._log_event("paused")
        elif cmd == "resume":
            sim.paused = False
            self._log_event("resumed")
        elif cmd == "toggle":
            sim.toggle_pause()
            self._log_event("paused" if sim.paused else "resumed")
        elif cmd == "step":
            # One-off tick even while paused.
            with self.snapshot_lock:
                sim._tick()
        elif cmd == "speed":
            idx = int(payload) if payload is not None else 0
            idx = max(0, min(len(config.SPEED_LEVELS) - 1, idx))
            sim.speed_index = idx
            self._log_event(f"speed→ x{config.SPEED_LEVELS[idx]}")
        elif cmd == "reset":
            with self.snapshot_lock:
                sim.reset()
            self._log_event("reset")
        elif cmd == "save":
            self._do_save(sim, "save_state.json")
        elif cmd == "load":
            self._do_load(sim, "save_state.json")
        elif cmd == "save_named":
            self._do_save(sim, str(payload or "save_state.json"))
        elif cmd == "load_named":
            self._do_load(sim, str(payload or "save_state.json"))

    def _do_save(self, sim, path: str) -> None:
        from data import save_load
        try:
            with self.snapshot_lock:
                info = save_load.save(sim.world, sim.stats, path=path, rng=sim.rng)
            self._log_event(f"saved {path} tick={info['tick']} cre={info['creatures']}")
        except Exception as exc:
            self._log_event(f"[save error] {exc!r}")

    def _do_load(self, sim, path: str) -> None:
        from data import save_load
        with self.snapshot_lock:
            ok = save_load.load(sim, path=path)
        self._log_event(f"load {path} {'ok' if ok else 'failed'}")

    def _log_event(self, msg: str) -> None:
        with self.events_lock:
            self.events.append(f"t={self.sim.world.tick} {msg}")
            if len(self.events) > 200:
                self.events = self.events[-200:]

    # ---------- read helpers ----------------------------------------
    def with_snapshot(self, fn: Callable[[Any], Any]) -> Any:
        with self.snapshot_lock:
            return fn(self.sim)

    def recent_events(self, n: int = 30) -> list[str]:
        with self.events_lock:
            return list(self.events[-n:])
