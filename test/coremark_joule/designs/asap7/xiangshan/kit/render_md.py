#!/usr/bin/env python3
"""Fill EXPORT.md's placeholders from the files the kit is made of.

EXPORT.md holds the prose; every number, list and table in it is a
`{{name}}` filled here from a build output or a file in the repo: the
kit's netlist facts (kit_facts.tcl), the floorplan plan, the KPI series,
the measured resources, the register-file specs, the arrays' A/B table,
MODULE.bazel and the build's stamp. A placeholder nothing fills, or a
fact nothing uses, stops the build: the document cannot go stale
quietly.

  render_md.py --template EXPORT.md --out EXPORT.filled.md --svg floorplan.svg
      --facts facts.json --plan plan.json --plan-bzl plan.bzl --kpi kpi.json
      --resources resources.json --ab ab.json --blocks blocks.json
      --module-bazel MODULE.bazel --sta sta.tcl --rtl-ports ports.json
      --pin pin.json [--status stable-status.txt]
      <spec.regfile>...
"""

import argparse
import ast
import json
import os
import re
import sys

STAGES = ["synth", "floorplan", "place", "cts", "grt"]


def num(x, digits=0):
    return "{:,.{d}f}".format(x, d=digits)


def table(header, rows, right=(), abbrev=None):
    """A Markdown table; columns named in `right` align right. `abbrev`
    maps a header much wider than its column's data to a short form,
    printed with a `*` and spelled out in a note under the table."""
    abbrev = abbrev or {}
    shown = ["%s\\*" % abbrev[h] if h in abbrev else h for h in header]
    out = ["| " + " | ".join(shown) + " |"]
    out.append("|" + "|".join("---:" if h in right else "---" for h in header) + "|")
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    if abbrev:
        notes = "; ".join(
            "%s: %s" % (abbrev[h], h.lower() if h[1:].islower() else h)
            for h in header
            if h in abbrev
        )
        out.append("")
        out.append("*\\* %s.*" % notes)
    return "\n".join(out)


def load_plan_bzl(path):
    """PLAN from plan.bzl: a Starlark dict literal, which Python reads."""
    text = open(path).read()
    m = re.search(r"^PLAN\s*=\s*", text, re.M)
    if not m:
        raise SystemExit("render_md: no PLAN in %s" % path)
    return ast.literal_eval(text[m.end() :].strip())


def parse_regfile(path):
    spec = {"read": 0, "write": 0}
    for line in open(path):
        words = line.split()
        if not words or words[0].startswith("#"):
            continue
        if words[0] in ("module", "words", "bits"):
            spec[words[0]] = words[1]
        elif words[0] in ("read", "read_banked"):
            spec["read"] += 1
        elif words[0] == "write":
            spec["write"] += 1
    for k in ("module", "words", "bits"):
        if k not in spec:
            raise SystemExit("render_md: %s has no %s" % (path, k))
    return spec


def where(paths, depth=3):
    """The instances' common hierarchy, at most `depth` levels."""
    parts = [p.split("/")[:-1] for p in paths]
    common = []
    for level in zip(*parts):
        if len(set(level)) != 1:
            break
        common.append(level[0])
    return "/".join(common[:depth]) or "(top)"


def opensta_pin(module_bazel):
    """The OpenSTA repository and commit OpenROAD's src/sta is fetched at."""
    m = re.search(
        r"https://github.com/([\w.-]+/OpenSTA)/archive/([0-9a-f]{40})\.tar\.gz",
        module_bazel,
    )
    if not m:
        raise SystemExit("render_md: no OpenSTA archive in MODULE.bazel")
    return m.group(1), m.group(2)


def status(path):
    values = {}
    if path:
        for line in open(path):
            k, _, v = line.rstrip("\n").partition(" ")
            values[k] = v
    return values


def floorplan_svg(plan_bzl, plan_json, width=640.0):
    """The plan's die, blocks, register-file netlists and regions to scale,
    with plain attributes (no CSS) and coordinates already in the
    picture's units, since the PDF writer does not scale a viewBox."""
    die = [float(v) for v in plan_bzl["parent"]["DIE_AREA"].split()]
    W, H = die[2], die[3]
    k = width / (W + 160)
    height = (H + 180) * k

    def at(x):
        return "%.1f" % ((x + 60) * k)

    def sz(x):
        return "%.1f" % (x * k)

    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %.0f %.0f" width="%.0f" height="%.0f">'
        % (width, height, width, height)
    ]

    def rect(x, y, w, h, style):
        out.append(
            '<rect x="%s" y="%s" width="%s" height="%s" %s/>'
            % (at(x), at(y), sz(w), sz(h), style)
        )

    def text(x, y, size, label, fill="#17202b", anchor="middle", rotate=False):
        rot = ' transform="rotate(-90 %s %s)"' % (at(x), at(y)) if rotate else ""
        out.append(
            '<text x="%s" y="%s" font-size="%s" text-anchor="%s" fill="%s"%s>%s</text>'
            % (at(x), at(y + size / 3), sz(size), anchor, fill, rot, label)
        )

    rect(0, 0, W, H, 'fill="none" stroke="#17202b" stroke-width="1.2"')
    for name, m in sorted(plan_bzl["macros"].items()):
        d = [float(v) for v in m["DIE_AREA"].split()]
        w, h = d[2], d[3]
        x, y = m["x_um"], H - m["y_um"] - h
        rect(x, y, w, h, 'fill="#dbe6f3" stroke="#1f5fa8" stroke-width="0.8"')
        size = 60 if w >= 500 else 40 if w >= 280 else 26
        text(x + w / 2, y + h / 2, size, name, rotate=w < 200)
    for n in plan_bzl["parent"].get("netlists", []):
        x, y = n["x_um"], H - n["y_um"] - n["h_um"]
        rect(
            x,
            y,
            n["w_um"],
            n["h_um"],
            'fill="#f3dccb" stroke="#a4511d" stroke-width="0.8"',
        )
        text(x + n["w_um"] / 2, y + n["h_um"] / 2, 36, n["module"])
    for r in plan_json["parent"].get("regions", []):
        x0, y0, x1, y1 = r["box_um"]
        rect(
            x0,
            H - y1,
            x1 - x0,
            y1 - y0,
            'fill="none" stroke="#8a5cc2" stroke-width="1" stroke-dasharray="4 2"',
        )
    text(0, H + 60, 44, "0", fill="#5a6675", anchor="start")
    text(W, H + 60, 44, "%s um" % num(W), fill="#5a6675", anchor="end")
    out.append("</svg>")
    return "\n".join(out) + "\n", W, H


def facts_values(a):
    facts = json.load(open(a.facts))
    plan = json.load(open(a.plan))
    plan_bzl = load_plan_bzl(a.plan_bzl)
    kpi = json.load(open(a.kpi))
    res = json.load(open(a.resources))
    ab = json.load(open(a.ab))
    blocks = json.load(open(a.blocks))
    regfiles = {s["module"]: s for s in (parse_regfile(p) for p in a.regfiles)}
    v = {}

    # the netlist
    v["cells"] = num(facts["cells"])
    v["flops"] = num(facts["flops"])
    v["clock_gates"] = num(facts["clock_gates"])
    v["ports"] = num(facts["ports"])
    v["std_area_mm2"] = num(facts["std_area_um2"] / 1e6, 2)
    c = facts["checks"]
    v["check_table"] = table(
        ["Check", "Count", "What it means"],
        [
            [
                "combinational loops",
                num(c["loops"]),
                "none, or the kit would not have been made",
            ],
            [
                "nets with two drivers",
                num(c["multidriven"]),
                "none, or the kit would not have been made",
            ],
            [
                "nets with loads and no driver",
                num(c["undriven"]),
                "inputs left open; zero when every input is driven",
            ],
            [
                "registers no clock reaches",
                num(c["no_clock"]),
                "OpenSTA's check_setup, no_clock",
            ],
            [
                "registers two clocks reach",
                num(c["multiple_clock"]),
                "OpenSTA's check_setup, multiple_clock",
            ],
        ],
        right=("Count",),
    )
    macros = facts["macros"]
    srams = {k: m for k, m in macros.items() if k not in regfiles}
    rfs = {k: m for k, m in macros.items() if k in regfiles}
    missing = sorted(set(regfiles) - set(rfs))
    if missing:
        raise SystemExit(
            "render_md: register files with a spec but no instance in the netlist: %s"
            % ", ".join(missing)
        )
    v["macro_instances"] = num(sum(len(m["instances"]) for m in macros.values()))
    v["sram_instances"] = num(sum(len(m["instances"]) for m in srams.values()))
    v["sram_shapes"] = num(len(srams))
    v["regfile_instances"] = num(sum(len(m["instances"]) for m in rfs.values()))
    rows = []
    for name, m in sorted(
        srams.items(), key=lambda kv: (-kv[1]["w_um"] * kv[1]["h_um"], kv[0])
    ):
        shape = re.search(r"(\d+)x(\d+)$", name)
        words, bits = (num(int(shape.group(1))), shape.group(2)) if shape else ("", "")
        rows.append(
            [
                "`%s`" % name,
                words,
                bits,
                len(m["instances"]),
                "%sx%s" % (num(m["w_um"], 1), num(m["h_um"], 1)),
                "`%s`" % where(m["instances"]),
            ]
        )
    v["sram_table"] = table(
        ["Macro", "Words", "Bits", "Instances", "W x H um", "Where"],
        rows,
        right=("Words", "Bits", "Instances", "W x H um"),
        abbrev={"Instances": "Inst."},
    )
    rows = []
    for name in sorted(
        rfs, key=lambda k: -int(regfiles[k]["words"]) * int(regfiles[k]["bits"])
    ):
        s, m = regfiles[name], rfs[name]
        rows.append(
            [
                "`%s`" % name,
                "%s x %s" % (s["words"], s["bits"]),
                s["read"],
                s["write"],
                len(m["instances"]),
                "%sx%s" % (num(m["w_um"], 1), num(m["h_um"], 1)),
                "`%s`" % where(m["instances"]),
            ]
        )
    v["regfile_table"] = table(
        [
            "Register file",
            "Words x bits",
            "Read ports",
            "Write ports",
            "Instances",
            "W x H um",
            "Where",
        ],
        rows,
        right=("Read ports", "Write ports", "Instances", "W x H um"),
        abbrev={"Read ports": "R", "Write ports": "W", "Instances": "Inst."},
    )
    v["regfile_max_read"] = str(max(s["read"] for s in regfiles.values()))
    v["regfile_max_write"] = str(max(s["write"] for s in regfiles.values()))

    # the tile's interface, as the RTL declares it, grouped by bus
    rtl = json.load(open(a.rtl_ports))
    groups = {}
    for q in rtl:
        words = q["name"].split("_")
        key = "_".join(words[:3]) if words[0] in ("io", "auto") else q["name"]
        g = groups.setdefault(key, {"in": 0, "out": 0, "ports": 0})
        g["in" if q["dir"] == "input" else "out"] += q["width"]
        g["ports"] += 1
    rows = [
        ["`%s`" % k, g["ports"], num(g["in"]), num(g["out"])]
        for k, g in sorted(groups.items(), key=lambda kv: -(kv[1]["in"] + kv[1]["out"]))
    ]
    v["rtl_port_table"] = table(
        ["Ports", "Count", "Input bits", "Output bits"],
        rows,
        right=("Count", "Input bits", "Output bits"),
    )
    v["rtl_ports"] = num(len(rtl))
    v["rtl_bits"] = num(sum(q["width"] for q in rtl))
    if sum(q["width"] for q in rtl) != facts["ports"]:
        raise SystemExit(
            "render_md: the netlist has %d port bits, the RTL %d"
            % (facts["ports"], sum(q["width"] for q in rtl))
        )

    # the floorplan
    svg, W, H = floorplan_svg(plan_bzl, plan)
    with open(a.svg, "w") as f:
        f.write(svg)
    v["die"] = "%s x %s" % (num(W), num(H))
    v["die_exact"] = "%.3f x %.3f" % (W, H)
    v["die_mm2"] = num(W * H / 1e6, 2)
    v["fill_pct"] = num(100.0 * facts["std_area_um2"] / (W * H))
    v["block_count"] = str(len(plan_bzl["macros"]))
    v["port_side"] = plan["parent"]["port_side"]

    # the periods: the latest KPI row that measured every block
    run = [r for r in kpi["runs"] if "blocks" in r][-1]
    periods = run["blocks"]
    parent = "XSTile_parent"
    v["kpi_date"] = run["date"]
    # XSTile's period: its slowest part, the Top's crossings included
    v["best_period"] = num(max(list(periods.values()) + [run.get("top_ps", 0)]))
    v["parent_period"] = num(periods[parent])
    v["target_ps"] = num(kpi["target_ps"])
    pins = {m["name"]: m["pins"] for m in plan["macros"]}
    rows = []
    undescribed = sorted(set(plan_bzl["macros"]) - set(blocks))
    if undescribed:
        raise SystemExit(
            "render_md: blocks.json has no description for %s" % ", ".join(undescribed)
        )
    for name, m in sorted(
        plan_bzl["macros"].items(),
        key=lambda kv: -float(kv[1]["DIE_AREA"].split()[2])
        * float(kv[1]["DIE_AREA"].split()[3]),
    ):
        d = m["DIE_AREA"].split()
        rows.append(
            [
                "`%s`" % name,
                blocks[name],
                "%s x %s" % (num(float(d[2])), num(float(d[3]))),
                num(pins[name]),
                num(periods[name]),
            ]
        )
    rows.append(
        [
            "**the rest of the tile**",
            blocks[parent],
            "die minus blocks",
            v["rtl_bits"],
            "**%s**" % num(periods[parent]),
        ]
    )
    v["block_table"] = table(
        ["Block", "What it is", "Outline um", "Pins", "Period ps"],
        rows,
        right=("Outline um", "Pins", "Period ps"),
    )

    # build times and memory
    units = res["units"]
    parts = list(plan_bzl["macros"]) + [parent]
    absent = [p for p in parts if p not in units]
    if absent:
        raise SystemExit(
            "render_md: resources.json does not measure %s" % ", ".join(absent)
        )
    rows = []

    def total(u):
        return sum(units[u]["stages"][s]["minutes"] for s in STAGES)

    def peak(u):
        return max(units[u]["stages"][s]["peak_gb"] for s in STAGES)

    for u in sorted(plan_bzl["macros"], key=lambda u: -total(u)) + [parent]:
        st = units[u]["stages"]
        label = "**the rest of the tile**" if u == parent else "`%s`" % u
        rows.append(
            [label]
            + [num(st[s]["minutes"], 1) for s in STAGES]
            + [num(total(u)), num(peak(u), 1)]
        )
    v["times_table"] = table(
        [
            "Part",
            "Synth",
            "Floorplan",
            "Place",
            "Clock tree",
            "Global route",
            "Total min",
            "Peak GB",
        ],
        rows,
        right=(
            "Synth",
            "Floorplan",
            "Place",
            "Clock tree",
            "Global route",
            "Total min",
            "Peak GB",
        ),
        abbrev={"Floorplan": "FP", "Clock tree": "CTS", "Global route": "GRT"},
    )
    v["resources_commit"] = res["commit"]
    v["resources_date"] = res["date"]
    slowest = max(plan_bzl["macros"], key=total)
    v["slowest_block"] = slowest
    v["slowest_block_min"] = num(total(slowest))
    v["parent_hours"] = num(total(parent) / 60.0, 1)
    v["parent_peak_gb"] = num(peak(parent))

    # the arrays' A/B
    rows = [
        [
            "`%s`" % r["block"],
            r["kind"],
            num(r["a_min"], 1),
            num(r["b_min"], 1),
            num(r["a_ps"]),
            num(r["b_ps"]),
        ]
        for r in ab["rows"]
    ]
    v["ab_table"] = table(
        [
            "Structure",
            "Kind",
            "Flow min, as written",
            "Flow min, extracted",
            "Period ps, as written",
            "Period ps, extracted",
        ],
        rows,
        right=(
            "Flow min, as written",
            "Flow min, extracted",
            "Period ps, as written",
            "Period ps, extracted",
        ),
        abbrev={
            "Flow min, as written": "A min",
            "Flow min, extracted": "B min",
            "Period ps, as written": "A ps",
            "Period ps, extracted": "B ps",
        },
    )

    # versions
    repo, commit = opensta_pin(open(a.module_bazel).read())
    v["opensta_repo"] = repo
    v["opensta_commit"] = commit
    v["commit"] = status(a.status).get("STABLE_GIT_COMMIT", "unstamped")
    # a commit that can be checked out: a kit built from uncommitted work
    # names no such commit, so its instructions take the latest instead
    v["checkout"] = (
        v["commit"] if re.match(r"^[0-9a-f]+$", v["commit"]) else "origin/main"
    )
    v["build_date"] = status(a.status).get("STABLE_BUILD_DATE", "unstamped")
    pin = json.load(open(a.pin))
    v["pin_netlist"], v["pin_date"] = pin["netlist_sha256"], pin["date"]

    # the test script, included as it ships
    v["sta_tcl"] = open(a.sta).read().rstrip("\n")
    return v


def render(template, values):
    used = set()

    def fill(m):
        key = m.group(1)
        if key not in values:
            raise SystemExit("render_md: no value for {{%s}}" % key)
        used.add(key)
        return values[key]

    out = re.sub(r"\{\{(\w+)\}\}", fill, template)
    unused = sorted(set(values) - used)
    if unused:
        raise SystemExit(
            "render_md: facts nothing in the template uses: %s" % ", ".join(unused)
        )
    return out


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    for flag in (
        "template",
        "out",
        "svg",
        "facts",
        "plan",
        "plan-bzl",
        "kpi",
        "resources",
        "ab",
        "blocks",
        "module-bazel",
        "sta",
        "rtl-ports",
        "pin",
    ):
        p.add_argument("--" + flag, required=True)
    p.add_argument("--status")
    p.add_argument("regfiles", nargs="+")
    a = p.parse_args(argv)
    text = render(open(a.template).read(), facts_values(a))
    with open(a.out, "w") as f:
        f.write(text)


if __name__ == "__main__":
    main()
