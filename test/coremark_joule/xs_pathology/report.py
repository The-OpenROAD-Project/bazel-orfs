#!/usr/bin/env python3
"""Tables from pathology records: report.py RESULTS_DIR ARM[=LABEL]...

Each ARM is a record name (RESULTS_DIR/ARM.json); a record that is not
there renders as "not yet measured". Fails with no records at all.
"""

import json
import os
import sys

COLUMNS = [
    ("slew_viol", "slew violators", "{:,}"),
    ("cap_viol", "cap", "{:,}"),
    ("fanout_viol", "fanout", "{:,}"),
    ("long_nets", "nets > 200 um", "{:,}"),
    ("period_ps", "period, ps", "{:,.0f}"),
    ("worst_stage_share", "worst path in one stage", "{:.0%}"),
]


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    results = argv[1]
    rows = []
    found = 0
    for spec in argv[2:]:
        arm, _, label = spec.partition("=")
        path = os.path.join(results, arm + ".json")
        if not os.path.exists(path):
            rows.append(
                "| %s | not yet measured |%s"
                % (label or arm, " |" * (len(COLUMNS) + 1))
            )
            continue
        found += 1
        r = json.load(open(path))
        cells = [
            fmt.format(r[key]) if r.get(key) is not None else ""
            for key, _, fmt in COLUMNS
        ]
        kept = (
            "yes"
            if sorted(r.get("kept", [])) == sorted(r.get("kept_expected", []))
            else "no"
        )
        rows.append("| %s | %s | %s |" % (label or arm, " | ".join(cells), kept))
    if not found:
        raise SystemExit(
            "report.py: no records in %s; run the campaign first" % results
        )
    print("| arm | " + " | ".join(c[1] for c in COLUMNS) + " | kept = stated |")
    print("|---|" + "---:|" * len(COLUMNS) + "---|")
    print("\n".join(rows))


if __name__ == "__main__":
    main(sys.argv)
