"""Background simulation thread.

Owns the Simulation instance; exposes thread-safe controls and a snapshot
lock so the FastAPI side can extract state without seeing torn arrays.

We run the tick loop in plain Python (no asyncio inside the sim) and let
the FastAPI side drive its own async loop. The two communicate through:
  - `self.sim` (read under `snapshot_lock`)
  - `self.command_queue` (write-only from any thread)
"""

from __future__ import annotations

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
        while not self._stop_event.is_set():
            self._drain_commands()

            now = time.perf_counter()
            if now < next_t:
                # Sleep just long enough; avoid busy-waiting.
                time.sleep(min(0.005, next_t - now))
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
                    except Exception as exc:
                        self._log_event(f"[error] tick raised: {exc!r}")
                        self.sim.profiler.last_exception = repr(exc)
                        self.sim.paused = True

            next_t += target_dt * max(1, steps)
            # If we've drifted way ahead (system was suspended), resync.
            if next_t < time.perf_counter() - 1.0:
                next_t = time.perf_counter()

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
