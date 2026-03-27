> **Repo**: Run from the openroad-demo root.

Capture unexpected values from mock OpenROAD/Yosys runs and turn them into
unit tests and sanity checks.

## What Mock OpenROAD Is: A Flow Linter

Mock OpenROAD is a **flow linter** that runs in seconds. It translates
inputs (ODB sizes, SDC constraints, LEF dimensions, cell counts) and
examines them quickly to report:

- **Estimated running times** per stage
- **Macro placement feasibility** — will it fit? aspect ratio issues?
- **Pin placement conflicts** — port count vs die perimeter
- **Cross-stage coherence** — e.g. "your pin placement will fail because
  you need to change the aspect ratio of the macro"
- **Configuration errors** — wrong scale factors, missing constraints,
  bad units

A mock run in the bazel-orfs GUI gives you a useful report: the kind of
things an expert human could tell you at a glance, reported in seconds.

**Separation of concerns**: Real OpenROAD's policy is "you asked for it,
you deserve the result" — PDN will happily generate an 8000x8000um grid.
Mock OpenROAD's job is to tell you *before* that happens whether what
you're asking for follows the intent.

Error messages gather information crossing stages to present a coherent
story. Claude helps capture heuristics from debugging sessions and encode
them into unit tests automatically.

## Formalization Path

The checks hardcoded in mock OpenROAD/Yosys lint will, when stable, be
refactored into the upstream `variables.yaml` file and formalized
(adding `min`, `max`, `type`, cross-variable constraints). Eventually,
the lint would live in ORFS itself, but while being developed it is good
to have the lint change in lockstep with the openroad-demo data —
the demo projects provide the ground truth for what values are sane.

## When to Use This Skill

After a mock build fails, hangs, or produces wrong output — or after
debugging a real flow issue where mock *should have* caught it. The goal:
ensure mock catches this class of problem next time.

## 1. Identify the Problem

Check build logs for mock warnings/errors:

```bash
bazelisk build <target> 2>&1 | grep -E 'mock:|ERROR|WARNING' | tail -30
```

Common patterns:
- **Hang/timeout**: insane DIE_AREA or MOCK_AREA scale factor
- **STA-0391**: platform SDC `group_path` on gutted design
- **Missing output files**: unimplemented TCL command
- **Wrong estimates**: cell count, area, or timing wildly off vs real

## 2. Check for Crazy Values

Environment variables and computed values — the most common sources:

- `MOCK_AREA` — scale factor, should be 0.1–10.0 (NOT absolute area)
- `DIE_AREA` — microns; ASAP7 macros rarely exceed 500um, sky130 much larger
- `CORE_UTILIZATION` — percent, must be (0, 100]
- Cell count estimates — compare mock vs base `synth_stat.txt`
- LEF SIZE — proportional to cell count and utilization

## 3. Add Sanity Check to Mock Python

Add the check in `mock/openroad/src/bin/openroad_commands.py` (or
`yosys_commands.py`) at the command that first encounters the value:

```python
if value > SANE_MAX:
    print(
        f"mock: ERROR: {name}={value}"
        f" exceeds {SANE_MAX} — likely a"
        f" configuration error",
        file=sys.stderr,
    )
```

Thresholds should be PDK-dependent (500um for ASAP7, larger for sky130).
Use `_MAX_DIE_UM` as the reference constant.

Check locations:
- `cmd_initialize_floorplan` — DIE_AREA, MOCK_AREA, CORE_UTILIZATION
- `cmd_write_abstract_lef` — computed LEF size
- `cmd_orfs_write_db` — cell count in metrics

## 4. Add Unit Test

Add to `mock/openroad/src/bin/openroad_commands_test.py` (or yosys/tcl):

```python
def test_<thing>_insane_warns(self, interp, capsys):
    """<describe what's insane and why>."""
    os.environ["VAR"] = "bad_value"
    interp.eval("command_that_checks")
    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    del os.environ["VAR"]

def test_<thing>_sane_no_warn(self, interp, capsys):
    os.environ["VAR"] = "good_value"
    interp.eval("command_that_checks")
    captured = capsys.readouterr()
    assert "ERROR" not in captured.err
    del os.environ["VAR"]
```

Always add both positive (insane triggers error) and negative (sane is quiet).

## 5. Run Tests

```bash
/usr/bin/python3 -m pytest mock/openroad/src/bin/openroad_commands_test.py -v
/usr/bin/python3 -m pytest mock/tcl/src/bin/tcl_interpreter_test.py -v
/usr/bin/python3 -m pytest mock/yosys/src/bin/yosys_commands_test.py -v
```

## 6. Fix the Root Cause

If the crazy value came from `defs.bzl` or `BUILD.bazel`, fix that too.
Add Starlark `fail()` for values validatable at analysis time.

## 7. Commit

Commit the sanity check, unit tests, and root cause fix together.

## Existing Checks

| Check | Location | Threshold |
|-------|----------|-----------|
| DIE_AREA too large | `cmd_initialize_floorplan` | >500um (ASAP7) |
| MOCK_AREA too large | `cmd_initialize_floorplan` | >10.0 |
| CORE_UTILIZATION range | `cmd_initialize_floorplan` | (0, 100] |
| LEF SIZE too large | `cmd_write_abstract_lef` | >500um (ASAP7) |
