"""Auxiliary UI widgets used by the debug overlay."""

from __future__ import annotations

from typing import List, Mapping

import pygame

import config


def draw_population_chart(
    surface: pygame.Surface,
    rect: pygame.Rect,
    history: List[Mapping[str, float]],
    font: pygame.font.Font,
) -> None:
    pygame.draw.rect(surface, (18, 20, 26), rect)
    pygame.draw.rect(surface, config.COLOR_PANEL_BORDER, rect, 1)

    if not history:
        label = font.render("population history", True, config.COLOR_TEXT_DIM)
        surface.blit(label, (rect.left + 4, rect.top + 4))
        return

    samples = history[-rect.width:] if len(history) > rect.width else history
    if not samples:
        return

    max_pop = max(1.0, max(float(s.get("population", 0)) for s in samples))
    max_food = max(1.0, max(float(s.get("food", 0)) for s in samples))
    n = len(samples)
    step = (rect.width - 4) / max(1, n - 1) if n > 1 else 0

    pop_points = []
    food_points = []
    for i, s in enumerate(samples):
        x = rect.left + 2 + int(i * step)
        pop_y = rect.bottom - 2 - int((float(s.get("population", 0)) / max_pop) * (rect.height - 4))
        food_y = rect.bottom - 2 - int((float(s.get("food", 0)) / max_food) * (rect.height - 4))
        pop_points.append((x, pop_y))
        food_points.append((x, food_y))

    if len(pop_points) > 1:
        pygame.draw.lines(surface, (240, 200, 100), False, pop_points, 1)
    if len(food_points) > 1:
        pygame.draw.lines(surface, (90, 200, 90), False, food_points, 1)

    label = font.render(f"pop max {int(max_pop)}", True, config.COLOR_TEXT_DIM)
    surface.blit(label, (rect.left + 4, rect.top + 2))
