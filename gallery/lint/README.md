# Lint OpenROAD and Yosys

Seconds-fast lint binaries that replace real OpenROAD and Yosys for
flow validation. They execute ORFS TCL scripts via a minimal TCL
interpreter with lint command implementations, creating all expected
output files without running actual synthesis or place-and-route.

A **flow linter** that validates ORFS parameters against design intent,
catching configuration errors in seconds. Reports the kind of things an
expert human could tell you at a glance: estimated running times, macro
placement feasibility, pin placement conflicts, and cross-stage coherence.

## A/B Comparison Flow

Set `mock=True` on `demo_flow()` to create both real and lint variants
side by side via `orfs_sweep`. Per-stage `py_test` targets compare
outputs automatically:

```python
demo_flow(
    name = "counter",
    verilog_files = ["rtl/counter.sv"],
    arguments = {"CORE_UTILIZATION": "40", "PLACE_DENSITY": "0.65"},
    sources = {"SDC_FILE": [":constraints.sdc"]},
    substeps = True,
    mock = True,
)
```

This generates:
- `:counter_synth`, `:counter_floorplan`, ..., `:counter_final` (real)
- `:counter_mock_synth`, ..., `:counter_mock_final` (lint)
- `:counter_synth_mock_test`, ..., `:counter_final_mock_test` (A/B comparison)

Lint variant uses `@lint-openroad` and `@lint-yosys` injected via
per-variant override in `orfs_sweep`.

## Usage with Bazel (openroad-demo)

```bash
# Run A/B tests (builds both real + lint, compares outputs)
bazelisk test //smoketest:counter_floorplan_mock_test

# Build lint variant only (seconds)
bazelisk build //smoketest:counter_mock_final

# Build real variant only (minutes)
bazelisk build //smoketest:counter_final
```

## Usage with ORFS Make (standalone)

Build the lint binaries with Bazel, then pass them to ORFS via
environment variables:

```bash
# Build lint binaries
bazelisk build @lint-openroad//src/bin:openroad @lint-yosys//src/bin:yosys

# Use with ORFS make flow
cd OpenROAD-flow-scripts/flow
make OPENROAD_EXE=/path/to/bazel-bin/external/lint-openroad+/src/bin/openroad \
     YOSYS_EXE=/path/to/bazel-bin/external/lint-yosys+/src/bin/yosys \
     DESIGN_CONFIG=designs/asap7/counter/config.mk
```

## Structure

```
lint/
  tcl/          Shared TCL interpreter (used by both lint tools)
  openroad/     Lint OpenROAD binary + command implementations
  yosys/        Lint Yosys binary + command implementations
```

Each is a Bazel module (`lint-openroad`, `lint-yosys`, `lint-tcl`).

## ORFS Variable Validation

The lint validates all ORFS variables from `variables.yaml`:
- Numeric ranges: CORE_UTILIZATION, PLACE_DENSITY, ROUTING_LAYER_ADJUSTMENT
- PDK-aware die size limits (500um ASAP7, 10000um sky130)
- Scale factors: MOCK_AREA sanity
- Boolean flags: 18 SKIP_*/SYNTH_* flags
- Cross-variable consistency: CORE_UTILIZATION+DIE_AREA conflicts

## SDC Validation

- `get_ports <name>` — warns if port not found in Verilog
- `get_ports a b` — warns about multi-arg (STA-0566)
- `create_clock` — validates clock port exists
- `group_path` — accepts empty lists gracefully
- `set_input_delay`/`set_output_delay` — validates port names

## Tests

```bash
# TCL interpreter: 96 tests
python3 -m pytest lint/tcl/src/bin/tcl_interpreter_test.py

# OpenROAD commands: 81 tests (including flow linter)
python3 -m pytest lint/openroad/src/bin/openroad_commands_test.py

# Yosys commands: 22 tests
python3 -m pytest lint/yosys/src/bin/yosys_commands_test.py
```
