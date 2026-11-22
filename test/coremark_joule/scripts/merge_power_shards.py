#!/usr/bin/env python3
"""Sum a hierarchical design's power shards into one report_power JSON.

    merge_power_shards.py --vectorless OUT --vector-driven OUT --report OUT
                          SHARD.json...

Each shard is one unit's report_power on its own ODB (flow/
power_shard_grt.tcl): the parent, a hardened block, a register file in
a block. A unit's children that are shards of their own appear in its
report as instances of their abstracts, so each shard also carries
those instances' power, and the sum takes it out again -- but only
their internal and leakage power. A child instance's switching power
is the power of the nets it drives in the unit: the unit's own wire and
loads, which the child's shard cannot see, because there they are a
port's. Subtracting the whole instance would drop those nets.

A child is an abstract, and report_power puts an abstract in its Macro
group (interface_timing in its liberty), so that is the group the
subtraction comes out of. A Macro group that would go negative means a
child was not in it, and the merge stops: the sum would be wrong.

The written JSONs have stage_power()'s shape, report_power's groups
each with internal, switching, leakage and total, so coremark_per_joule
reads either. The report carries, per shard, its own totals (children
taken out) and its SAIF annotation rate.

The merge fails, naming each shard, when a shard's SAIF-driven report
equals its vectorless one, or the SAIF annotated less than
--min-annotation of its pins: the SAIF did not bind at that shard's
scope, and OpenSTA said so only by falling back to its default
activity. Equal reports alone are not enough: a wrong scope still binds
wherever a generated cell name there (`_360_`) is also one here.
"""

import argparse
import json
import sys

GROUPS = ["Sequential", "Combinational", "Clock", "Macro", "Pad", "Total"]
KINDS = ["internal", "switching", "leakage"]
ARMS = ["vectorless", "vector_driven"]
# what a child's abstract keeps: the nets it drives in the unit
CHILD_TAKEN = ["internal", "leakage"]
# report_power prints six digits; below this a negative is rounding
_SLACK = 1e-5
# how far a unit's module rows may sum over its own total before refused
_ROWS_OVER = 0.01


def _zero():
    return {k: 0.0 for k in KINDS + ["total"]}


def _with_total(row):
    row = dict(row)
    row["total"] = sum(row[k] for k in KINDS)
    return row


def own(shard, arm):
    """The shard's groups for one arm, its children's internal and
    leakage power taken out of Macro and Total."""
    unit = shard["unit"] or "the parent"
    design = shard[arm]["design"]
    groups = {g: {k: float(design[g][k]) for k in KINDS} for g in GROUPS}
    # report_power escapes a bus bit's brackets, the ODB's name does not
    found = {c["name"].replace("\\", ""): c for c in shard[arm]["children"]}
    for child in shard.get("child_names", shard["children"]):
        child = child.replace("\\", "")
        if child not in found:
            raise ValueError(
                "{}: no power for child {} in its {} report".format(unit, child, arm)
            )
        for k in CHILD_TAKEN:
            v = float(found[child][k])
            groups["Macro"][k] -= v
            groups["Total"][k] -= v
    for g in ("Macro", "Total"):
        for k in CHILD_TAKEN:
            if groups[g][k] < -_SLACK * max(1.0, abs(float(design[g][k]))):
                raise ValueError(
                    "{}: {} {} power is negative once its children are "
                    "taken out ({}); a child is not in report_power's "
                    "Macro group".format(unit, g, k, groups[g][k])
                )
            groups[g][k] = max(0.0, groups[g][k])
    return {g: _with_total(groups[g]) for g in GROUPS}


def rate(shard):
    pins = shard["annotation"]["pins"]
    return shard["annotation"]["saif_pins"] / float(pins) if pins else 0.0


def binding_errors(shard, min_annotation):
    """Why the SAIF did not bind at this shard's scope, if it did not."""
    unit = shard["unit"] or "the parent"
    errors = []
    if rate(shard) < min_annotation:
        errors.append(
            "{}: the SAIF annotated {} of {} pins at scope {}, under {:.0%}".format(
                unit,
                shard["annotation"]["saif_pins"],
                shard["annotation"]["pins"],
                shard["scope"],
                min_annotation,
            )
        )
    less = shard["vectorless"]["design"]["Total"]
    driven = shard["vector_driven"]["design"]["Total"]
    if all(float(less[k]) == float(driven[k]) for k in KINDS + ["total"]):
        errors.append(
            "{}: the SAIF-driven report equals the vectorless one at scope {}".format(
                unit, shard["scope"]
            )
        )
    return errors


def scope_errors(shards, partial=False):
    """A child's shard must read the SAIF where its parent unit's ODB has
    the child: the parent unit's scope, then the child's instance as the
    SAIF names it (child_scopes, from the parent unit's own ODB). A
    partial sum may take each unit from its own replay's SAIF, a scope
    outside its parent's: nothing to compare there."""
    by_unit = {s["unit"]: s for s in shards}
    errors = []
    for s in shards:
        unit = s["unit"]
        if not unit:
            continue
        up = max(
            (u for u in by_unit if u and unit.startswith(u + "/")),
            key=len,
            default="",
        )
        parent = by_unit.get(up)
        # a partial sum without the parent unit: nothing to check against
        if parent is None or "child_scopes" not in parent:
            continue
        if partial and not s["scope"].startswith(parent["scope"] + "/"):
            continue
        rel = unit[len(up) + 1 :] if up else unit
        if rel not in parent["children"]:
            errors.append(
                "{}: not among {}'s children".format(unit, up or "the parent")
            )
            continue
        expected = (
            parent["scope"]
            + "/"
            + parent["child_scopes"][parent["children"].index(rel)]
        )
        if s["scope"] != expected:
            errors.append(
                "{}: read the SAIF at {}, but {}'s ODB has it at {}".format(
                    unit, s["scope"], up or "the parent", expected
                )
            )
    return errors


def merge(shards, min_annotation=0.9, partial=False):
    """(vectorless, vector_driven, report) for a list of shard dicts."""
    units = [s["unit"] for s in shards]
    dup = sorted({u for u in units if units.count(u) > 1})
    if dup:
        raise ValueError("units reported twice: {}".format(", ".join(dup)))
    if "" not in units and not partial:
        raise ValueError("no parent shard (unit ''); --partial sums what there is")
    errors = scope_errors(shards, partial)
    if errors:
        raise ValueError("a shard's scope is wrong:\n  " + "\n  ".join(errors))
    for s in shards:
        errors += binding_errors(s, min_annotation)
    if errors:
        raise ValueError("the SAIF did not bind:\n  " + "\n  ".join(errors))

    sums = {arm: {g: _zero() for g in GROUPS} for arm in ARMS}
    report = {"shards": []}
    for s in sorted(shards, key=lambda s: s["unit"]):
        entry = {
            "unit": s["unit"],
            "design": s.get("design", ""),
            "scope": s["scope"],
            "children": s["children"],
            "annotation": {
                "saif_pins": s["annotation"]["saif_pins"],
                "pins": s["annotation"]["pins"],
                "rate": rate(s),
            },
        }
        for arm in ARMS:
            groups = own(s, arm)
            entry[arm] = groups["Total"]
            for g in GROUPS:
                for k in KINDS + ["total"]:
                    sums[arm][g][k] += groups[g][k]
        report["shards"].append(entry)
    report["total"] = {arm: sums[arm]["Total"] for arm in ARMS}
    return sums["vectorless"], sums["vector_driven"], report


def unit_rows(shards, units):
    """The per-module breakdown across the shards: every module instance
    of every unit, its path from the parent's root, SAIF-driven, and each
    unit's flat remainder (its own total less its depth-1 rows). Refused
    when a remainder goes negative: module rows counting more than the
    unit, a module counted twice."""
    rows = []
    for shard, mods in zip(shards, units):
        unit = shard["unit"]
        prefix = unit + "/" if unit else ""
        own_total = own(shard, "vector_driven")["Total"]
        top = {k: 0.0 for k in KINDS}
        for m in mods:
            rows.append(
                {
                    "path": prefix + m["path"],
                    "unit": unit,
                    "module": m["module"],
                    "depth": m["depth"],
                    **{k: m[k] for k in KINDS},
                    "total": sum(m[k] for k in KINDS),
                }
            )
            if m["depth"] == 1:
                for k in KINDS:
                    top[k] += m[k]
        rest = {k: own_total[k] - top[k] for k in KINDS}
        over = []
        for k in KINDS:
            if rest[k] >= -_SLACK * max(1.0, abs(own_total[k])) - 1e-12:
                continue
            # module rows over the unit by up to 1%: kept, the remainder
            # negative and said so (first pass: Frontend's leakage rows
            # 0.13% over its own, not traced); more is refused
            if -rest[k] <= _ROWS_OVER * abs(own_total[k]):
                over.append(k)
                continue
            raise ValueError(
                "{}: its module instances' {} power, {}, is over the unit's, {}".format(
                    unit or "the parent", k, top[k], own_total[k]
                )
            )
        rows.append(
            {
                "path": unit,
                "unit": unit,
                "module": "(the unit's own cells under no module instance)",
                "depth": 0,
                **rest,
                "total": sum(rest.values()),
                **(
                    {
                        "note": "module rows over the unit's own "
                        + ", ".join(over)
                        + " (under 1%)"
                    }
                    if over
                    else {}
                ),
            }
        )
    return sorted(rows, key=lambda r: r["path"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("shards", nargs="+")
    parser.add_argument("--vectorless", required=True)
    parser.add_argument("--vector-driven", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--units",
        action="append",
        default=[],
        help="a shard's per-module rows, in the shards' order",
    )
    parser.add_argument("--units-out")
    parser.add_argument(
        "--partial",
        action="store_true",
        help="sum the shards given, the parent's among them or not: a stand-in, "
        "not the design's power",
    )
    parser.add_argument(
        "--min-annotation",
        type=float,
        default=0.9,
        help="least fraction of a shard's pins the SAIF must annotate",
    )
    args = parser.parse_args(argv)
    shards = []
    for path in args.shards:
        with open(path) as f:
            shards.append(json.load(f))
    try:
        vectorless, vector_driven, report = merge(
            shards, args.min_annotation, args.partial
        )
        report["partial"] = args.partial
    except ValueError as e:
        sys.stderr.write("merge_power_shards: {}\n".format(e))
        return 1
    outputs = [
        (args.vectorless, vectorless),
        (args.vector_driven, vector_driven),
        (args.report, report),
    ]
    if args.units_out:
        units = []
        for path in args.units:
            with open(path) as f:
                units.append(json.load(f))
        try:
            outputs.append((args.units_out, unit_rows(shards, units)))
        except ValueError as e:
            sys.stderr.write("merge_power_shards: {}\n".format(e))
            return 1
    for path, data in outputs:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
