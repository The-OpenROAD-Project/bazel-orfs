"""The ladder's table, from the row JSONs run_row.sh keeps.

One line per row, flip-flops against the register file: minimum period
at global route (the pass rule: at most 3 % above), standard-cell area,
power, hold worst slack and the flows' wall time. A row that failed to
build says so and why; a row not yet run is absent.
"""

import json
import os
import sys


def fmt(row):
    if row.get("failed"):
        return "| %s | failed | | | | | | | %s |" % (row["name"], row.get("error", ""))
    f, r = row["flops"], row["regfile"]

    def pct(a, b):
        return "%+.1f %%" % (100.0 * (b / a - 1)) if a else "n/a"

    return (
        "| %s | %.0f / %.0f ps (%+.1f %%) | %s | %.0f / %.0f ps | %.0f / %.0f µm² (%s) | %.2f / %.2f mW (%s) | %.0f / %.0f ps | %.0f / %.0f s |"
        % (
            row["name"],
            f["min_period_ps"],
            r["min_period_ps"],
            row["period_delta_percent"],
            ("**passes**" if row["passes"] else "fails")
            + (
                ""
                if row.get("like_for_like", True)
                else " (macros differ: %d / %d)" % (f["macros"], r["macros"])
            ),
            f["setup_ws"],
            r["setup_ws"],
            f["stdcell_area"],
            r["stdcell_area"],
            pct(f["stdcell_area"], r["stdcell_area"]),
            1e3 * f["power"],
            1e3 * r["power"],
            pct(f["power"], r["power"]),
            1e12 * f["hold_ws"] if abs(f["hold_ws"]) < 1e-3 else f["hold_ws"],
            1e12 * r["hold_ws"] if abs(r["hold_ws"]) < 1e-3 else r["hold_ws"],
            f["total_seconds"],
            r["total_seconds"],
        )
    )


def main():
    rows = []
    d = sys.argv[1]
    for n in sorted(os.listdir(d)):
        if n.endswith(".json"):
            with open(os.path.join(d, n)) as f:
                rows.append(json.load(f))
    print(
        "| row | reg-to-reg min period, flops / regfile | ≤ 3 % | setup WS (all paths) | std-cell area | power | hold WS | stage wall time (logs with an elapsed line) |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for row in rows:
        print(fmt(row))


if __name__ == "__main__":
    main()
