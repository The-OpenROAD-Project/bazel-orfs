"""Pin the ASAP7 sweep YAML into the source tree.

`bazel run @bazel-orfs//tools/memory_macro_scaler/characterization:pin_asap7_sweep`
harvests the characterized `.lib` files from the committed per-shape
orfs_flow() abstracts and writes the result YAML back to
`tools/memory_macro_scaler/characterization/asap7_sweep.yaml` *inside
the workspace source tree*. That pins the numbers into git so the fit
picks them up on every subsequent tool invocation without re-running
the (slow) sweep.

Writing to the source tree from a Bazel target requires the
BUILD_WORKSPACE_DIRECTORY environment variable that `bazel run` sets
for its subprocess. `bazel test` does not set it; that is the idiom
signalling "this target is a pin / update, not a test."

When the per-shape orfs_flow() targets land in
`characterization/BUILD`, this script's `data` list grows to include
them; until then, running the target produces an empty `runs: []`
YAML and exits cleanly so the pin step is in place.
"""

import argparse
import os
import sys
from pathlib import Path

import generate_sweep


_RELATIVE_YAML = "tools/memory_macro_scaler/characterization/asap7_sweep.yaml"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--result-files",
        nargs="*",
        default=[],
        type=Path,
        help="Harvested .lib files from the per-shape abstract targets. "
        "When empty, an empty runs list is written.",
    )
    args = p.parse_args(argv)

    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not workspace:
        print(
            "pin_asap7_sweep: BUILD_WORKSPACE_DIRECTORY is not set — "
            "this target is meant to be run via `bazel run`, not "
            "`bazel test` / `bazel build`.",
            file=sys.stderr,
        )
        return 2

    out = Path(workspace) / _RELATIVE_YAML
    if not out.parent.exists():
        print(
            f"pin_asap7_sweep: expected directory {out.parent} does "
            "not exist — is this the bazel-orfs workspace?",
            file=sys.stderr,
        )
        return 2

    if not args.result_files:
        return _write_empty(out)
    return generate_sweep.main(
        [
            "--result-files",
            *(str(p) for p in args.result_files),
            "--output",
            str(out),
        ]
    )


_STUB_HEADER = """\
# ASAP7 FF-memory characterization sweep
# =======================================
#
# Committed output of the manual Bazel target
# //tools/memory_macro_scaler/characterization:pin_asap7_sweep, which
# harvests per-shape orfs_flow() abstracts on ASAP7 into a structured
# YAML that memory_macro_scaler.py auto-loads and folds into its fit.
#
# Regenerate (after the per-shape abstracts have built):
#
#     bazel run //tools/memory_macro_scaler/characterization:pin_asap7_sweep
#
# Empty `runs: []` means "no sweep results harvested yet" — the tool
# falls back to the built-in MEMORY_DATA_POINTS (OpenRAM/DFFRAM
# numbers from public PDKs).
#
# Schema
# ------
# version: int (increment on incompatible schema changes)
# runs:    list of characterized macros, each with:
#   tech_nm:         int     technology node in nanometers
#   kind:            str     "ff" | "sram"
#   rows:            int     number of words
#   bits:            int     word width in bits
#   ports_key:       str     "1RW" | "1R1W" | "2R1W" | …
#   write_mask_bits: int     byte-write = 8, whole-word = 0, etc.
#   area_um2:        float   macro outline area
#   access_time_ps:  float   reg-to-reg read delay worst-case
#   setup_ps:        float   data-side setup wrt clock
#   hold_ps:         float   data-side hold wrt clock
#   wns_ps:          float   worst negative slack at clk_period_ps
#   clk_period_ps:   float   target clock period used in the sweep
#   tool:            str     toolchain tag, e.g. "orfs-0.0.0"
#   notes:           str     free-form
"""


def _write_empty(out_path):
    """Write an empty-but-schema-documented stub YAML.

    Called when the pin target runs with no result files — keeps the
    rich schema comments in place so a future reader still knows what
    the file is for.
    """
    out_path.write_text(_STUB_HEADER + "\nversion: 1\nruns: []\n")
    print(
        f"pin_asap7_sweep: wrote empty stub to {out_path} "
        "(no per-shape result files were passed)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
