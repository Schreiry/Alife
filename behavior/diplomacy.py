"""Inter-clan diplomacy: border friction, relation drift, war/peace events.

Each Clan stores relations as ``{other_id: value in [-1, 1]}``. Two forces move
them on every ``DIPLOMACY_INTERVAL``:

  * **border friction** — clans whose territories touch erode each other's
    relation in proportion to the shared-border length, scaled by militancy
    (clan ideology) and global resource stress. This is what *starts*
    hostility. Previously relations only dropped on a cross-clan kill, but a
    kill needed an already-hostile relation to even perceive the enemy
    (perception flags a foreign clan as an enemy only when rel < -0.3) — a
    deadlock that left the world permanently at peace no matter how long it ran.
  * **coexistence drift** — relations not under active friction relax toward
    zero and pick up a small warmth bonus, so clans that stop bordering each
    other eventually make peace.

When the (more hostile of the two) relation crosses ``WAR_THRESHOLD`` a war is
declared once; it ends when the relation recovers past ``WAR_END_THRESHOLD``.
Crossing ``ALLIANCE_THRESHOLD`` forms an alliance. Each transition drops a
positioned map signal at the contact centroid so the world shows where it
happened.
"""

from __future__ import annotations

import numpy as np

import config


def step_diplomacy(world) -> None:
    clans = world.clans
    if not clans:
        return

    friction = _border_friction(world)        # {(lo, hi): (count, cx, cy)}
    stress = _global_stress(world)             # 0..1

    # 1. Coexistence drift on EVERY relation: decay toward zero plus a small
    #    warmth bonus. This restoring force is always present, so a relation has
    #    an equilibrium — friction below it settles into a tense-but-not-war
    #    neutral, friction above it escalates to war, and once contact ends the
    #    relation recovers (wars end, alliances can form). Crucially this is
    #    applied to bordering pairs too; otherwise mere adjacency guaranteed war.
    decay = config.DIPLOMACY_DECAY
    coexist = config.DIPLOMACY_COEXIST_BONUS
    for clan in clans.values():
        for other_id, rel in list(clan.relations.items()):
            if rel > 0.0:
                rel = max(0.0, rel - decay)
            elif rel < 0.0:
                rel = min(0.0, rel + decay)
            rel += coexist
            clan.relations[other_id] = 1.0 if rel > 1.0 else (-1.0 if rel < -1.0 else rel)

    # 2. Border friction subtracts on top for clans whose territories touch
    #    (and seeds an entry for pairs that have never interacted). Scaled by
    #    militancy (clan ideology) and global resource stress, so wars erupt
    #    from aggressive temperament and scarcity — not from adjacency alone.
    rate = config.BORDER_FRICTION_RATE
    sat = config.BORDER_FRICTION_SATURATION
    contact_pos: dict = {}
    for (lo, hi), (count, cx, cy) in friction.items():
        a = clans.get(lo)
        b = clans.get(hi)
        if a is None or b is None:
            continue
        contact = min(1.0, count / sat)
        militancy = 0.5 * (a.ideology + b.ideology)          # 0 .. 1 avg ideology
        # Steep militancy gate: peaceful neighbors barely erode (force stays
        # under the ~0.0013/step restoring pull, so they settle into a tense
        # neutral), while aggressive clans — or any clans under resource stress —
        # cross into war within their lifetime.
        force = rate * contact * (0.05 + 1.10 * militancy) * (0.4 + 1.2 * stress)
        _bump(a, hi, -force)
        _bump(b, lo, -force)
        contact_pos[(lo, hi)] = (cx, cy)

    # 3. War / alliance transitions, once per unordered pair.
    seen: set = set()
    for clan in clans.values():
        cid = clan.id
        for other_id in list(clan.relations.keys()):
            key = (cid, other_id) if cid < other_id else (other_id, cid)
            if key in seen:
                continue
            seen.add(key)
            a = clans.get(key[0])
            b = clans.get(key[1])
            if a is None or b is None:
                continue
            _check_transitions(world, a, b, contact_pos.get(key))


def _bump(clan, other_id: int, delta: float) -> None:
    rel = clan.relations.get(other_id, 0.0) + delta
    clan.relations[other_id] = 1.0 if rel > 1.0 else (-1.0 if rel < -1.0 else rel)


def _check_transitions(world, a, b, pos) -> None:
    """Announce war/peace/alliance crossings between two clans, once each."""
    rel = min(a.relations.get(b.id, 0.0), b.relations.get(a.id, 0.0))
    if pos is None:
        pos = (world.centroid_x, world.centroid_y)
    cx, cy = pos

    # --- war (hysteresis: declare at WAR_THRESHOLD, end at WAR_END_THRESHOLD) ---
    if rel <= config.WAR_THRESHOLD:
        if b.id not in a.at_war:
            a.at_war.add(b.id)
            b.at_war.add(a.id)
            a.allied.discard(b.id)
            b.allied.discard(a.id)
            world.push_signal("war_declared", cx, cy, {
                "a": a.id, "b": b.id, "a_name": a.name, "b_name": b.name,
                "rel": round(rel, 3),
            })
    elif rel >= config.WAR_END_THRESHOLD and b.id in a.at_war:
        a.at_war.discard(b.id)
        b.at_war.discard(a.id)
        world.push_signal("war_ended", cx, cy, {
            "a": a.id, "b": b.id, "a_name": a.name, "b_name": b.name,
        })

    # --- alliance ---
    if rel >= config.ALLIANCE_THRESHOLD:
        if b.id not in a.allied:
            a.allied.add(b.id)
            b.allied.add(a.id)
            world.push_signal("alliance_formed", cx, cy, {
                "a": a.id, "b": b.id, "a_name": a.name, "b_name": b.name,
            })
    elif rel < config.ALLIANCE_THRESHOLD * 0.5:
        a.allied.discard(b.id)
        b.allied.discard(a.id)


def _global_stress(world) -> float:
    """0..1 environmental hostility multiplier from food scarcity."""
    try:
        stress = float(world.ecology.mean_depletion())
    except Exception:
        stress = 0.0
    if getattr(world, "in_famine", False):
        stress = max(stress, 0.6)
    return 0.0 if stress < 0.0 else (1.0 if stress > 1.0 else stress)


def _border_friction(world) -> dict:
    """Shared-border length + centroid per clan pair, from the territory grid.

    Vectorized: scan the owner grid for orthogonally adjacent tiles with two
    different (non-empty) owners. Returns ``{(lo_id, hi_id): (tiles, cx, cy)}``
    in world-tile coordinates. Runs on DIPLOMACY_INTERVAL, so the full-grid
    sweep is cheap relative to the per-creature brain pass.
    """
    ow = world.territory.owner
    a_ids = []
    b_ids = []
    xs = []
    ys = []

    left = ow[:-1, :]
    right = ow[1:, :]
    mh = (left >= 0) & (right >= 0) & (left != right)
    if mh.any():
        xi, yi = np.nonzero(mh)
        a_ids.append(left[mh])
        b_ids.append(right[mh])
        xs.append(xi.astype(np.float64) + 0.5)
        ys.append(yi.astype(np.float64))

    top = ow[:, :-1]
    bot = ow[:, 1:]
    mv = (top >= 0) & (bot >= 0) & (top != bot)
    if mv.any():
        xi, yi = np.nonzero(mv)
        a_ids.append(top[mv])
        b_ids.append(bot[mv])
        xs.append(xi.astype(np.float64))
        ys.append(yi.astype(np.float64) + 0.5)

    if not a_ids:
        return {}

    ca = np.concatenate(a_ids)
    cb = np.concatenate(b_ids)
    X = np.concatenate(xs)
    Y = np.concatenate(ys)

    lo = np.minimum(ca, cb).astype(np.int64)
    hi = np.maximum(ca, cb).astype(np.int64)
    shift = np.int64(1) << 32
    key = lo * shift + hi
    uniq, inv = np.unique(key, return_inverse=True)
    inv = inv.ravel()
    counts = np.bincount(inv).astype(np.float64)
    sx = np.bincount(inv, weights=X)
    sy = np.bincount(inv, weights=Y)

    out: dict = {}
    mask = int(shift) - 1
    for i, u in enumerate(uniq.tolist()):
        lo_id = int(u >> 32)
        hi_id = int(u & mask)
        c = counts[i]
        out[(lo_id, hi_id)] = (int(c), sx[i] / c, sy[i] / c)
    return out


def relation_label(value: float) -> str:
    if value <= config.WAR_THRESHOLD:
        return "war"
    if value >= config.ALLIANCE_THRESHOLD:
        return "ally"
    return "neutral"
