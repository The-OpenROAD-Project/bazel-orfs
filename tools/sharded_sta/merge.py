"""Merge the shards of a sharded timing into one report.

    merge.py <out.json> <out.md> <out.ends> <count> <shard>=<rows>,<paths>,<stats>...

Each endpoint is reported by exactly one shard; one reported twice is an
error, so nothing is counted twice. The period comes from the exact rows,
those every path into which runs through netlists; the rows a timing model
reaches are counted and listed apart. <out.ends> holds the exact rows as
module_sta's ends files do, for ends.py compare against a flat timing.
"""

import json
import sys

BUCKETS = [
    float("-inf"),
    -200,
    -100,
    -50,
    -20,
    -10,
    0,
    10,
    20,
    50,
    100,
    200,
    float("inf"),
]


def read_rows(path):
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                pin, slack, exact = line.rsplit(" ", 2)
                yield pin, float(slack), exact == "1"


def histogram(slacks):
    out = []
    for lo, hi in zip(BUCKETS, BUCKETS[1:]):
        out.append(
            {"from": lo, "to": hi, "count": sum(1 for s in slacks if lo <= s < hi)}
        )
    return out


def merge(shards):
    """shards: {name: [(pin, slack, exact)]} -> {pin: (slack, exact, shard)}."""
    out = {}
    for name, rows in sorted(shards.items()):
        for pin, slack, exact in rows:
            if pin in out:
                raise ValueError(
                    "%s is reported by both shard %s and shard %s"
                    % (pin, out[pin][2], name)
                )
            out[pin] = (slack, exact, name)
    return out


def paths_of(path):
    """{endpoint: report text} of a shard's paths file."""
    out = {}
    pin = None
    with open(path) as f:
        for line in f:
            if line.startswith("endpoint "):
                pin = line.split(" ", 1)[1].strip()
                out[pin] = []
            elif pin is not None:
                out[pin].append(line)
    return {k: "".join(v) for k, v in out.items()}


def report(merged, stats, count):
    exact = {p: v for p, v in merged.items() if v[1]}
    modelled = {p: v for p, v in merged.items() if not v[1]}
    worst = sorted(exact.items(), key=lambda kv: (kv[1][0], kv[0]))[:count]
    return {
        "endpoints": len(merged),
        "exact": len(exact),
        "modelled": len(modelled),
        "wns_exact": min((v[0] for v in exact.values()), default=None),
        "wns_modelled": min((v[0] for v in modelled.values()), default=None),
        "tns_exact": sum(v[0] for v in exact.values() if v[0] < 0),
        "histogram_exact": histogram([v[0] for v in exact.values()]),
        "histogram_modelled": histogram([v[0] for v in modelled.values()]),
        "worst": [{"endpoint": p, "slack": v[0], "shard": v[2]} for p, v in worst],
        "shards": stats,
    }


def markdown(r, texts):
    lines = [
        "# Sharded timing",
        "",
        "%d endpoints: %d exact, %d through a timing model."
        % (r["endpoints"], r["exact"], r["modelled"]),
        "Worst exact slack %s ps; worst modelled slack %s ps."
        % (r["wns_exact"], r["wns_modelled"]),
        "",
        "| Slack from (ps) | to | exact | modelled |",
        "| --- | --- | --- | --- |",
    ]
    for e, m in zip(r["histogram_exact"], r["histogram_modelled"]):
        lines.append(
            "| %s | %s | %d | %d |" % (e["from"], e["to"], e["count"], m["count"])
        )
    lines += [
        "",
        "| Shard | cells | endpoints | exact | seconds | peak MiB |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, s in sorted(r["shards"].items()):
        lines.append(
            "| %s | %s | %s | %s | %s | %s |"
            % (
                name,
                s.get("cells"),
                s.get("endpoints"),
                s.get("exact"),
                s.get("seconds"),
                s.get("peak_mib"),
            )
        )
    lines += ["", "## Worst exact endpoints", ""]
    for w in r["worst"]:
        lines.append("- %s %s ps (shard %s)" % (w["endpoint"], w["slack"], w["shard"]))
        text = texts.get(w["shard"], {}).get(w["endpoint"])
        if text:
            lines += ["", "```", text.rstrip(), "```", ""]
    return "\n".join(lines) + "\n"


def main(argv):
    out_json, out_md, out_ends, count = argv[0], argv[1], argv[2], int(argv[3])
    shards, stats, texts = {}, {}, {}
    for arg in argv[4:]:
        name, files = arg.split("=", 1)
        rows, paths, stat = files.split(",")
        shards[name] = list(read_rows(rows))
        texts[name] = paths_of(paths)
        with open(stat) as f:
            stats[name] = json.load(f)
    merged = merge(shards)
    r = report(merged, stats, count)
    with open(out_json, "w") as f:
        json.dump(r, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(out_md, "w") as f:
        f.write(markdown(r, texts))
    with open(out_ends, "w") as f:
        for pin in sorted(merged):
            if merged[pin][1]:
                f.write("%s %s\n" % (pin, merged[pin][0]))


if __name__ == "__main__":
    main(sys.argv[1:])
