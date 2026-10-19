"""Where a CI run's time went, from the Bazel profile it wrote.

    slowest_actions.py <profile> [<top>]

Prints the critical path, the time per mnemonic and the slowest actions.
The profile is Bazel's JSON trace (--profile), gzipped or not; times in
it are microseconds.
"""

import collections
import gzip
import json
import sys


def load(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw)["traceEvents"]


def summarize(events, top):
    actions = [
        e for e in events if e.get("cat") == "action processing" and e.get("ph") == "X"
    ]
    critical = [
        e
        for e in events
        if e.get("cat") == "critical path component" and e.get("ph") == "X"
    ]
    lines = []

    total = sum(e["dur"] for e in critical)
    lines.append("Critical path: {:.0f} s".format(total / 1e6))
    for e in sorted(critical, key=lambda e: -e["dur"])[:top]:
        lines.append("{:8.0f} s  {}".format(e["dur"] / 1e6, e["name"]))

    per_mnemonic = collections.defaultdict(lambda: [0, 0])
    for e in actions:
        m = per_mnemonic[e.get("args", {}).get("mnemonic", "?")]
        m[0] += e["dur"]
        m[1] += 1
    lines.append("")
    lines.append("Time per mnemonic (summed over parallel actions):")
    for name, (dur, n) in sorted(per_mnemonic.items(), key=lambda kv: -kv[1][0])[:top]:
        lines.append("{:8.0f} s  {:6d}  {}".format(dur / 1e6, n, name))

    lines.append("")
    lines.append("Slowest actions:")
    for e in sorted(actions, key=lambda e: -e["dur"])[:top]:
        lines.append(
            "{:8.0f} s  {:<14} {}".format(
                e["dur"] / 1e6, e.get("args", {}).get("mnemonic", "?"), e["name"]
            )
        )
    return "\n".join(lines)


def main():
    top = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    print(summarize(load(sys.argv[1]), top))


if __name__ == "__main__":
    main()
