#!/usr/bin/env python3
"""Rungs 0 and 1 of the planner's ladder: what a block's own size and
netlist say about its routing before any layout.

Rung 0, from the synthesis statistics in block.json (seconds):

  grt_capacity    the block's instances at global route, its synthesis
                  instances times the design's measured ratio, against
                  the most a worker of its class routes (calibrated from
                  the peak memory per instance of the design's grt runs)
  wire_demand     the block's total wire, Donath's a-priori average
                  length at Rent exponent p in gate pitches, times its
                  two-pin connections (pins less nets), against the
                  tracks its outline holds: every routable layer's
                  tracks per um at its share, over the outline, less
                  the hard objects' obstructed layers
  rent_terminals  the block's signal pins against Rent's rule for its
                  size, k G^p

Rung 1, from the block's netlist (netlist.json, netlist.py; under a
minute):

  rent_wire       wire_demand at the p the block's own recursive
                  bisection fits
  fanout          the nets of most sinks (after synthesis merged equal
                  registers): a repeater chain's delay grows with its
                  sinks, `ps_per_sink`, against the period
  escape          per side: the wires its pins' cones fan out into the
                  block (each pin's cone breadth, the most cells at one
                  logic level before the first register) against the
                  tracks crossing the side, the layers running into the
                  block
  via_stack       per side and pin layer: the pins on the layer plus the
                  via stacks of the pins above it (a pin on layer L
                  reaches the cells through every layer below it near the
                  side), each costing `via_cost` tracks, against the
                  layer's tracks along the side; buses take their layer
                  by distance: the lowest pin layer for a facing partner
                  within that layer's repeater spacing, the highest for a
                  longer or a lateral one

Beside them, each block's logic depth (logic_bound): the deepest
register-to-register path of its synthesis netlist, so a period its
logic sets is told from one its wires set, and is never put down to the
floorplan.

With the netlist, feed-through bits (an input reaching an output alone,
through buffers at most) are wires across the block, not its logic:
they leave Rent's terminals and the a-priori wire, and each adds one
crossing of the outline.

Each block's minimum outline (min_outline) is the smallest w x h every
calibrated rung passes at: the area its wire limit needs, and per side
the length its pins and escape need.

Each rung measures; it fails only against a limit the design's
calibration supplies (plan.py's CALIBRATION_KEYS). The coefficients a
calibration fits (calibrate.py) are `wirelength_factor` (measured over
Donath's wire), `p` and `k`, `via_cost`.

Stdlib only.
"""

import math

# Rent's exponent and coefficient where the design's calibration names
# none: Landman and Russo's random logic. They shape what is reported;
# no verdict rests on them without a calibrated limit.
RENT_DEFAULT = {"p": 0.6, "k": 2.5}


def donath_length(p, n):
    """Donath's average two-pin connection length on a square grid of n
    gates under Rent exponent p, in gate pitches."""
    n = max(float(n), 4.0)
    if abs(p - 0.5) < 1e-6:
        p = 0.5 + 1e-6
    a = 7.0 * (n ** (p - 0.5) - 1.0) / (4.0 ** (p - 0.5) - 1.0)
    b = (1.0 - n ** (p - 1.5)) / (1.0 - 4.0 ** (p - 1.5))
    c = (1.0 - 4.0 ** (p - 1.0)) / (1.0 - n ** (p - 1.0))
    return 2.0 / 9.0 * (a - b) * c


def outline_um(block, slot=None):
    """The block's routing area: its slot when the plan gives one, else
    the core its flow's rule draws."""
    if slot:
        return slot[0], slot[1]
    r = block["area"]["die_rule"]
    if r is None:
        return None
    return r.get("core_w_um", r["w_um"]), r.get("core_h_um", r["h_um"])


def wire_supply_um(block, w, h, layer_tracks):
    """Track length the outline holds, um: every routable layer's tracks
    per um over the outline, less what the hard objects obstruct."""
    area = w * h
    total = 0.0
    for n, t in layer_tracks.items():
        blocked = sum(
            o["w"] * o["h"] for o in block.get("hard", []) if n in o.get("obs", [])
        )
        total += t * max(0.0, area - blocked)
    return total


def feedthrough(netlist):
    return (netlist or {}).get("feedthrough") or {
        "bits": 0,
        "cells": 0,
        "connections": 0,
    }


def grt_capacity(block, per_inst, max_insts):
    """Rung 0: the instances global route will see against a worker's."""
    st = block.get("netlist")
    if not st:
        return None
    out = {"synth_insts": st["insts"]}
    if per_inst is not None:
        out["grt_insts"] = int(round(st["insts"] * per_inst))
        if max_insts:
            out["max_insts"] = max_insts
            out["ratio"] = round(out["grt_insts"] / max_insts, 4)
    return out


def wire_demand(block, layer_tracks, p, factor=1.0, slot=None, netlist=None):
    """Rung 0 and rent_wire: the block's a-priori wire against its
    supply, its feed-through bits as straight crossings. None when the
    block carries no netlist statistics."""
    st = block.get("netlist")
    wh = outline_um(block, slot)
    if not st or wh is None or st["insts"] < 2:
        return None
    w, h = wh
    ft = feedthrough(netlist)
    insts = max(st["insts"] - ft["cells"], 2)
    std_area = max(w * h - block["area"]["hard_um2"], 1e-9)
    pitch = math.sqrt(std_area / insts)
    connections = max(st["pins"] - st["nets"] - ft["connections"], 0)
    length = donath_length(p, insts)
    demand = factor * length * pitch * connections + ft["bits"] * (w + h) / 2
    supply = wire_supply_um(block, w, h, layer_tracks)
    return {
        "p": round(p, 4),
        "insts": insts,
        "connections": connections,
        "feedthrough_bits": ft["bits"],
        "length_pitches": round(length, 3),
        "pitch_um": round(pitch, 4),
        "demand_um": round(demand, 1),
        "supply_um": round(supply, 1),
        "ratio": round(demand / supply, 4) if supply > 0 else math.inf,
        "outline_um": [round(w, 3), round(h, 3)],
    }


def logic_bound(block):
    """The block's deepest register-to-register path in its synthesis
    netlist against its clock: a period its logic sets before any wire,
    which no floorplan moves."""
    lg = block.get("logic")
    if not lg:
        return None
    period = (block.get("clock") or {}).get("period_ps")
    out = dict(lg)
    if period:
        out["period_ps"] = period
        out["over_period"] = round(lg["ps"] / period, 4)
    return out


def signal_pins(block):
    return sum(p["bits"] for p in block["ports"])


def rent_terminals(block, p, k, netlist=None):
    """Rung 0: the block's signal pins over Rent's prediction for its
    size; with its netlist, the feed-through bits' pins left out."""
    st = block.get("netlist")
    if not st or st["insts"] < 2:
        return None
    ft = feedthrough(netlist)
    t = signal_pins(block) - 2 * ft["bits"]
    insts = max(st["insts"] - ft["cells"], 2)
    pred = k * insts**p
    return {
        "pins": t,
        "feedthrough_bits": ft["bits"],
        "insts": insts,
        "p": round(p, 4),
        "k": round(k, 4),
        "predicted": round(pred, 1),
        "ratio": round(t / pred, 4) if pred > 0 else math.inf,
    }


def perpendicular(side):
    """The direction of the wires that cross a side into the block."""
    return "V" if side in "NS" else "H"


def escape(side, side_um, buses, netlist, pdk, layer_tracks, usable=1.0):
    """Rung 1, one side: the wires the side's pins fan into the block, each
    pin its cone's breadth (netlist.json per bus; a bus it does not know
    counts one per pin), against the tracks crossing the side.

    buses: [(bus, bits)]"""
    known = (netlist or {}).get("buses", {})
    demand = 0.0
    rows = []
    for bus, bits in buses:
        b = known.get(bus, {}).get("breadth_mean", 1.0)
        demand += bits * b
        rows.append({"bus": bus, "bits": bits, "breadth": round(b, 3)})
    d = perpendicular(side)
    tracks = sum(t for n, t in layer_tracks.items() if pdk["layers"][n]["dir"] == d)
    supply = side_um * tracks * usable
    rows.sort(key=lambda r: (-r["bits"] * r["breadth"], r["bus"]))
    return {
        "demand": round(demand, 1),
        "supply": round(supply, 1),
        "ratio": round(demand / supply, 4) if supply > 0 else math.inf,
        "buses": rows,
    }


def assign_layers(buses, io, pdk):
    """Each bus's pin layer by distance: the lowest of the side's pin
    layers (io, lowest first) for a facing partner within that layer's
    repeater spacing, the highest for a longer or a lateral one.

    buses: [(bus, bits, distance_um, facing)]; returns {layer: bits} and
    the per-bus choice."""
    per = {n: 0 for n in io}
    rows = []
    if not io:
        return per, rows
    lo, hi = io[0], io[-1]
    reach = pdk["layers"][lo].get("spacing_um", math.inf)
    for bus, bits, dist, facing in buses:
        n = lo if facing and dist <= reach else hi
        per[n] += bits
        rows.append({"bus": bus, "bits": bits, "um": round(dist, 1), "layer": n})
    return per, rows


def via_stack(side_um, per_layer, pdk, via_cost):
    """Rung 1, one side: per routable layer at or below the side's highest
    pin layer, the pins on it plus `via_cost` tracks for every pin above
    it, against its tracks along the side; the track spacing (tracks per
    pin) the side then has on that layer. via_cost None reports the pins
    and the stacks alone."""
    order = pdk["order"]
    used = [n for n, b in per_layer.items() if b]
    if not used:
        return {}
    top = max(order.index(n) for n in used)
    out = {}
    for n in order[: top + 1]:
        L = pdk["layers"].get(n, {})
        if not L.get("routable"):
            continue
        i = order.index(n)
        pins = per_layer.get(n, 0)
        above = sum(b for m, b in per_layer.items() if order.index(m) > i)
        row = {"pins": pins, "stacks": above}
        if via_cost is not None:
            need = pins + via_cost * above
            row["demand"] = round(need, 1)
            row["track_spacing"] = (
                round(side_um * L["tracks_per_um"] / need, 3) if need else math.inf
            )
        out[n] = row
    return out


def fanout(netlist, ps_per_sink, budget_ps):
    """Rung 1: the nets whose repeater chain, `ps_per_sink` per sink,
    would take more than `budget_ps`; every top net when uncalibrated."""
    rows = []
    for r in (netlist or {}).get("fanout", []):
        row = dict(r)
        if ps_per_sink is not None:
            row["chain_ps"] = round(r["sinks"] * ps_per_sink, 1)
            if budget_ps is not None and row["chain_ps"] <= budget_ps:
                continue
        rows.append(row)
    return rows


def min_outline(w0, h0, area_need, sides):
    """The smallest outline that passes: at least `area_need` um2, each
    side at least its need (sides {N|S|E|W: um}), at the present aspect
    where the sides leave it free."""
    w_need = max([sides.get(s, 0.0) for s in "NS"] + [0.0])
    h_need = max([sides.get(s, 0.0) for s in "EW"] + [0.0])
    aspect = h0 / w0 if w0 else 1.0
    w = max(w_need, math.sqrt(area_need / aspect) if area_need else 0.0)
    h = max(h_need, area_need / w if w and area_need else 0.0)
    if w * h < area_need:
        w = area_need / h
    return [round(w, 3), round(h, 3)]
