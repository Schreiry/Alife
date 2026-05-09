"""Color helpers used by both rendering and world bookkeeping."""

from __future__ import annotations

from typing import Tuple

from genetics.genome import Genome


Color = Tuple[int, int, int]


def clamp_byte(v: float) -> int:
    if v < 0.0:
        return 0
    if v > 255.0:
        return 255
    return int(v)


def genome_to_color(genome: Genome) -> Color:
    r = genome.normalized("color_r")
    g = genome.normalized("color_g")
    b = genome.normalized("color_b")
    # Push colors toward visible saturation.
    r = 60 + 195 * r
    g = 60 + 195 * g
    b = 60 + 195 * b
    return (clamp_byte(r), clamp_byte(g), clamp_byte(b))


def mix_colors(a: Color, b: Color, t: float) -> Color:
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return (
        clamp_byte(a[0] * (1.0 - t) + b[0] * t),
        clamp_byte(a[1] * (1.0 - t) + b[1] * t),
        clamp_byte(a[2] * (1.0 - t) + b[2] * t),
    )


def darken(c: Color, amount: float = 0.4) -> Color:
    return (
        clamp_byte(c[0] * (1.0 - amount)),
        clamp_byte(c[1] * (1.0 - amount)),
        clamp_byte(c[2] * (1.0 - amount)),
    )


def with_alpha_overlay(base: Color, overlay: Color, alpha: float) -> Color:
    """Pre-blended overlay simulating per-tile territory tint."""
    return mix_colors(base, overlay, alpha)
