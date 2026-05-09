"""ALife simulation entry point.

Decoupled main loop: render runs at FPS, simulation runs as many ticks as
the speed multiplier asks for, capped at MAX_STEPS_PER_FRAME so the UI
stays responsive even when the simulation is heavy. If the simulation
falls behind, we drop ticks rather than freeze.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

import config  # noqa: E402
from core.simulation import Simulation  # noqa: E402
from data import save_load  # noqa: E402
from rendering.renderer import Renderer  # noqa: E402


def _make_window_size() -> tuple[int, int]:
    # The renderer caps the world rect, so the actual window size mirrors
    # whatever the renderer decides. We compute the same numbers here so
    # pygame opens a window the renderer will fully fill.
    from rendering.renderer import _MAX_VIEWPORT_PX
    w_world = min(_MAX_VIEWPORT_PX, config.WORLD_WIDTH * config.TILE_SIZE)
    h_world = min(_MAX_VIEWPORT_PX, config.WORLD_HEIGHT * config.TILE_SIZE)
    return (w_world + config.UI_PANEL_WIDTH, h_world)


def main() -> int:
    pygame.init()
    pygame.display.set_caption(config.WINDOW_TITLE)
    window_size = _make_window_size()
    surface = pygame.display.set_mode(window_size)
    clock = pygame.time.Clock()

    simulation = Simulation()
    renderer = Renderer(surface)

    running = True
    while running:
        # --- input ----------------------------------------------------
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    simulation.toggle_pause()
                elif event.key == pygame.K_UP:
                    simulation.speed_up()
                elif event.key == pygame.K_DOWN:
                    simulation.speed_down()
                elif event.key == pygame.K_r:
                    simulation.reset()
                elif event.key == pygame.K_s:
                    save_load.save(simulation.world, simulation.stats)
                elif event.key == pygame.K_l:
                    save_load.load(simulation)
                elif event.key == pygame.K_e:
                    simulation.stats.export_json(config.STATS_EXPORT_PATH)

        # --- update (capped) ------------------------------------------
        simulation.update(max_steps=config.MAX_STEPS_PER_FRAME)

        # --- render ---------------------------------------------------
        renderer.draw(simulation)
        pygame.display.flip()
        clock.tick(config.FPS)

    pygame.quit()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # surface stack trace before the BAT pause
        import traceback
        traceback.print_exc()
        print(f"\n[FATAL] {exc}", file=sys.stderr)
        time.sleep(0.2)
        sys.exit(1)
