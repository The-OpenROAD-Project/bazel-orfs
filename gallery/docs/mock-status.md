# Mock OpenROAD/Yosys — Status and Next Steps

*Updated 2026-03-26*

## What's Done

### Mock binaries (mock/)
- **TCL interpreter** in `mock/tcl/` — executes ORFS stage scripts with
  mock command implementations. Handles `{*}` expansion, braces-no-substitution,
  nested `[$obj method]` calls, `lmap`, `clock`, proc with args.
- **Mock OpenROAD** in `mock/openroad/` — creates ODB, SDC, LEF, LIB, logs,
  metrics JSON. Mock ODB object model for `mock_area.tcl`. SDC commands:
  `get_ports`, `create_clock`, `group_path`, `set_input_delay`/`set_output_delay`,
  `all_registers`, `all_inputs` (with `-no_clocks`), `all_outputs`.
- **Mock Yosys** in `mock/yosys/` — parses Verilog for module/port/reg
  structure, estimates cell counts, produces mock netlist + synth_stat.txt.
- **129 unit tests** total (77 TCL + 36 openroad + 16 yosys).

### A/B comparison flow
- `demo_flow(mock=True)` creates base (real) + mock variants via `orfs_sweep`
  with per-variant `openroad`/`yosys` override.
- `demo_sram(mock=True)` uses two separate `orfs_flow` calls (base with
  `mock_area`, mock without) to avoid `mock_area.tcl` reading text-stub ODB.
- `demo_hierarchical(mock=True)` works now that mock OpenROAD implements
  `all_registers`/`all_inputs`/`all_outputs` for platform SDC `group_path`.
- 7 per-stage `py_test` targets compare real vs mock outputs (synth → final).
- `mock_compare_test.py` — shared A/B logic parameterized by `--stage`/`--design`.

### Smoketest project (smoketest/)
- `counter` — flat flow with `mock=True, substeps=True`. 7 A/B tests.
- `tiny_sram` — SRAM macro with `mock=True, mock_area=200.0`.
- `counter_with_sram` — hierarchical with `mock=True`. 6 A/B tests.
- `mock_make_test` — Bazel `sh_test` (tagged manual, needs ORFS checkout).
  Runs mock tools through synth of counter_with_sram via ORFS Makefile.
- `config.mk` + `block.mk` — ORFS Makefile configs with `BLOCKS = tiny_sram`.

### Other changes
- `gallery.bzl` — gallery image macros split from `defs.bzl`.
- `MODULE.bazel` — `git_override` for bazel-orfs (22be97c), mock modules,
  ORFS bumped to 26Q1-737.

### bazel-orfs changes (merged upstream)
- `sweep.bzl` — per-variant `openroad`/`yosys` override in sweep dict.
- `private/attrs.bzl` — public `yosys` attribute (renamed from `_yosys`).
- `private/flow.bzl` — `_strip_tool_kwargs()` for `orfs_macro`/`orfs_run`,
  filter `yosys` from non-synth stages.
- Included in upstream bazel-orfs commit `22be97c`.

## Next Steps

1. **Add serv `mock=True`** — serv has no `mock_area`, should work now.

2. **Train from real data** — serv has real `logs/`, `metrics/`, `reports/`.
   Compare mock estimates vs real. Encode as unit tests.

3. **Estimation intelligence** — cell count calibration, runtime
   prediction, parameter suggestions.

4. **mock-train skill** — `.claude/commands/mock-train.md` for capturing
   debugging insights as mock unit tests.

5. **Run full A/B tests** — verify counter, tiny_sram, and counter_with_sram
   mock tests pass after ORFS bump to 26Q1-737.
