# Optuna minimum example

Use `--define X=Y` to override variables in ORFS `config.mk`. `--define X=Y` is adequate for simple ORFS flows to drive Optuna where there's no ambiguity as to which of several subflows that varibles such as `PLACE_DENSITY` refers to:

    bazelisk run --define PLACE_DENSITY=0.1234 //:lb_32x128_floorplan_deps /tmp/x print-PLACE_DENSITY

Outputs:

    PLACE_DENSITY = 0.1234

## Simple Optuna example to search for minimum clock period

Search for minimum clock period using the synthesis stage only:

    bazelisk run //optuna:min-clock-synth

