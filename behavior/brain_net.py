"""Brain network projection — a neural-graph view of how a creature decides.

This is NOT a second decision engine. It is a faithful, deterministic
projection of the *existing* scoring brain (behavior/decisions.py) onto a
three-layer graph so the cognition can be inspected and visualized:

    sensors (perception)  ->  cognition / drive genes  ->  actions

Edge base-weights mirror the coefficients the real scorer uses (e.g.
aggression weighs 1.3 toward ATTACK), and every edge is then scaled by the
creature's normalized gene value. So a smarter / more aggressive genome grows
denser, brighter connections — the graph literally is the decision function of
that genome. The same builder, fed population-averaged gene values, yields the
collective "mind" of the world.

All inputs are normalized gene values in [0,1] (genome.to_dict()), so the same
code serves a single creature or an aggregate dict.
"""

from __future__ import annotations

from typing import Dict, List

# Perception sensors (mirror behavior/perception.py fields).
SENSORS = [
    ("food",   "perception"),
    ("mate",   "perception"),
    ("ally",   "perception"),
    ("enemy",  "perception"),
    ("danger", "perception"),
    ("hunger", "perception"),
    ("home",   "perception"),
    ("crowd",  "perception"),
]

# Cognition + drive genes — the hidden layer. label == gene name (normalized).
HIDDEN = [
    ("intelligence",        "intellect"),
    ("memory_capacity",     "intellect"),
    ("learning_speed",      "intellect"),
    ("planning_ability",    "intellect"),
    ("pattern_recognition", "intellect"),
    ("risk_analysis",       "intellect"),
    ("curiosity",           "intellect"),
    ("strategic_thinking",  "intellect"),
    ("aggression",          "instinct"),
    ("fear",                "instinct"),
    ("reproduction_drive",  "instinct"),
    ("territoriality",      "instinct"),
    ("hunting_instinct",    "instinct"),
    ("self_preservation",   "instinct"),
    ("expansion_drive",     "instinct"),
    ("migration_drive",     "instinct"),
    ("social_bonding",      "social"),
    ("cooperation_instinct","social"),
    ("leadership",          "social"),
]

ACTIONS = [
    "eat", "flee", "attack", "reproduce", "claim",
    "clan", "migrate", "communicate", "defend", "rest",
]

# sensor -> hidden  (which perception engages which cognition/drive)
S2H = [
    ("food", "intelligence", 0.4), ("food", "curiosity", 0.3),
    ("hunger", "self_preservation", 0.6), ("hunger", "migration_drive", 0.5), ("hunger", "aggression", 0.3),
    ("mate", "reproduction_drive", 0.9), ("mate", "social_bonding", 0.3),
    ("enemy", "fear", 0.8), ("enemy", "aggression", 0.7), ("enemy", "risk_analysis", 0.6), ("enemy", "self_preservation", 0.5),
    ("danger", "fear", 0.9), ("danger", "risk_analysis", 0.7), ("danger", "self_preservation", 0.6),
    ("ally", "social_bonding", 0.8), ("ally", "cooperation_instinct", 0.7), ("ally", "leadership", 0.4),
    ("home", "territoriality", 0.9), ("home", "expansion_drive", 0.5),
    ("crowd", "pattern_recognition", 0.5), ("crowd", "strategic_thinking", 0.4), ("crowd", "social_bonding", 0.3),
]

# hidden -> hidden  (knowledge wiring up: cognition reinforces cognition)
H2H = [
    ("intelligence", "planning_ability", 0.5), ("intelligence", "strategic_thinking", 0.4),
    ("memory_capacity", "learning_speed", 0.5), ("learning_speed", "pattern_recognition", 0.4),
    ("pattern_recognition", "strategic_thinking", 0.4), ("risk_analysis", "planning_ability", 0.3),
]

# hidden -> action  (base weights mirror decisions.py scoring coefficients)
H2A = [
    ("intelligence", "eat", 0.4), ("pattern_recognition", "eat", 0.3),
    ("self_preservation", "rest", 0.5), ("self_preservation", "flee", 0.8),
    ("fear", "flee", 1.4), ("risk_analysis", "flee", 0.4),
    ("aggression", "attack", 1.3), ("hunting_instinct", "attack", 0.6), ("strategic_thinking", "attack", 0.3),
    ("reproduction_drive", "reproduce", 1.4),
    ("territoriality", "claim", 0.9), ("expansion_drive", "claim", 0.4), ("territoriality", "defend", 0.9),
    ("leadership", "clan", 1.0), ("social_bonding", "clan", 0.8), ("cooperation_instinct", "clan", 0.4),
    ("social_bonding", "communicate", 0.6),
    ("curiosity", "migrate", 0.4), ("migration_drive", "migrate", 0.9), ("planning_ability", "migrate", 0.3),
]


def build(genes: Dict[str, float]) -> Dict[str, object]:
    """Build the brain graph from a dict of normalized gene values [0,1]."""
    g = lambda name: float(max(0.0, min(1.0, genes.get(name, 0.0))))

    nodes: List[dict] = []
    idx: Dict[str, int] = {}

    def add(nid, label, layer, group, act):
        idx[nid] = len(nodes)
        nodes.append({"id": nid, "label": label, "layer": layer,
                      "group": group, "act": round(act, 3)})

    for name, grp in SENSORS:
        add("s:" + name, name, 0, grp, 0.7)
    for name, grp in HIDDEN:
        add("h:" + name, name, 1, grp, g(name))
    for name in ACTIONS:
        add("a:" + name, name, 2, "action", 0.0)

    edges: List[dict] = []
    act_drive: Dict[str, float] = {a: 0.0 for a in ACTIONS}

    def edge(s, t, w):
        if w <= 0.02:
            return
        edges.append({"s": idx[s], "t": idx[t], "w": round(w, 3)})

    for s, h, base in S2H:
        edge("s:" + s, "h:" + h, base * g(h))
    for a, b, base in H2H:
        edge("h:" + a, "h:" + b, base * g(a) * g(b))
    for h, a, base in H2A:
        w = base * g(h)
        edge("h:" + h, "a:" + a, w)
        act_drive[a] += w

    # Output node activation = summed incoming drive (normalized for display).
    mx = max(1e-6, max(act_drive.values()))
    for a, v in act_drive.items():
        nodes[idx["a:" + a]]["act"] = round(min(1.0, v / mx), 3)

    return {"nodes": nodes, "edges": edges}


def population_net(sim, sample: int = 240) -> Dict[str, object]:
    """Collective mind: build the graph from population-averaged gene values."""
    world = sim.world
    creatures = list(world.creatures.values())
    n = len(creatures)
    if n == 0:
        return {"nodes": [], "edges": [], "sample": 0, "population": 0}

    if n > sample:
        step = n / sample
        creatures = [creatures[int(i * step)] for i in range(sample)]

    names = [h[0] for h in HIDDEN]
    acc = {name: 0.0 for name in names}
    for c in creatures:
        gd = c.genome.to_dict()
        for name in names:
            acc[name] += float(gd.get(name, 0.0))
    k = max(1, len(creatures))
    avg = {name: acc[name] / k for name in names}

    net = build(avg)
    net["sample"] = len(creatures)
    net["population"] = n
    return net
