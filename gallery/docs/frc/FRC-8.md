# FRC-8: cell-not-found

| Field | Value |
|-------|-------|
| **ID** | FRC-8 |
| **Name** | cell-not-found |
| **Severity** | Error |
| **Stage** | synth (STA timing) |

## What it checks

After synthesis, OpenSTA resolves every cell instance against the loaded
liberty libraries. When a cell name referenced in the netlist or SDC is
not present in any library, OpenSTA emits STA-0453 and the flow aborts.

## Why it matters

A missing cell means the design references a technology library that was
not included in the build configuration. The error appears only after
synthesis completes, wasting the synthesis runtime.

## Root cause

On ihp-sg13g2, the platform `config.mk` conditionally adds IO pad
libraries when `FOOTPRINT_TCL` is set:

```makefile
ifneq ($(FOOTPRINT_TCL),)
    export ADDITIONAL_SLOW_LIBS += .../sg13g2_io_slow_1p08V_3p0V_125C.lib
    export ADDITIONAL_FAST_LIBS += .../sg13g2_io_fast_1p32V_3p6V_m40C.lib
    export ADDITIONAL_TYP_LIBS += .../sg13g2_io_typ_1p2V_3p3V_25C.lib
endif
```

Bazel does not evaluate Makefile conditionals. When `CORNERS = slow fast`
is set, `read_liberty.tcl` loads `SLOW_LIB_FILES` and `FAST_LIB_FILES`
(which include `ADDITIONAL_SLOW_LIBS` / `ADDITIONAL_FAST_LIBS`). Without
the per-corner IO pad libs, OpenSTA cannot resolve `sg13g2_IOPadIn`.

The original patch 0033 only added `ADDITIONAL_LIBS` (typ corner),
missing the slow/fast corner libs that `read_liberty.tcl` actually loads.

## Example

`ihp-sg13g2/i2c-gpio-expander:I2cGpioExpanderTop_synth` failed with:

```
[WARNING STA-0363] pin 'sg13g2_IOPad_io_clock/p2c' not found.
[ERROR STA-0453] 'sg13g2_IOPadIn' not found.
```

## Fix

Add per-corner IO pad libs explicitly in the design's `config.mk`:

```makefile
export ADDITIONAL_SLOW_LIBS += $(PLATFORM_DIR)/lib/sg13g2_io_slow_1p08V_3p0V_125C.lib
export ADDITIONAL_FAST_LIBS += $(PLATFORM_DIR)/lib/sg13g2_io_fast_1p32V_3p6V_m40C.lib
export ADDITIONAL_LIBS += $(PLATFORM_DIR)/lib/sg13g2_io_typ_1p2V_3p3V_25C.lib
```

This was applied in the updated patch 0033 and verified: synthesis now
passes with IO pad libs loaded for both slow and fast corners.

Also required: add `ADDITIONAL_SLOW_LIBS`, `ADDITIONAL_FAST_LIBS`, and
`ADDITIONAL_TYP_LIBS` to `config_mk_parser.py` SOURCE_VARS so the parser
resolves these platform-relative paths to Bazel labels.

## Implementation

Not yet implemented in mock-openroad. The mock synthesis flow does not
validate that every instantiated cell has a matching liberty entry.
A future implementation could cross-reference the Yosys netlist cell
names against the loaded liberty cell names.
