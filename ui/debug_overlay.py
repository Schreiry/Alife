"""Debug HUD: side panel showing simulation stats + profiler timings.

The text surfaces are cached and only re-rendered every
`config.RENDER_DEBUG_INTERVAL` frames; on intermediate frames we just
re-blit the cached lines. Font rendering is the third-most-expensive
thing pygame does in this scene at high tick rates.
"""

from __future__ import annotations

from typing import List, Tuple

import pygame

import config
from ui.panels import draw_population_chart


class DebugOverlay:
    def __init__(self, rect: pygame.Rect):
        self.rect = rect
        pygame.font.init()
        self._font = pygame.font.SysFont("consolas", 14)
        self._font_bold = pygame.font.SysFont("consolas", 16, bold=True)
        self._cached_lines: List[Tuple[pygame.Surface, Tuple[int, int]]] = []
        self._last_rebuild_frame: int = -1
        self._chart_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)

    def draw(self, surface: pygame.Surface, simulation, frame_idx: int) -> None:
        pygame.draw.rect(surface, config.COLOR_PANEL, self.rect)
        pygame.draw.line(
            surface, config.COLOR_PANEL_BORDER,
            (self.rect.left, 0), (self.rect.left, self.rect.bottom), 1,
        )

        if (frame_idx - self._last_rebuild_frame) >= config.RENDER_DEBUG_INTERVAL:
            self._rebuild_text(simulation)
            self._last_rebuild_frame = frame_idx

        for surf, pos in self._cached_lines:
            surface.blit(surf, pos)

        # Chart redraws every frame — it's a few line segments, very cheap.
        draw_population_chart(
            surface, self._chart_rect, simulation.stats.history, self._font,
        )

    def _rebuild_text(self, simulation) -> None:
        stats = simulation.stats
        prof = simulation.profiler
        lines: List[Tuple[str, bool, Tuple[int, int, int]]] = []

        speed = config.SPEED_LEVELS[simulation.speed_index]
        status = "PAUSED" if simulation.paused else f"x{speed}"

        lines.append(("ALife Simulation", True, config.COLOR_TEXT_ACCENT))
        lines.append(("", False, config.COLOR_TEXT))
        lines.append((f"Tick: {stats.tick}    {status}", False, config.COLOR_TEXT))
        lines.append((
            f"Population: {stats.population} / {config.MAX_CREATURES}",
            False, config.COLOR_TEXT,
        ))
        lines.append((f"Food: {stats.food}", False, config.COLOR_TEXT))
        lines.append((
            f"Species: {stats.species_count}   Clans: {stats.clan_count}",
            False, config.COLOR_TEXT,
        ))
        lines.append((
            f"Hybrids: {stats.hybrid_total}   Gen max: {stats.generation_max}",
            False, config.COLOR_TEXT,
        ))
        lines.append(("", False, config.COLOR_TEXT))

        lines.append(("Performance", False, config.COLOR_TEXT_ACCENT))
        lines.append((
            f"  tick    {prof.get_average('tick'):6.2f} ms",
            False, config.COLOR_TEXT,
        ))
        lines.append((
            f"  render  {prof.get_average('render'):6.2f} ms",
            False, config.COLOR_TEXT,
        ))
        slow_name, slow_avg = prof.slowest_section()
        if slow_name:
            lines.append((
                f"  hot:    {slow_name} ({slow_avg:.2f} ms)",
                False, config.COLOR_TEXT_DIM,
            ))
        lines.append((
            f"  brain   {prof.get_average('brain'):6.2f} ms",
            False, config.COLOR_TEXT_DIM,
        ))
        lines.append((
            f"  vec     {prof.get_average('vec_passive'):6.2f} ms",
            False, config.COLOR_TEXT_DIM,
        ))
        lines.append((
            f"  grid    {prof.get_average('grid_rebuild'):6.2f} ms",
            False, config.COLOR_TEXT_DIM,
        ))
        lines.append(("", False, config.COLOR_TEXT))

        lines.append(("Averages", False, config.COLOR_TEXT_ACCENT))
        lines.append((f"  energy:    {stats.avg_energy:6.1f}", False, config.COLOR_TEXT))
        lines.append((f"  health:    {stats.avg_health:6.1f}", False, config.COLOR_TEXT))
        lines.append((f"  strength:  {stats.avg_strength:6.2f}", False, config.COLOR_TEXT))
        lines.append((f"  intel:     {stats.avg_intelligence:6.2f}", False, config.COLOR_TEXT))
        lines.append((f"  aggression:{stats.avg_aggression:6.2f}", False, config.COLOR_TEXT))
        lines.append((f"  age:       {stats.avg_age:6.0f}", False, config.COLOR_TEXT))
        lines.append(("", False, config.COLOR_TEXT))

        lines.append(("Totals", False, config.COLOR_TEXT_ACCENT))
        lines.append((f"  births:     {stats.births_total}", False, config.COLOR_TEXT))
        lines.append((f"  deaths:     {stats.deaths_total}", False, config.COLOR_TEXT))
        lines.append((f"   starvation:{stats.deaths_by_starvation}",
                      False, config.COLOR_TEXT_DIM))
        lines.append((f"   age:       {stats.deaths_by_age}",
                      False, config.COLOR_TEXT_DIM))
        lines.append((f"   combat:    {stats.deaths_by_combat}",
                      False, config.COLOR_TEXT_DIM))
        lines.append(("", False, config.COLOR_TEXT))

        lines.append(("Controls", False, config.COLOR_TEXT_ACCENT))
        for line in (
            "SPACE  pause / resume",
            "UP     speed +",
            "DOWN   speed -",
            "R      restart",
            "S/L    save / load",
            "E      export stats",
            "ESC    quit",
        ):
            lines.append(("  " + line, False, config.COLOR_TEXT_DIM))

        # Render lines.
        x = self.rect.left + 12
        y = 12
        cached: List[Tuple[pygame.Surface, Tuple[int, int]]] = []
        for text, bold, color in lines:
            font = self._font_bold if bold else self._font
            surf = font.render(text, True, color)
            cached.append((surf, (x, y)))
            y += 20 if bold else (16 if text else 8)
        self._cached_lines = cached

        # Place chart below the text block.
        self._chart_rect = pygame.Rect(
            x - 4, y + 8, self.rect.width - 16, 80,
        )
