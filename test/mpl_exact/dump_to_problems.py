"""Convert mpl's study dumps (MPL_DUMP_DIR jsonl) into packing problems.

One problem per distinct (design, tag, outline, blocks); the annealer's
own outcome for it is carried along so the exact check can be compared
with what mpl did.

usage: dump_to_problems.py <design> <dump.jsonl>... > problems.txt
       (also writes problems.csv beside stdout's target via --csv)
"""

import argparse
import csv
import json
import re
import sys


def clean(name):
    return re.sub(r"[^A-Za-z0-9_./:\[\]-]", "_", name) or "_"


def blocks_of(record):
    blocks = []
    soft = record["kind"] == "soft"
    # Only the first seq_pair_macros take part in the packing (0: all); the
    # rest are wirelength terminals (IO clusters, the parent's other cells).
    count = record["seq_pair_macros"] or len(record["macros"])
    for m in record["macros"][:count]:
        w, h = m["w"], m["h"]
        name = clean(m["name"])
        if soft:
            t = m["type"]
            if m["fixed"] or t in ("blockage", "terminal", "io"):
                if w * h == 0:
                    continue
                blocks.append(("F", name, m["x"], m["y"], w, h))
            elif t == "macro":
                shapes = sorted({(a[0], b[0]) for a, b in zip(m["wi"], m["hi"])})
                blocks.append(("R", name, shapes))
            elif t in ("mixed", "std"):
                if m["area"] == 0:
                    continue
                # SoftMacro::resizeRandomly: interval k's area is
                # min width * max height.
                blocks.append(
                    (
                        "S",
                        name,
                        [
                            (wi[0], wi[1], wi[0] * hi[1])
                            for wi, hi in zip(m["wi"], m["hi"])
                        ],
                    )
                )
            else:
                raise SystemExit(f"unknown soft macro type {t} in {record['tag']}")
        else:
            if m["fixed"]:
                blocks.append(("F", name, m["x"], m["y"], w, h))
            else:
                blocks.append(("R", name, [(w, h)]))
    return blocks


def line_of(block):
    if block[0] == "F":
        return "B {1} F {2} {3} {4} {5}".format(*block)
    if block[0] == "R":
        return f"B {block[1]} R {len(block[2])} " + " ".join(
            f"{w} {h}" for w, h in block[2]
        )
    return f"B {block[1]} S {len(block[2])} " + " ".join(
        f"{lo} {hi} {area}" for lo, hi, area in block[2]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("design")
    parser.add_argument("dumps", nargs="+")
    parser.add_argument("--csv", required=True)
    args = parser.parse_args()

    problems = {}
    for path in args.dumps:
        with open(path) as f:
            for row in f:
                r = json.loads(row)
                x0, y0, x1, y1 = r["outline"]
                key = (r["tag"], x1 - x0, y1 - y0, json.dumps(blocks_of(r)))
                entry = problems.setdefault(
                    key,
                    {
                        "runs": 0,
                        "valid": 0,
                        "seconds": 0.0,
                        "first_valid": [],
                        "steps": r["steps"] * r["perturb_per_step"],
                        "record": r,
                    },
                )
                entry["runs"] += 1
                entry["valid"] += r["valid"]
                entry["seconds"] += r["seconds"]
                entry["first_valid"].append(r["first_valid_step"])

    with open(args.csv, "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(
            [
                "id",
                "design",
                "tag",
                "kind",
                "width",
                "height",
                "dbu",
                "blocks",
                "runs",
                "valid_runs",
                "sa_seconds",
                "first_valid_steps",
                "steps",
            ]
        )
        for i, (key, e) in enumerate(problems.items()):
            tag, width, height, blocks = key
            blocks = json.loads(blocks)
            pid = f"{args.design}#{i}"
            print(f"P {pid} {width} {height} {len(blocks)}")
            for b in blocks:
                print(line_of(b))
            out.writerow(
                [
                    pid,
                    args.design,
                    tag,
                    e["record"]["kind"],
                    width,
                    height,
                    e["record"]["dbu"],
                    len(blocks),
                    e["runs"],
                    e["valid"],
                    f"{e['seconds']:.4f}",
                    " ".join(map(str, e["first_valid"])),
                    e["steps"],
                ]
            )


if __name__ == "__main__":
    sys.exit(main())
