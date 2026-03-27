> **Repo**: Run from the openroad-demo root.

Capture unexpected values from mock OpenROAD/Yosys runs and turn them into
unit tests and sanity checks.

## What Mock OpenROAD Is

A flow linter that runs in seconds. See
[flow-linter-with-frc.md](../../gallery/docs/flow-linter-with-frc.md)
for the full vision: why a linting flow (not just static checks) is needed,
the separation of concerns with real OpenROAD, FRC rule design, and the
formalization path to upstream `frc.yaml`.

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
