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
synthesis completes, wasting the synthesis runtime. In Bazel, the
dependency on the correct library must be declared explicitly — unlike
Make, there is no ambient search path.

## Example

`ihp-sg13g2/i2c-gpio-expander:I2cGpioExpanderTop_synth` fails with:

```
[WARNING STA-0363] pin 'sg13g2_IOPad_io_clock/p2c' not found.
[ERROR STA-0453] 'sg13g2_IOPadIn' not found.
```

The design instantiates IHP IO pad cells (`sg13g2_IOPadIn`,
`sg13g2_IOPad`) but the IO pad liberty library is not included in the
synthesis liberty file list.

## Fix

Add the IO pad liberty file to the design's `ADDITIONAL_LIBS` or
equivalent configuration so that OpenSTA can resolve all cell references.

## Implementation

Not yet implemented in mock-openroad. The mock synthesis flow does not
validate that every instantiated cell has a matching liberty entry.
A future implementation could cross-reference the Yosys netlist cell
names against the loaded liberty cell names.
