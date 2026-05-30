"""ALife entry point.

Modes:
  python main.py                 # default → --ui (browser observatory)
  python main.py --ui            # FastAPI server + Canvas2D frontend
  python main.py --gui           # legacy pygame window (debug fallback)
  python main.py --headless      # no UI, ticks forever (Ctrl+C to stop)
  python main.py --benchmark N   # run N ticks headless, print perf summary
  python main.py --profile       # one-shot profile dump after 600 ticks
  python main.py --safe-mode     # smaller pop, observability minimized
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _apply_safe_mode() -> None:
    """Shrink population and silence heavy aggregations. Used by `--safe-mode`
    and as a panic fallback when watchdog detects pathological slow ticks."""
    import config as cfg
    cfg.INITIAL_CREATURES = 60
    cfg.MAX_CREATURES = 300
    cfg.INITIAL_FOOD = 250
    cfg.MAX_FOOD = 700
    cfg.STATISTICS_INTERVAL = 30
    cfg.SPECIES_RESYNC_INTERVAL = 500


def _run_gui() -> int:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame

    import config
    from core.simulation import Simulation
    from data import save_load
    from rendering.renderer import Renderer, _MAX_VIEWPORT_PX

    pygame.init()
    pygame.display.set_caption(config.WINDOW_TITLE)
    w_world = min(_MAX_VIEWPORT_PX, config.WORLD_WIDTH * config.TILE_SIZE)
    h_world = min(_MAX_VIEWPORT_PX, config.WORLD_HEIGHT * config.TILE_SIZE)
    surface = pygame.display.set_mode((w_world + config.UI_PANEL_WIDTH, h_world))
    clock = pygame.time.Clock()

    simulation = Simulation()
    renderer = Renderer(surface)

    running = True
    while running:
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

        simulation.update(max_steps=config.MAX_STEPS_PER_FRAME)
        renderer.draw(simulation)
        pygame.display.flip()
        clock.tick(config.FPS)

    pygame.quit()
    return 0


def _run_headless(max_ticks: int = 0, profile: bool = False) -> int:
    """Pure simulation. Returns when `max_ticks` reached (0 = forever, until
    Ctrl+C). Used by --headless, --benchmark and --profile."""
    from core.simulation import Simulation

    sim = Simulation()
    t0 = time.perf_counter()
    last_report = t0
    try:
        while True:
            sim._tick()
            if max_ticks and sim.world.tick >= max_ticks:
                break
            now = time.perf_counter()
            if now - last_report >= 5.0:
                tps = sim.world.tick / max(1e-6, (now - t0))
                hot, hot_ms = sim.profiler.slowest_section()
                print(
                    f"tick={sim.world.tick} pop={sim.world.population()} "
                    f"food={sim.world.food_count()} clans={len(sim.world.clans)} "
                    f"tps={tps:.1f} hot={hot}:{hot_ms:.2f}ms",
                    flush=True,
                )
                last_report = now
    except KeyboardInterrupt:
        print("\n[headless] interrupted", flush=True)

    elapsed = time.perf_counter() - t0
    tps = sim.world.tick / max(1e-6, elapsed)
    print(
        f"\n[headless] done — ticks={sim.world.tick} elapsed={elapsed:.2f}s "
        f"tps={tps:.1f}",
        flush=True,
    )
    if profile:
        print("\n[profile] section averages (ms):")
        for name, avg in sorted(sim.profiler.snapshot().items(),
                                key=lambda kv: -kv[1]):
            print(f"  {name:<18} {avg:7.3f}")
    return 0


def _run_observatory() -> int:
    """Start FastAPI + WebSocket server, auto-open browser, run sim in
    a background thread. Imported lazily so headless/gui don't need
    fastapi/uvicorn installed."""
    try:
        from observatory.server import run_server
    except ImportError as exc:
        print(f"[error] observatory mode requires fastapi+uvicorn: {exc}",
              file=sys.stderr)
        print("  install with: pip install fastapi uvicorn", file=sys.stderr)
        return 2
    return run_server()


def _run_experiment(name: str, ticks: int, seed: int, out: str) -> int:
    from core.experiments import SCENARIOS, run_experiment
    if name not in SCENARIOS:
        print(f"[error] unknown experiment '{name}'", file=sys.stderr)
        print(f"  choose from: {', '.join(SCENARIOS)}", file=sys.stderr)
        return 2
    print(f"[experiment] {name} ticks={ticks} seed={seed}", flush=True)
    t0 = time.perf_counter()
    result = run_experiment(name, ticks=ticks, seed=seed, out_path=out)
    print(f"[experiment] done in {time.perf_counter() - t0:.2f}s")
    print(f"  tps={result['tps']} final_pop={result.get('final_population')}")
    if out:
        print(f"  -> {out}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="alife", description="ALife simulation")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--ui", action="store_true",
                       help="run browser observatory (default)")
    group.add_argument("--gui", action="store_true",
                       help="run legacy pygame window (debug fallback)")
    group.add_argument("--headless", action="store_true",
                       help="run simulation forever without UI")
    group.add_argument("--benchmark", type=int, metavar="TICKS",
                       help="run N ticks headless and print TPS summary")
    group.add_argument("--experiment", metavar="NAME",
                       help="run a controlled scenario (survival_arena, "
                            "genetic_drift, benchmark)")
    parser.add_argument("--ticks", type=int, default=2000,
                        help="ticks for --experiment (default 2000)")
    parser.add_argument("--seed", type=int, default=0,
                        help="rng seed for --experiment (default 0)")
    parser.add_argument("--out", default=None,
                        help="JSON output file for --experiment results")
    parser.add_argument("--profile", action="store_true",
                        help="emit a profiler dump on exit")
    parser.add_argument("--safe-mode", action="store_true",
                        help="shrink pop + silence heavy aggregations")
    args = parser.parse_args(argv)

    if args.safe_mode:
        _apply_safe_mode()

    if args.gui:
        return _run_gui()
    if args.headless:
        return _run_headless(0, profile=args.profile)
    if args.benchmark is not None:
        return _run_headless(args.benchmark, profile=True)
    if args.experiment is not None:
        return _run_experiment(args.experiment, args.ticks, args.seed, args.out)
    # Default → observatory.
    return _run_observatory()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"\n[FATAL] {exc}", file=sys.stderr)
        time.sleep(0.2)
        sys.exit(1)
