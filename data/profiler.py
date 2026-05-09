"""Lightweight section profiler.

Wrap hot blocks with `with profiler.section('name'):` (or use the
matching start/end methods). Reports rolling averages over the last
`window` samples, plus the slowest section in the last sample. Cheap
enough to leave on in production builds.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple


class _SectionTimer:
    __slots__ = ("samples", "_start")

    def __init__(self, window: int):
        self.samples: Deque[float] = deque(maxlen=window)
        self._start: Optional[float] = None


class PerformanceProfiler:
    def __init__(self, window: int = 120):
        self.window = window
        self._sections: Dict[str, _SectionTimer] = {}
        self.counters: Dict[str, int] = {}
        self.last_frame_ms: float = 0.0
        self._frame_start: float = 0.0

    # ---------- sections -------------------------------------------------
    def start_section(self, name: str) -> None:
        timer = self._sections.get(name)
        if timer is None:
            timer = _SectionTimer(self.window)
            self._sections[name] = timer
        timer._start = time.perf_counter()

    def end_section(self, name: str) -> None:
        timer = self._sections.get(name)
        if timer is None or timer._start is None:
            return
        timer.samples.append((time.perf_counter() - timer._start) * 1000.0)
        timer._start = None

    def section(self, name: str):
        return _SectionContext(self, name)

    # ---------- counters -------------------------------------------------
    def add(self, key: str, n: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + n

    def set(self, key: str, value: int) -> None:
        self.counters[key] = value

    def reset_counters(self) -> None:
        self.counters.clear()

    # ---------- queries --------------------------------------------------
    def get_average(self, name: str) -> float:
        timer = self._sections.get(name)
        if timer is None or not timer.samples:
            return 0.0
        return sum(timer.samples) / len(timer.samples)

    def get_last(self, name: str) -> float:
        timer = self._sections.get(name)
        if timer is None or not timer.samples:
            return 0.0
        return timer.samples[-1]

    def slowest_section(self) -> Tuple[str, float]:
        slowest_name = ""
        slowest_avg = 0.0
        for name, timer in self._sections.items():
            if not timer.samples:
                continue
            avg = sum(timer.samples) / len(timer.samples)
            if avg > slowest_avg:
                slowest_avg = avg
                slowest_name = name
        return slowest_name, slowest_avg

    def render_debug_lines(self) -> List[str]:
        lines: List[str] = []
        # Frame + tick first.
        if "tick" in self._sections:
            lines.append(f"tick     {self.get_average('tick'):6.2f}ms (avg)")
        if "render" in self._sections:
            lines.append(f"render   {self.get_average('render'):6.2f}ms (avg)")
        # Then top sections by average.
        order = sorted(
            ((self.get_average(name), name) for name in self._sections),
            reverse=True,
        )
        for avg, name in order:
            if name in ("tick", "render") or avg < 0.05:
                continue
            lines.append(f"  {name:<14}{avg:6.2f}ms")
            if len(lines) >= 10:
                break
        return lines

    # ---------- frame --------------------------------------------------
    def begin_frame(self) -> None:
        self._frame_start = time.perf_counter()

    def end_frame(self) -> None:
        self.last_frame_ms = (time.perf_counter() - self._frame_start) * 1000.0


class _SectionContext:
    __slots__ = ("_profiler", "_name")

    def __init__(self, profiler: PerformanceProfiler, name: str):
        self._profiler = profiler
        self._name = name

    def __enter__(self) -> "_SectionContext":
        self._profiler.start_section(self._name)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._profiler.end_section(self._name)
