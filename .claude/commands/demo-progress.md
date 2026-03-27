Monitor and report progress on a running bazel-orfs build.

Use this skill to check what stage a long-running build is at and what it's doing.

## 1. Find the active build process

```bash
ps -Af | grep '[t]ee.*\.log'
```

This finds the `tee` process that ORFS uses to log each subcommand. The log path
tells you which stage is running:
- `1_1_yosys_canonicalize.log` → Synthesis: reading RTL with slang/yosys
- `1_2_yosys.log` → Synthesis: technology mapping with ABC
- `2_1_floorplan.log` → Floorplan: die area, IO placement
- `2_4_floorplan_pdn.log` → Floorplan: power distribution network
- `3_1_place_gp_skip_io.log` → Placement: global placement without IO (RePlAce)
- `3_3_place_gp.log` → Placement: global placement (RePlAce)
- `3_5_place_dp.log` → Placement: detailed placement
- `4_1_cts.log` → Clock tree synthesis (TritonCTS)
- `5_1_grt.log` → Global routing (FastRoute)
- `5_2_route.log` → Detailed routing (TritonRoute) — often the slowest stage
- `6_report.log` → Final reporting: timing, power, area

**Tip**: The log may be a `.tmp.log` while running. Use:
```bash
tail -f <log_path_with_.tmp.log>
```

## 2. Tail the active log and interpret

```bash
tail -30 <log_path>
```

### What to look for per stage:

**Synthesis (1_2_yosys.log)**:
- `Executing ABC pass` → technology mapping, can be very slow for large flat designs
- `ABC failed with status F` → design too large for flat synthesis, need SYNTH_HIERARCHICAL=1
- `Printing statistics` → almost done

**Global Placement (3_1_place_gp_skip_io.log / 3_3_place_gp.log)**:
```
      iter |  overflow |     HPWL      |  change  |  step     |
      100  |   0.9971  |  1.988e+05    |  +4.17%  |  3.03e-13 |
      110  |   0.9969  |  2.141e+05    |  +7.68%  |  4.92e-13 |
```
- Watch **overflow** decreasing toward 0 (target: <0.1)
- Watch **HPWL** (half-perimeter wirelength) stabilizing
- If overflow is stuck high after hundreds of iterations → placement may not converge,
  try lower PLACE_DENSITY or larger CORE_UTILIZATION

**Global Routing (5_1_grt.log)**:
- `[GRT-0101] Running routing...` → in progress
- Watch **overflow** decreasing to 0
- `[FLW-0009] Clock clk slack` → timing summary at end

**Detailed Routing (5_2_route.log)**:
- `[DRT-0001] iteration N` → routing iterations
- Watch **violations** (DRC) decreasing: `1523 → 892 → 412 → 0`
- If violations plateau → may need routing layer adjustments

**Final Report (6_report.log)**:
- `Total power` → power consumption
- `Cell type report` → final cell counts

## 3. Report qualitatively

Tell the user:
- Which stage is running (e.g., "Global placement, iteration 150, overflow 0.45")
- Whether it looks healthy (e.g., "HPWL stabilizing, overflow decreasing steadily")
- If it looks stuck or about to fail

ARGUMENTS: $ARGUMENTS
