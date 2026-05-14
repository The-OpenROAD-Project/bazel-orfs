#!/usr/bin/env bash
#
# Test whether a failing bazel `_test` is a yosys-environment false
# positive or a real bazel-vs-make OpenROAD divergence.
#
# Usage: bazelisk run //:yosys-check //flow/designs/<plat>/<design>:<n>_test
#
# Yosys is sensitive to its build environment (abc version, cxxopts
# version, compile flags), so bazel-built yosys and make-built yosys
# produce different `1_2_yosys.v` for the same RTL.  Different netlists
# then push QoR metrics around enough to break rules-base.json
# thresholds even when OpenROAD is behaving identically.  This wrapper
# feeds bazel's pre-built netlist into a fresh make-flow run (via
# SYNTH_NETLIST_FILES) and SHA-compares .odb at every stage:
#
#   all MATCH    -> yosys-only false positive, ignore.
#   any DIFFER   -> real bazel-vs-make OpenROAD divergence, investigate.

set -e -u -o pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: bazelisk run //:yosys-check <test-label>" >&2
    echo "       e.g.  bazelisk run //:yosys-check //flow/designs/asap7/uart:uart_test" >&2
    exit 2
fi

cd "${BUILD_WORKSPACE_DIRECTORY:?must be invoked via bazelisk run}"

LABEL="$1"

# Parse //flow/designs/<plat>/<design>:<name>_test
case "$LABEL" in
    //flow/designs/*/*:*_test) ;;
    *)
        echo "yosys-check: expected //flow/designs/<plat>/<design>:<name>_test, got $LABEL" >&2
        exit 2
        ;;
esac

PKG="${LABEL#//}"; PKG="${PKG%:*}"      # flow/designs/asap7/uart
NAME="${LABEL##*:}"                     # uart_test
DESIGN_DIR="${PKG#flow/designs/}"       # asap7/uart
PLAT="${DESIGN_DIR%%/*}"                # asap7
DESIGN="${DESIGN_DIR#*/}"               # uart
SYNTH_TARGET="//$PKG:${NAME%_test}_synth"

# BLOCKS= designs don't pass clean bazel-vs-make comparisons because
# bazel-orfs's hierarchical-block plumbing differs from make's
# (sub-block .lef/.lib aren't staged into the parent synth action).
# See aes-block.  Refuse rather than emit a misleading DIFFER table.
# Matches make-yosys-netlist.sh.
if grep -qE '^[[:space:]]*export[[:space:]]+BLOCKS[[:space:]]*[?:]?=' \
     "flow/designs/$PLAT/$DESIGN/config.mk"; then
    echo "yosys-check: $DESIGN sets BLOCKS=… (hierarchical design)." >&2
    echo "  bazel-orfs's BLOCKS handling diverges from make's at the parent" >&2
    echo "  synth step (sub-block abstracts not staged into the parent action)" >&2
    echo "  so a per-stage .odb comparison won't be apples-to-apples." >&2
    echo "  Skipping; this is a known bazel-orfs gap, not an OpenROAD-determinism" >&2
    echo "  question." >&2
    exit 2
fi

# bazel-orfs and classic make disagree on which design-config var to
# put in the results path: bazel uses DESIGN_NAME (the module/top),
# make uses DESIGN_NICKNAME (the user-friendly tag).  For most designs
# they're equal; aes-block is the canonical exception
# (DESIGN_NAME=aes_cipher_top vs DESIGN_NICKNAME=aes-block).
echo "==> Building $SYNTH_TARGET (need bazel's 1_2_yosys.v and the results subdir)"
bazelisk build "$SYNTH_TARGET"

# Bazel side: glob the single subdir under bazel-bin/<pkg>/results/<plat>/.
BAZEL_PLAT_DIR="bazel-bin/$PKG/results/$PLAT"
BAZEL_NICK=$(basename "$(ls -d "$BAZEL_PLAT_DIR"/*/ 2>/dev/null | head -1)" 2>/dev/null)
BAZEL_NICK="${BAZEL_NICK:-$DESIGN}"

# Make side: parse DESIGN_NICKNAME out of the design's config.mk.
MAKE_NICK=$(awk '
    /^[[:space:]]*export[[:space:]]+DESIGN_NICKNAME[[:space:]]*=/ {
        n = index($0, "="); v = substr($0, n + 1)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", v); print v; exit
    }
' "flow/designs/$PLAT/$DESIGN/config.mk")
MAKE_NICK="${MAKE_NICK:-$DESIGN}"
echo "==> bazel subdir=$BAZEL_NICK   make subdir=$MAKE_NICK"

BAZEL_RES="bazel-bin/$PKG/results/$PLAT/$BAZEL_NICK/base"
MAKE_RES="flow/results/$PLAT/$MAKE_NICK/base"

echo "==> Building $LABEL (so we have bazel's downstream .odb to compare)"
bazelisk build "$LABEL"

echo "==> Installing OpenROAD into tools/install/ (idempotent)"
( cd tools/OpenROAD && bazelisk run //:install )

BAZEL_NETLIST_RO="$(pwd)/$BAZEL_RES/1_2_yosys.v"
if [[ ! -f "$BAZEL_NETLIST_RO" ]]; then
    echo "yosys-check: bazel netlist not at $BAZEL_NETLIST_RO" >&2
    exit 1
fi

# synth_preamble.tcl copies SYNTH_NETLIST_FILES with `cp -p`, which
# carries over the source's perms.  bazel-out files are read-only, so
# the second copy (do-yosys after do-yosys-canonicalize) hits
# "Permission denied" on the read-only destination.  Stage the netlist
# in a writable temp path so both copies succeed.
BAZEL_NETLIST="$(mktemp --suffix=-1_2_yosys.v)"
trap 'rm -f "$BAZEL_NETLIST"' EXIT
cp --no-preserve=mode "$BAZEL_NETLIST_RO" "$BAZEL_NETLIST"

echo "==> make clean_all + metadata with bazel netlist (SYNTH_NETLIST_FILES)"
# Run make in a subshell that tolerates non-zero exit codes — metadata-check
# may fail on QoR thresholds even when the .odb stages are bit-identical to
# bazel.  We only care about SHA equivalence; the QoR comparison is bazel's
# `_test` job, and the whole point of yosys-check is to look past that.
( cd flow \
  && make clean_all DESIGN_CONFIG="designs/$PLAT/$DESIGN/config.mk" ) || true
( cd flow \
  && make metadata DESIGN_CONFIG="designs/$PLAT/$DESIGN/config.mk" \
                   SYNTH_NETLIST_FILES="$BAZEL_NETLIST" ) || true

echo ""
echo "==> .odb SHA matrix (bazel vs make, same netlist)"
printf '%-22s  %-18s  %-18s  %s\n' stage bazel make outcome
all_match=1
for f in 1_synth.odb 2_floorplan.odb 3_place.odb 4_cts.odb \
         5_1_grt.odb 5_route.odb 6_final.odb; do
    bs=$(sha256sum "$BAZEL_RES/$f" 2>/dev/null | cut -c1-16 || true)
    ms=$(sha256sum "$MAKE_RES/$f"  2>/dev/null | cut -c1-16 || true)
    if [[ -n "$bs" && "$bs" == "$ms" ]]; then
        tag=MATCH
    elif [[ -z "$bs" && -z "$ms" ]]; then
        tag=skip
    else
        tag=DIFFER
        all_match=0
    fi
    printf '%-22s  %-18s  %-18s  %s\n' "$f" "${bs:--}" "${ms:--}" "$tag"
done

echo ""
if [[ $all_match -eq 1 ]]; then
    echo "yosys-check: all stages MATCH -> bazel _test failure (if any) is a"
    echo "             yosys-environment false positive; OpenROAD is deterministic."
    exit 0
else
    echo "yosys-check: some stages DIFFER -> bazel-vs-make OpenROAD divergence."
    echo "             Investigate compile flags, abc version, etc."
    exit 1
fi
