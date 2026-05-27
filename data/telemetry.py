"""SQLite-backed telemetry sink with buffered writes.

Werld-inspired observation layer: the simulation core emits structured
events synchronously (cheap — just an append to a Python list); a
background flusher batches them into SQLite every `flush_interval`
seconds or when the buffer hits `flush_size`. This keeps the hot tick
free of any disk I/O.

Schema:
  events(id INTEGER PK, tick INTEGER, ts REAL, kind TEXT, payload TEXT)
  metrics(tick INTEGER, key TEXT, value REAL, PRIMARY KEY(tick, key))

Events are append-only and used for the dashboard event log + post-hoc
lineage analysis. Metrics are sparse rolling timeseries (births per
window, avg energy, etc.) and back the chart endpoints.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    tick    INTEGER NOT NULL,
    ts      REAL    NOT NULL,
    kind    TEXT    NOT NULL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_tick ON events(tick);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);

CREATE TABLE IF NOT EXISTS metrics (
    tick  INTEGER NOT NULL,
    key   TEXT    NOT NULL,
    value REAL    NOT NULL,
    PRIMARY KEY(tick, key)
);
CREATE INDEX IF NOT EXISTS idx_metrics_key ON metrics(key);
"""


class Telemetry:
    """Thread-safe buffered telemetry sink."""

    def __init__(
        self,
        db_path: str = "telemetry.db",
        flush_interval: float = 2.0,
        flush_size: int = 500,
        max_events_kept: int = 100_000,
    ):
        self.db_path = db_path
        self.flush_interval = flush_interval
        self.flush_size = flush_size
        self.max_events_kept = max_events_kept

        self._lock = threading.Lock()
        self._event_buf: List[Tuple[int, float, str, Optional[str]]] = []
        self._metric_buf: List[Tuple[int, str, float]] = []

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._init_db()

    def _init_db(self) -> None:
        # Ensure parent directory exists when db_path is e.g. data/telemetry.db.
        directory = os.path.dirname(os.path.abspath(self.db_path)) or "."
        os.makedirs(directory, exist_ok=True)
        with sqlite3.connect(self.db_path) as con:
            con.executescript(_SCHEMA)
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")

    # ---------- emit (hot path) -----------------------------------------
    def emit_event(self, tick: int, kind: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Cheap: appends to a Python list under a single lock."""
        payload_str = json.dumps(payload) if payload else None
        with self._lock:
            self._event_buf.append((tick, time.time(), kind, payload_str))

    def emit_metric(self, tick: int, key: str, value: float) -> None:
        with self._lock:
            self._metric_buf.append((tick, key, float(value)))

    def buffer_size(self) -> int:
        with self._lock:
            return len(self._event_buf) + len(self._metric_buf)

    # ---------- flush --------------------------------------------------
    def _swap_buffers(
        self,
    ) -> Tuple[List[Tuple[int, float, str, Optional[str]]],
               List[Tuple[int, str, float]]]:
        with self._lock:
            ev = self._event_buf
            mt = self._metric_buf
            self._event_buf = []
            self._metric_buf = []
        return ev, mt

    def flush(self) -> None:
        events, metrics = self._swap_buffers()
        if not events and not metrics:
            return
        try:
            with sqlite3.connect(self.db_path, timeout=5.0) as con:
                if events:
                    con.executemany(
                        "INSERT INTO events(tick, ts, kind, payload) VALUES(?,?,?,?)",
                        events,
                    )
                if metrics:
                    con.executemany(
                        "INSERT OR REPLACE INTO metrics(tick, key, value) VALUES(?,?,?)",
                        metrics,
                    )
                if self.max_events_kept > 0:
                    con.execute(
                        "DELETE FROM events WHERE id IN ("
                        "SELECT id FROM events ORDER BY id DESC LIMIT -1 OFFSET ?)",
                        (self.max_events_kept,),
                    )
        except sqlite3.Error as exc:
            # Telemetry must NEVER break the simulation; log once via stderr.
            import sys
            print(f"[telemetry] flush failed: {exc!r}", file=sys.stderr)

    # ---------- background thread --------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, name="alife-telemetry", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self.flush()

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self.buffer_size() >= self.flush_size:
                self.flush()
            else:
                self._stop.wait(self.flush_interval)
                if not self._stop.is_set():
                    self.flush()

    # ---------- queries (UI side) --------------------------------------
    def recent_events(
        self,
        limit: int = 100,
        kind: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path, timeout=2.0) as con:
            con.row_factory = sqlite3.Row
            if kind:
                rows = con.execute(
                    "SELECT tick, ts, kind, payload FROM events WHERE kind = ?"
                    " ORDER BY id DESC LIMIT ?",
                    (kind, limit),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT tick, ts, kind, payload FROM events"
                    " ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            {
                "tick": r["tick"],
                "ts": r["ts"],
                "kind": r["kind"],
                "payload": json.loads(r["payload"]) if r["payload"] else None,
            }
            for r in rows
        ]

    def metric_history(self, key: str, limit: int = 500) -> List[Tuple[int, float]]:
        with sqlite3.connect(self.db_path, timeout=2.0) as con:
            rows = con.execute(
                "SELECT tick, value FROM metrics WHERE key = ?"
                " ORDER BY tick DESC LIMIT ?",
                (key, limit),
            ).fetchall()
        rows.reverse()
        return [(int(t), float(v)) for t, v in rows]

    def event_counts_by_kind(self) -> Dict[str, int]:
        with sqlite3.connect(self.db_path, timeout=2.0) as con:
            rows = con.execute(
                "SELECT kind, COUNT(*) FROM events GROUP BY kind"
            ).fetchall()
        return {k: int(c) for k, c in rows}
