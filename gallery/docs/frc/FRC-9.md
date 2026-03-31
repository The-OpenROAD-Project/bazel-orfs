# FRC-9: pad-instance-not-found

| Field | Value |
|-------|-------|
| **ID** | FRC-9 |
| **Name** | pad-instance-not-found |
| **Severity** | Error |
| **Stage** | floorplan (2_1_floorplan) |

## What it checks

When `IO_NORTH_PINS`, `IO_SOUTH_PINS`, etc. reference pad cell instance
names, those instances must exist in the design after synthesis. If the
pad placement TCL (`FOOTPRINT_TCL`) has not yet instantiated the pads,
the floorplan step fails with PAD-0102.

## Why it matters

IO pad designs require a specific initialization order: pad cells must
be instantiated (via `FOOTPRINT_TCL` or `ICE40_FOOTPRINT`) before pin
placement can reference them. If the pad instantiation step is skipped
or not supported, the floorplan aborts immediately.

## Example

`ihp-sg13g2/i2c-gpio-expander:I2cGpioExpanderTop_floorplan` fails with:

```
[ERROR PAD-0102] Unable to find instance: sg13g2_IOPad_io_gpio_3
```

The design's `IO_NORTH_PINS` references pad instances that should be
created by `FOOTPRINT_TCL = $(PLATFORM_DIR)/pad.tcl`, but the Bazel
flow does not support the IO pad instantiation step.

## Fix

IO pad flow support requires the `FOOTPRINT_TCL` script to run during
floorplan initialization. This is a platform-level feature that needs
integration in the Bazel rules.

## Implementation

Not yet implemented. The IO pad instantiation flow is not supported in
the current Bazel rules for ihp-sg13g2.
