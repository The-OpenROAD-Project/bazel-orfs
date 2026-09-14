"""The global router's own congestion report, which the metrics JSON omits.

ORFS writes 82 `globalroute__*` metrics and not one of them is a
congestion number. The routing resource picture exists only in the stage
log, as the GRT-0096 table:

    [INFO GRT-0096] Final congestion report:
    Layer         Resource        Demand        Usage (%)    Max H / Max V / Total Congestion
    ----------------------------------------------------------------------
    M2                2041           467           22.88%             0 /  0 /  0
    ...
    Total            10625          1286           12.10%             0 /  0 /  0

That omission matters here. OpenROAD #7581 was a *routing congestion*
failure on `dynamic_node` traced to a global placement change, and the
thread's whole diagnosis ran through this table -- target density
spiking, 76% area inflation on the first routability iteration. A study
of a placement knob that reported only timing and wirelength could
reproduce that failure and not notice.

So the endpoint is parsed from the log rather than dropped, and the
per-layer rows are kept as well as the total: congestion concentrated on
one layer and congestion spread over five are different problems, and
the total alone cannot tell them apart.
"""

import re

_HEADER = re.compile(r"GRT-0096\]\s*Final congestion report")

# Layer rows and the Total row share a shape: a name, three numbers, a
# percentage, then the three-way max-H / max-V / total field. The last
# column is headed "Total Overflow" on some versions and "Total
# Congestion" on others; the numbers are in the same place either way, so
# the header wording is deliberately not matched.
_ROW = re.compile(
    r"^(?P<layer>\S+)\s+"
    r"(?P<resource>\d+)\s+"
    r"(?P<demand>\d+)\s+"
    r"(?P<usage>[0-9.]+)%\s+"
    r"(?P<max_h>\d+)\s*/\s*(?P<max_v>\d+)\s*/\s*(?P<total>\d+)\s*$",
    re.M,
)


def summarize(text):
    """The final congestion report.

    Args:
        text: a `5_1_grt.log`.

    Returns:
        A dict, or None when the report is absent -- a run that failed
        before global route finished, which must read as missing rather
        than as zero congestion.

        * `total_resource`, `total_demand`, `total_usage_pct`
        * `total_overflow`  the Total row's third field
        * `max_layer_usage_pct` and `max_layer` -- the worst single
          layer, which the total hides
        * `layers`          per-layer rows, in report order
        * `congested`       any layer reports non-zero overflow
    """
    match = _HEADER.search(text)
    if not match:
        return None
    # Only the last report: global route prints one per iteration when
    # it runs extra passes to remove overflow, and the last one is the
    # result. Taking the first would report the problem it fixed.
    tail = text[text.rfind("GRT-0096") :]
    rows = []
    total = None
    for row in _ROW.finditer(tail):
        entry = {
            "layer": row.group("layer"),
            "resource": int(row.group("resource")),
            "demand": int(row.group("demand")),
            "usage_pct": float(row.group("usage")),
            "max_h": int(row.group("max_h")),
            "max_v": int(row.group("max_v")),
            "overflow": int(row.group("total")),
        }
        if entry["layer"].lower() == "total":
            total = entry
        else:
            rows.append(entry)
    if total is None:
        return None
    routed = [row for row in rows if row["resource"] > 0]
    worst = max(routed, key=lambda row: row["usage_pct"]) if routed else None
    return {
        "total_resource": total["resource"],
        "total_demand": total["demand"],
        "total_usage_pct": total["usage_pct"],
        "total_overflow": total["overflow"],
        "max_layer_usage_pct": worst["usage_pct"] if worst else None,
        "max_layer": worst["layer"] if worst else None,
        "congested": any(row["overflow"] > 0 for row in rows),
        "layers": rows,
    }
