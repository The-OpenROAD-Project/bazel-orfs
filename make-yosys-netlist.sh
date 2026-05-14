#!/usr/bin/env bash
#
# Symmetric companion to //:yosys-check.  Feeds make's pre-built yosys
# netlist into a fresh bazel run and SHA-compares the resulting .odb at
# every stage against make's own .odb.  When MATCH, the bazel-test
# build of OpenROAD is bit-identical to tools/install OpenROAD given
# the same starting netlist — a one-command proof that any bazel
# `_test` QoR failure on this design is yosys-environment drift, not a
# bazel-orfs / OpenROAD bug.
#
# Usage:
#   bazelisk run //:make-yosys-netlist //flow/designs/<plat>/<design>:<n>_test
#
# Output: a 7-row × 3-column SHA table covering 1_synth.odb through
# 6_final.odb.  Two comparison columns:
#   1. bazel-natural vs make            -> usually DIFFER (yosys-env drift)
#   2. bazel-with-make-netlist vs make  -> expected MATCH (the proof)

set -e -u -o pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: bazelisk run //:make-yosys-netlist <test-label>" >&2
    echo "       e.g.  bazelisk run //:make-yosys-netlist //flow/designs/asap7/jpeg_lvt:jpeg_encoder_test" >&2
    exit 2
fi

cd "${BUILD_WORKSPACE_DIRECTORY:?must be invoked via bazelisk run}"

LABEL="$1"

case "$LABEL" in
    //flow/designs/*/*:*_test) ;;
    *)
        echo "make-yosys-netlist: expected //flow/designs/<plat>/<design>:<name>_test, got $LABEL" >&2
        exit 2
        ;;
esac

PKG="${LABEL#//}"; PKG="${PKG%:*}"
NAME="${LABEL##*:}"
DESIGN_DIR="${PKG#flow/designs/}"
PLAT="${DESIGN_DIR%%/*}"
DESIGN="${DESIGN_DIR#*/}"
BASE="${NAME%_test}"
SYNTH_TARGET="//$PKG:${BASE}_synth"
FINAL_TARGET="//$PKG:${BASE}_final"

# BLOCKS= designs don't pass clean bazel-vs-make comparisons because
# bazel-orfs's hierarchical-block plumbing differs from make's
# (sub-block .lef/.lib aren't staged into the parent synth action).
# See aes-block.  Refuse rather than emit a misleading DIFFER table.
if grep -qE '^[[:space:]]*export[[:space:]]+BLOCKS[[:space:]]*[?:]?=' \
     "flow/designs/$PLAT/$DESIGN/config.mk"; then
    echo "make-yosys-netlist: $DESIGN sets BLOCKS=… (hierarchical design)." >&2
    echo "  bazel-orfs's BLOCKS handling diverges from make's at the parent" >&2
    echo "  synth step (sub-block abstracts not staged into the parent action)" >&2
    echo "  so a per-stage .odb comparison won't be apples-to-apples." >&2
    echo "  Skipping; this is a known bazel-orfs gap, not an OpenROAD-determinism" >&2
    echo "  question." >&2
    exit 2
fi

echo "==> Building $FINAL_TARGET (bazel-natural baseline; produces the full .odb chain)"
bazelisk build "$FINAL_TARGET"

# Bazel-side results subdir glob (bazel uses DESIGN_NAME for the path).
BAZEL_PLAT_DIR="bazel-bin/$PKG/results/$PLAT"
BAZEL_NICK=$(basename "$(ls -d "$BAZEL_PLAT_DIR"/*/ 2>/dev/null | head -1)" 2>/dev/null)
BAZEL_NICK="${BAZEL_NICK:-$DESIGN}"

# Make-side results subdir (make uses DESIGN_NICKNAME).
MAKE_NICK=$(awk '
    /^[[:space:]]*export[[:space:]]+DESIGN_NICKNAME[[:space:]]*=/ {
        n = index($0, "="); v = substr($0, n + 1)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", v); print v; exit
    }
' "flow/designs/$PLAT/$DESIGN/config.mk")
MAKE_NICK="${MAKE_NICK:-$DESIGN}"
echo "==> bazel subdir=$BAZEL_NICK   make subdir=$MAKE_NICK"

BAZEL_NATURAL="bazel-bin/$PKG/results/$PLAT/$BAZEL_NICK/base"
MAKE_RES="flow/results/$PLAT/$MAKE_NICK/base"

echo "==> Installing OpenROAD into tools/install/ (idempotent)"
( cd tools/OpenROAD && bazelisk run //:install )

echo "==> Running full make flow (yields make's 1_2_yosys.v and full .odb chain)"
( cd flow && make clean_all DESIGN_CONFIG="designs/$PLAT/$DESIGN/config.mk" ) || true
( cd flow && make finish DESIGN_CONFIG="designs/$PLAT/$DESIGN/config.mk" ) || true

MAKE_NETLIST_RO="$MAKE_RES/1_2_yosys.v"
if [[ ! -f "$MAKE_NETLIST_RO" ]]; then
    echo "make-yosys-netlist: make's 1_2_yosys.v not at $MAKE_NETLIST_RO" >&2
    echo "  (the 'make finish' run above failed before yosys; nothing to feed bazel)" >&2
    exit 1
fi

# synth_preamble.tcl copies SYNTH_NETLIST_FILES with `cp -p`; the
# canonicalize step then the synth step each copy.  The second cp
# fails on a read-only dest, so stage to a writable temp.
# Stage the bazel-natural .odb files into a temp dir BEFORE the second
# bazel run overwrites them in bazel-bin/.
MAKE_NETLIST="$(mktemp --suffix=-make-1_2_yosys.v)"
NATURAL_STAGED="$(mktemp -d --suffix=-bazel-natural)"
trap 'rm -f "$MAKE_NETLIST"; rm -rf "$NATURAL_STAGED"' EXIT
cp --no-preserve=mode "$MAKE_NETLIST_RO" "$MAKE_NETLIST"
echo "==> Snapshotting bazel-natural .odb to $NATURAL_STAGED"
for f in 1_synth.odb 2_floorplan.odb 3_place.odb 4_cts.odb \
         5_1_grt.odb 5_route.odb 6_final.odb; do
    [[ -f "$BAZEL_NATURAL/$f" ]] && cp "$BAZEL_NATURAL/$f" "$NATURAL_STAGED/$f"
done

echo "==> Re-running bazel flow with make's netlist injected via SYNTH_NETLIST_FILES"
# bazel-orfs supports positional KEY=VAL args after `bazel run` (see
# bazel-orfs/README.md:354-368).  The override propagates to make on
# the command line where it wins over the design config.
bazelisk run "$FINAL_TARGET" -- SYNTH_NETLIST_FILES="$MAKE_NETLIST"

# The second run wrote fresh .odb to the same bazel-bin path.
BAZEL_OVERLAY="$BAZEL_NATURAL"

echo ""
echo "==> .odb SHA matrix"
printf '%-22s  %-18s  %-18s  %-18s  %s\n' \
    stage bazel-natural make 'bazel+make-netlist' outcome
all_overlay_match=1
for f in 1_synth.odb 2_floorplan.odb 3_place.odb 4_cts.odb \
         5_1_grt.odb 5_route.odb 6_final.odb; do
    bs=$(sha256sum "$NATURAL_STAGED/$f" 2>/dev/null | cut -c1-16 || true)
    ms=$(sha256sum "$MAKE_RES/$f"       2>/dev/null | cut -c1-16 || true)
    os=$(sha256sum "$BAZEL_OVERLAY/$f"  2>/dev/null | cut -c1-16 || true)
    if [[ -z "$os" && -z "$ms" ]]; then
        ovl_tag=skip
    elif [[ -n "$os" && "$os" == "$ms" ]]; then
        ovl_tag=MATCH
    else
        ovl_tag=DIFFER
        all_overlay_match=0
    fi
    printf '%-22s  %-18s  %-18s  %-18s  %s\n' \
        "$f" "${bs:--}" "${ms:--}" "${os:--}" "$ovl_tag"
done

echo ""
if [[ $all_overlay_match -eq 1 ]]; then
    echo "make-yosys-netlist: every stage MATCHes in the 'bazel-with-make-netlist'"
    echo "  column -> bazel-test OpenROAD is bit-identical to tools/install"
    echo "  OpenROAD given the same yosys netlist.  Any bazel _test QoR failure"
    echo "  on this design is yosys-environment drift, not a bazel-orfs or"
    echo "  OpenROAD bug."
    exit 0
else
    echo "make-yosys-netlist: some stages DIFFER even with the same netlist ->"
    echo "  real bazel-vs-make OpenROAD divergence on this design.  Worth"
    echo "  filing the per-stage SHA matrix as an issue."
    exit 1
fi
