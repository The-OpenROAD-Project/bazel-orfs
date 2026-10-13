# potential_report (pilot)

Says where a design's repeating structures leave period or area on the
table, and whose problem it is: the RTL's (a rewrite buys it), the
flow's (the structure is far from what the literature says it should
cost), or nobody's. Advisory: it never edits RTL, no flow stage reads
it, and a finding is a recommendation the flow's own period confirms or
refutes.

This is the pilot that gauges whether the report is worth building; the
pilot's results and the go/no-go are in the pull request that adds it.

## Tiers

| tier | what | cost | file |
|---|---|---|---|
| 1 | shapes in the netlist, counted on yosys JSON of the hierarchy: replicated leaves, constant-per-instance ports compared inside the leaf (decoders in disguise), broadcast keys into compares (CAMs), flat CAMs of registered words, triangular age matrices, wide reductions over a group's outputs | seconds per module | `detect.py` |
| 2 | what-if: the parent synthesised with the leaf kept and flattened, on generic gates (cells, unit levels) or mapped to the library and timed by OpenSTA with fanout loads and no wire | minutes per module | `whatif.py` |
| 3 | the placed truth: arms of one function through the flow to placement, period as clock minus worst slack | tens of minutes per arm | `//test/potential_report` |

The literature column (`models.py`) converts published access times to
FO4 with Hrishikesh et al.'s 360 ps per drawn micron; every row names its
source and scope. `calibrate/` times generated register files on their
own placement against that column.

## Running it

```sh
bazelisk test //tools/potential_report:detect_test
bazelisk build //test/coremark_joule/designs/asap7/xiangshan:Rob_potential_findings
bazelisk build //test/coremark_joule/designs/asap7/xiangshan:Rob_potential_whatif
bazelisk build //tools/potential_report/calibrate:regfile_read
bazelisk build //test/potential_report:rob_like_kept_period
```

Tier 1 reads a module straight from XiangShan's flat Verilog with
slang, as synthesis reads it; it does not need any block flow.

## Known limits, stated

- Unit gate levels cannot see fanout; only the library arm and tier 3
  can say anything about period.
- The matrix detector reads register names; a matrix whose registers
  are not named by two indices is missed.
- The literature rows model custom arrays (CACTI's sense-amplified
  bitlines); a standard-cell structure is not expected to reach them.
