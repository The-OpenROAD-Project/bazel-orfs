"""The wire campaign's probe on the miniature: each row has every field
the ledger reads, the floor is under the period, and the parent placed
at 0.7 has less wire than at 0.2 -- the mechanism the campaign measures
on XSTile (docs/plans/xstile-wire-campaign.md)."""

import json
import sys

FIELDS = (
    "period_ps",
    "floor_ps",
    "hpwl_m",
    "worst_wire_um",
    "target_density",
    "gp_instances",
    "steps",
)


def main(d02_path, d07_path):
    rows = {}
    for density, path in (("0.2", d02_path), ("0.7", d07_path)):
        with open(path) as f:
            row = json.load(f)
        missing = [k for k in FIELDS if row.get(k) is None]
        assert not missing, "%s: no %s" % (path, missing)
        assert 0 < row["floor_ps"] <= row["period_ps"], row
        assert abs(row["target_density"] - float(density)) < 1e-6, row
        assert "3_5_place_dp" in row["steps"], row["steps"]
        rows[density] = row
    assert rows["0.7"]["hpwl_m"] < rows["0.2"]["hpwl_m"], (
        rows["0.2"]["hpwl_m"],
        rows["0.7"]["hpwl_m"],
    )
    print(
        "ok: HPWL %.4f m at 0.2, %.4f m at 0.7"
        % (rows["0.2"]["hpwl_m"], rows["0.7"]["hpwl_m"])
    )


if __name__ == "__main__":
    main(*sys.argv[1:])
