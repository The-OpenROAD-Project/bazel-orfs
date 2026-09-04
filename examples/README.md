# Examples

The idiomatic way to write a bazel-orfs flow, kept deliberately small.

```bash
bazelisk run //examples:mac_final gui_final
```

`mac` is a multiply-accumulate unit: a 24-bit accumulator that adds the
product of two 8-bit inputs on every enabled clock. It is small enough to
run the whole ORFS flow on asap7 in a couple of minutes and has a real
timing path, the multiplier feeding the adder, for the GUI to show.

| File | What it is |
|---|---|
| [BUILD](BUILD) | One `orfs_flow()`; the file to copy into your own project |
| [mac.v](mac.v) | The RTL |
| [constraints.sdc](constraints.sdc) | Clock and I/O timing constraints |

## Things to try

Change `PLACE_DENSITY` in `BUILD` and rerun. Only placement and the stages
after it rebuild; synthesis and floorplan come from cache.

Change the clock period in `constraints.sdc` and rerun. Synthesis and
everything after it rebuild, because the SDC is a synthesis input.

Open the Tcl shell instead of the GUI and ask for the worst path:

```bash
bazelisk run //examples:mac_final open_final
report_checks -path_delay max
```

Re-run one substep outside Bazel, edit the flow Tcl, run it again:

```bash
bazelisk run //:deps -- //examples:mac_place do-3_4_place_resized
```

See [docs/local-flow.md](../docs/local-flow.md) for that workflow and
[docs/customize.md](../docs/customize.md) for macros, abstracts and
parameter sweeps.

## Examples versus tests

This directory is written to be read; `//test` is written to break when a
rule changes. CI builds the example through `mac_build_test` so it cannot
rot, but when clarity and coverage pull in different directions, clarity
wins here and the coverage goes in `//test`.
