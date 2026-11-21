"""Block's report has a synthesis estimate and a real value for every data
port bus: each register-to-boundary path has an arc in both views."""

import sys

rows = {}
for line in open(sys.argv[1]):
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) == 6 and cells[0] not in ("bus", "---"):
        rows[cells[0]] = cells
assert set(rows) >= {"in_bits", "in_valid", "out_bits", "out_valid"}, sorted(rows)
for bus in ["in_bits", "in_valid", "out_valid"]:
    _, _, _, estimated, real, diff = rows[bus]
    assert "-" not in (estimated, real, diff), rows[bus]
    float(estimated), float(real), float(diff)
print("ok")
