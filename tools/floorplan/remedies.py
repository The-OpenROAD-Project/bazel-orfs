"""Remedies for a plan's failed findings, each as a what-if: the edit to
the model (the constraints, the parent's crossings or a block's facts)
that the remedy is, and its effect, the plan run again on the edited
inputs. Nothing here is applied: the verdict lists them, ranked, so a
person or an agent picks one with its consequence in hand.

  reshape       a macro's outline at the aspect its failing side needs
  resize_slot   a macro's slot grown to what its rule or its pins need
  resize_die    the die a quarter larger each way
  narrow_bus    the widest contributing bus cut to what the side holds
  change_side   a forced side given up, the planner sides the buses
  move_memory   a walling hard object moved out of the macro to the glue
  move_slot     the constraints' places for the macros given up
  promote_layer starved layers given their full tracks
  register_bus  a register at the chain's source end (two chains)
  move_module   needs a finer keep and a resynthesis: named, not run
  split_side    one partner over two sides: named, not run

Stdlib only.
"""

import copy
import math

TRANSPOSABLE = ("side_blocked", "no_internal_arrangement")


def _macro(c, m):
    return c.setdefault("macros", {}).setdefault(m, {})


def _shape(model, st, m):
    r = st["rects"][m] if st.get("rects") and m in st["rects"] else None
    if r is not None:
        return r[2], r[3]
    rule = model.block(m)["area"]["die_rule"]
    return rule["w_um"], rule["h_um"]


def _scale_bus(inputs, model, m, bus, to_bits):
    """A macro's bus cut to `to_bits` in its block's facts and every
    crossing it takes part in."""
    block = model.macros[m]["block"]
    for b in inputs["blocks"]:
        if b["block"] == block:
            for p in b["ports"]:
                if p["name"] == bus:
                    p["bits"] = to_bits
    for x in (inputs.get("parent") or {}).get("crossings", []):
        for end in ("a", "b"):
            if (
                model.macro_of(x[end], x.get(end + "_inst")) == m
                and x[end + "_bus"] == bus
            ):
                frac = to_bits / max(
                    1, x[end + "_bits"] if end + "_bits" in x else x["bits"]
                )
                x[end + "_bits"] = to_bits
                other = "b" if end == "a" else "a"
                x[other + "_bits"] = max(
                    1, int(round(x.get(other + "_bits", x["bits"]) * frac))
                )
                x["bits"] = max(x["a_bits"], x["b_bits"])


def candidates(f, model, st):
    """(kind, details, edit) for a finding; edit(inputs) changes a deep copy."""
    out = []
    kind = f.get("kind", f["rung"])
    m = f.get("macro")
    c = model.c
    if kind == "pins_per_um":
        w, h = _shape(model, st, m)
        need = (
            f["demand"]["bits"] * f["limit"]["track_spacing"] / model.tracks(f["side"])
        )
        side_len = w if f["side"] in "NS" else h
        area = w * h
        if f["side"] in "NS":
            nw, nh = max(w, need), area / max(w, need)
        else:
            nh, nw = max(h, need), area / max(h, need)
        out.append(
            (
                "reshape",
                {"macro": m, "to": [round(nw, 3), round(nh, 3)]},
                lambda i: _macro(i["constraints"], m).update(slot=[nw, nh]),
            )
        )
        k = need / side_len if side_len else 1.0
        out.append(
            (
                "resize_slot",
                {"macro": m, "to": [round(w * k, 3), round(h * k, 3)]},
                lambda i: _macro(i["constraints"], m).update(slot=[w * k, h * k]),
            )
        )
        if f["contributors"]:
            top = f["contributors"][0]
            to = max(1, top["bits"] - f["excess"]["bits"])
            out.append(
                (
                    "narrow_bus",
                    {"macro": m, "bus": top["bus"], "to_bits": to},
                    lambda i: _scale_bus(i, model, m, top["bus"], to),
                )
            )
        out.append(("split_side", {"macro": m, "side": f["side"]}, None))
        out.append(
            (
                "move_module",
                {"macro": m, "note": "needs a keep below the block and a resynthesis"},
                None,
            )
        )
    elif kind == "area":
        if m is None:
            die = f.get("die")
            if die:
                out.append(
                    (
                        "resize_die",
                        {"to": [die["w"] * 1.25, die["h"] * 1.25]},
                        lambda i: i["constraints"].update(
                            die=[die["w"] * 1.25, die["h"] * 1.25]
                        ),
                    )
                )
        else:
            r = f["need"]
            # one percent over the rule, so the edited slot is not a rounding short
            k = math.sqrt(1.01 * r["um2"] / f["slot"]["um2"])
            to = [f["slot"]["w"] * k, f["slot"]["h"] * k]
            out.append(
                (
                    "resize_slot",
                    {"macro": m, "to": [round(v, 3) for v in to]},
                    lambda i: _macro(i["constraints"], m).update(slot=to),
                )
            )
    elif kind == "aspect":
        out.append(
            (
                "reshape",
                {"macro": m, "aspect_range": model.cal("aspect", "range")},
                lambda i: _macro(i["constraints"], m).pop("aspect_range", None),
            )
        )
    elif kind in TRANSPOSABLE:
        w, h = _shape(model, st, m)
        mc = model.macro_c(m)
        if kind == "side_blocked" and mc.get("sides"):
            side = f["side"]
            out.append(
                (
                    "change_side",
                    {"macro": m, "from": side},
                    lambda i: _macro(i["constraints"], m).update(
                        sides={p: s for p, s in mc["sides"].items() if s != side}
                    ),
                )
            )
        out.append(
            (
                "reshape",
                {"macro": m, "to": [round(h, 3), round(w, 3)]},
                lambda i: _macro(i["constraints"], m).update(slot=[h, w]),
            )
        )
        if kind == "no_internal_arrangement":
            out.append(
                (
                    "resize_slot",
                    {"macro": m, "to": [round(w * 1.25, 3), round(h * 1.25, 3)]},
                    lambda i: _macro(i["constraints"], m).update(
                        slot=[w * 1.25, h * 1.25]
                    ),
                )
            )
        walls = [w_["inst"] for w_ in f.get("walls", [])] or f.get("objects", [])
        if walls:
            inst = walls[0]
            out.append(
                (
                    "move_memory",
                    {"inst": inst, "from": m, "to": "GLUE"},
                    lambda i: _move_memory(i, model, m, inst),
                )
            )
    elif kind in ("no_channel", "over_capacity"):
        names = [
            x
            for x in f.get("channel", "%s|%s" % (m, f.get("partner"))).split("|")
            if x in model.macros
        ]
        placed = [x for x in names if "place" in model.macro_c(x)]
        if placed:
            out.append(
                (
                    "move_slot",
                    {"macros": placed},
                    lambda i: [
                        _macro(i["constraints"], x).pop("place", None) for x in placed
                    ],
                )
            )
        every = [x for x in model.macros if "place" in model.macro_c(x)]
        if every and c.get("die"):
            out.append(
                (
                    "move_slot",
                    {"macros": every, "slots": "planned", "die": "searched"},
                    lambda i: _replan(i, every),
                )
            )
        if c.get("die"):
            die = c["die"]
            out.append(
                (
                    "resize_die",
                    {"to": [die[0] * 1.25, die[1] * 1.25]},
                    lambda i: i["constraints"].update(
                        die=[die[0] * 1.25, die[1] * 1.25]
                    ),
                )
            )
        if any(v.get("share", 1.0) < 1.0 for v in c.get("layers", {}).values()):
            out.append(
                (
                    "promote_layer",
                    {"layers": sorted(c["layers"])},
                    lambda i: i["constraints"].pop("layers", None),
                )
            )
    elif kind in ("path_budget", "layer_capacity"):
        src = f.get("source") or {}
        if src:
            out.append(
                (
                    "register_bus",
                    {"macro": src["macro"], "bus": src["bus"], "at": "source"},
                    lambda i: _register(i, model, src["macro"], src["bus"]),
                )
            )
        ends = [
            x
            for x in (src.get("macro"), m)
            if x in model.macros and "place" in model.macro_c(x)
        ]
        if ends:
            out.append(
                (
                    "move_slot",
                    {"macros": ends},
                    lambda i: [
                        _macro(i["constraints"], x).pop("place", None) for x in ends
                    ],
                )
            )
        if any(v.get("share", 1.0) < 1.0 for v in c.get("layers", {}).values()):
            out.append(
                (
                    "promote_layer",
                    {"layers": sorted(c["layers"])},
                    lambda i: i["constraints"].pop("layers", None),
                )
            )
    return out


def _replan(inputs, macros):
    """The constraints' slots, places and die given up: the planner shapes
    and places the macros."""
    c = inputs["constraints"]
    c.pop("die", None)
    for x in macros:
        _macro(c, x).pop("place", None)
        _macro(c, x).pop("slot", None)


def _move_memory(inputs, model, m, inst):
    block = model.macros[m]["block"]
    for b in inputs["blocks"]:
        if b["block"] != block:
            continue
        objs = [o for o in b["hard"] if o["inst"] == inst]
        if not objs:
            return
        o = objs[0]
        b["hard"] = [x for x in b["hard"] if x["inst"] != inst]
        a = o["w"] * o["h"]
        b["area"]["hard_um2"] = round(b["area"]["hard_um2"] - a, 3)
        rule = b["area"]["die_rule"]
        if rule and rule.get("rule") == "CORE_UTILIZATION":
            k = math.sqrt(
                max(1e-6, rule["w_um"] * rule["h_um"] - a / rule["util"])
                / (rule["w_um"] * rule["h_um"])
            )
            rule["w_um"] = round(rule["w_um"] * k, 3)
            rule["h_um"] = round(rule["h_um"] * k, 3)
        c = inputs["constraints"]
        c["glue_um2"] = (
            c.get(
                "glue_um2",
                (inputs.get("parent") or {}).get("glue", {}).get("std_um2", 0.0),
            )
            + a
        )


def _register(inputs, model, m, bus):
    """A register in the parent at a macro's output bus: every crossing
    from it goes through the register."""
    for x in (inputs.get("parent") or {}).get("crossings", []):
        if model.macro_of(x["a"], x.get("a_inst")) == m and x["a_bus"] == bus:
            x["via"] = "reg"
            x["glue_ps"] = 0.0


def summary(v):
    first = next((f for f in v["findings"] if f["status"] == "fail"), None)
    out = {"verdict": v["verdict"], "stopped_at": v["stopped_at"]}
    if first:
        out["first"] = {
            k: first.get(k)
            for k in ("rung", "kind", "block", "side", "bus", "channel")
            if first.get(k)
        }
    return out


def compute(run, inputs, model, st, findings, limit=8):
    """Every remedy of the failed findings (the first stop's, or all with
    --all), each with its effect: `run(inputs)` is the plan on edited
    inputs, without remedies. Ranked feasible first, then by the rung
    the edited plan reaches."""
    out = []
    seen = set()
    for f in findings:
        if f["status"] != "fail":
            continue
        for kind, details, edit in candidates(f, model, st):
            key = (kind, repr(sorted(details.items())))
            if key in seen:
                continue
            seen.add(key)
            r = dict(
                {
                    "kind": kind,
                    "for": {
                        k: f.get(k)
                        for k in ("rung", "kind", "block", "side", "bus")
                        if f.get(k)
                    },
                },
                **details
            )
            if edit is None:
                r["effect"] = None
            elif len([x for x in out if x.get("effect")]) >= limit:
                r["effect"] = "not run: over the what-if limit"
            else:
                i = copy.deepcopy(inputs)
                edit(i)
                r["effect"] = summary(run(i))
            out.append(r)
    from plan import RUNGS

    def rank(r):
        e = r.get("effect")
        if not isinstance(e, dict):
            return (2, 0)
        if e["verdict"] == "feasible":
            return (0, 0)
        return (1, -RUNGS.index(e["stopped_at"]) if e["stopped_at"] in RUNGS else 0)

    return sorted(out, key=rank)
