#!/usr/bin/env bash
#
# //:deps: a flow's stages in a tree you can run by hand.
#
#   bazelisk run //:deps -- start   <flow> <stage> [--dir D] [--variant V] [--fresh]
#   bazelisk run //:deps -- next    <stage>        [--dir D]
#   bazelisk run //:deps -- status                 [--dir D]
#   bazelisk run //:deps -- archive <flow> <stage> <file.tar.gz> [--variant V]
#
# start   Bazel builds everything <stage> needs (every stage before it)
#         and installs it, with <stage>'s scripts, in one tree per flow:
#         tmp/<package>/<flow>[_<variant>]. Run the stage there with
#         <tree>/make do-<stage>.
# next    Adds <stage>'s scripts to the same tree and keeps the results
#         already in it: a stage run by hand carries on into the next one
#         (the _deps lane, .claude/commands/deps-lane.md). Builds no stage.
# status  Says where each stage's result in the tree came from, Bazel or
#         a hand-run make, and which settings were edited.
# archive A self-contained reproducer .tar.gz of what <stage> needs.
#
# <flow> is the flow's label, //test:lb_32x128; a stage target's label,
# //test:lb_32x128_place, is accepted in place of <flow> <stage>.
# DEPS_STARTUP_OPTS (e.g. --output_base=...) and DEPS_BUILD_OPTS (e.g.
# --jobs=8) are passed to the bazelisk calls this makes.
# Building a stage's scripts is instant: Bazel builds only the output
# groups asked for, the same actions a plain build caches.

set -euo pipefail

STAGES="synth floorplan place cts grt route final generate_abstract"

die() {
    echo "deps: $*" >&2
    exit 1
}

usage() {
    sed -n '3,9p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-1}"
}

# bazel run executes from the runfiles tree; nested bazelisk calls and the
# trees belong to the workspace, relative paths to where the user typed.
WS="${BUILD_WORKSPACE_DIRECTORY:?run me with bazelisk run //:deps -- ...}"
CWD="${BUILD_WORKING_DIRECTORY:-$WS}"
cd "$WS"

# bazelisk with the caller's startup options
bz() {
    # shellcheck disable=SC2086 # options are words
    bazelisk ${DEPS_STARTUP_OPTS:-} "$@"
}

is_stage() {
    case " $STAGES " in *" $1 "*) return 0 ;; esac
    return 1
}

abspath() {
    case "$1" in
    /*) echo "$1" ;;
    *) echo "$CWD/$1" ;;
    esac
}

# --- target names -----------------------------------------------------------

# flow label + stage + variant -> stage target label
stage_target() {
    local flow="$1" stage="$2" variant="$3"
    if [ -n "$variant" ] && [ "$variant" != base ]; then
        echo "${flow}_${variant}_${stage}"
    else
        echo "${flow}_${stage}"
    fi
}

# //pkg:name -> pkg
label_pkg() { local l="${1#//}"; echo "${l%%:*}"; }
label_name() { echo "${1##*:}"; }

default_dir() {
    local flow="$1" variant="$2" name
    name="$(label_name "$flow")"
    if [ -n "$variant" ] && [ "$variant" != base ]; then
        name="${name}_${variant}"
    fi
    echo "$WS/tmp/$(label_pkg "$flow")/$name"
}

check_tmp_ignored() {
    local missing=()
    grep -qxF "tmp/" "$WS/.gitignore" 2>/dev/null || missing+=(".gitignore")
    grep -qxF "tmp" "$WS/.bazelignore" 2>/dev/null || missing+=(".bazelignore")
    if [ ${#missing[@]} -gt 0 ]; then
        die "'tmp' missing from ${missing[*]}: add 'tmp/' to .gitignore and 'tmp' to .bazelignore"
    fi
}

# --- building and installing --------------------------------------------------

# build_group <target> <group>: build an output group, print the manifest
build_group() {
    local target="$1" group="$2"
    bz build ${DEPS_BUILD_OPTS:-} --output_groups="$group" "$target" >&2 ||
        die "bazelisk build --output_groups=$group $target failed (is it an ORFS stage target?)"
    local manifest
    manifest="$(bz cquery --output=files --output_groups=deps_scripts "$target" 2>/dev/null |
        grep '_deps_manifest\.txt$' || true)"
    [ -n "$manifest" ] || die "$target has no deps manifest (is it an ORFS stage target?)"
    echo "$manifest"
}

# install_tree <manifest> <dir> <mode>: mode "all" installs every file,
# "keep-results" never writes an earlier stage's result.
install_tree() {
    local manifest="$1" dst="$2" mode="$3"
    local execroot outbase
    execroot="$(bz info execution_root 2>/dev/null)"
    outbase="$(bz info output_base 2>/dev/null)"
    mkdir -p "$dst/_main"
    local src to kind from
    while IFS=$'\t' read -r src to kind; do
        [ -n "$src" ] || continue
        # one link per repository instead, below
        case "$to" in _main/external/*) continue ;; esac
        if [ "$kind" = result ] && [ "$mode" = keep-results ]; then
            continue
        fi
        from="$execroot/$src"
        mkdir -p "$(dirname "$dst/$to")"
        rm -rf "${dst:?}/$to"
        if [ -L "$from" ] && [ "${src#external/}" = "$src" ]; then
            # a symlink artifact (a venv's interpreter): its relative
            # target resolves in the tree's runfiles layout, not here
            cp -P "$from" "$dst/$to"
            continue
        fi
        [ -e "$from" ] || die "$src is not built (manifest $manifest)"
        case "$src" in
        external/*)
            # other repositories (ORFS, the PDK): read, never edited. The
            # link goes to the output base, not the execroot, whose
            # external/ links each build replaces.
            ln -s "$outbase/$src" "$dst/$to"
            ;;
        *)
            # this workspace's sources and every Bazel output, tools
            # included: a copy, so an edit never reaches Bazel's output
            # tree and a later build never pulls a file out from under
            # the tree
            cp -R --dereference --preserve=mode "$from" "$dst/$to"
            chmod -R u+w "$dst/$to"
            ;;
        esac
    done <"$execroot/$manifest"
    # Bazel >= 8: _main/external/<repo> must resolve.
    rm -rf "$dst/_main/external"
    mkdir -p "$dst/_main/external"
    local repo name
    for repo in "$dst"/*/; do
        name="$(basename "$repo")"
        [ "$name" = _main ] && continue
        ln -sfn "../../$name" "$dst/_main/external/$name"
    done
    # Canonical repository names end in '+'; C++ runfiles look up the
    # apparent name without it.
    for repo in "$dst"/*+/; do
        [ -d "$repo" ] || continue
        name="$(basename "$repo")"
        [ -e "$dst/${name%+}" ] || ln -s "$name" "$dst/${name%+}"
    done
    # The manifest's make wrapper runs the stage; ours records the run.
    mv -f "$dst/make" "$dst/make.stage"
    cat >"$dst/make" <<'EOF'
#!/usr/bin/env bash
# Runs the installed stage's make and records the run in .deps, so
# `bazelisk run //:deps -- status` can say which results were made here.
here="$(cd "$(dirname "$0")" && pwd)"
rc=0
"$here/make.stage" "$@" || rc=$?
for a in "$@"; do
    case "$a" in do-*) echo "ran $a $(date '+%Y-%m-%d %H:%M') exit $rc" >>"$here/.deps" ;; esac
done
exit $rc
EOF
    chmod +x "$dst/make"
    cp -f "$dst/_main/config.mk" "$dst/.config.mk.installed"
}

# results_missing <manifest> <dir>: the first earlier-stage result the
# tree lacks, if any. Only results/ counts: an earlier stage's logs and
# reports are not what a stage reads, and Bazel's copies would describe
# a different run than the one made here.
results_missing() {
    local manifest="$1" dst="$2" execroot src to kind
    execroot="$(bz info execution_root 2>/dev/null)"
    while IFS=$'\t' read -r src to kind; do
        [ "$kind" = result ] || continue
        case "$to" in _main/external/*) continue ;; esac
        case "$to" in */results/*) ;; *) continue ;; esac
        [ -e "$dst/$to" ] || {
            echo "$to"
            return
        }
    done <"$execroot/$manifest"
}

tree_id() {
    if git -C "$WS" rev-parse --git-dir >/dev/null 2>&1; then
        local t
        t="$(git -C "$WS" rev-parse 'HEAD^{tree}')"
        git -C "$WS" diff --quiet HEAD -- 2>/dev/null || t="$t dirty"
        echo "$t"
    else
        echo "not a git workspace"
    fi
}

# the make targets that run a stage in the tree <dir>. ORFS spells
# synthesis as canonicalize, yosys, the SDC copy (a plain cp in Bazel,
# a file target in ORFS) and do-1_synth, which writes the 1_synth.odb
# floorplan reads; every other stage is do-<stage>.
stage_make() {
    local stage="$1" dir="$2" results
    if [ "$stage" = synth ]; then
        results="$("$dir/make.stage" print-RESULTS_DIR 2>/dev/null | sed -n 's/^RESULTS_DIR: //p' | tail -1)"
        echo "do-yosys-canonicalize do-yosys ${results:-<RESULTS_DIR>}/1_2_yosys.sdc do-1_synth"
    else
        echo "do-$stage"
    fi
}

next_steps() {
    local dir="$1" stage="$2"
    echo
    echo "Installed in ${dir#"$CWD"/}"
    echo "next: ${dir#"$CWD"/}/make $(stage_make "$stage" "$dir")"
}

# --- arguments ----------------------------------------------------------------

[ $# -ge 1 ] || usage
CMD="$1"
shift
DIR="" VARIANT="" FRESH=0
POS=()
while [ $# -gt 0 ]; do
    case "$1" in
    --dir)
        DIR="$(abspath "${2:?--dir needs a path}")"
        shift 2
        ;;
    --variant)
        VARIANT="${2:?--variant needs a name}"
        shift 2
        ;;
    --fresh)
        FRESH=1
        shift
        ;;
    -h | --help) usage 0 ;;
    -*) die "unknown option $1" ;;
    *)
        POS+=("$1")
        shift
        ;;
    esac
done

# <flow> <stage>, or a stage target's label alone
flow_and_stage() {
    if [ ${#POS[@]} -ge 2 ] && is_stage "${POS[1]}"; then
        FLOW="${POS[0]}" STAGE="${POS[1]}"
        POS=("${POS[@]:2}")
        return
    fi
    if [ ${#POS[@]} -ge 2 ] && [ "${POS[1]#*.}" = "${POS[1]}" ] && [ "${POS[1]#/}" = "${POS[1]}" ]; then
        die "'${POS[1]}' is not a stage; stages are: $STAGES"
    fi
    [ ${#POS[@]} -ge 1 ] || die "which flow and stage? e.g. //test:lb_32x128 place"
    local s
    for s in $STAGES; do
        case "${POS[0]}" in *_"$s")
            FLOW="${POS[0]%_"$s"}" STAGE="$s"
            POS=("${POS[@]:1}")
            return
            ;;
        esac
    done
    die "'${POS[0]}' names no stage; stages are: $STAGES"
}

# the tree `next` and `status` work on: --dir, the tree the user is in,
# or the one last started
find_tree() {
    if [ -n "$DIR" ]; then
        [ -f "$DIR/.deps" ] || die "no tree in ${DIR#"$CWD"/}: start one first"
        return
    fi
    local d="$CWD"
    while [ "$d" != / ]; do
        if [ -f "$d/.deps" ]; then
            DIR="$d"
            return
        fi
        d="$(dirname "$d")"
    done
    if [ -f "$WS/tmp/.deps_last" ]; then
        DIR="$(cat "$WS/tmp/.deps_last")"
        [ -f "$DIR/.deps" ] && return
    fi
    die "no tree here: start one with bazelisk run //:deps -- start <flow> <stage>"
}

deps_value() { sed -n "s/^$1 //p" "$DIR/.deps" | head -1; }

case "$CMD" in
start)
    flow_and_stage
    [ ${#POS[@]} -eq 0 ] || die "unexpected arguments: ${POS[*]}"
    check_tmp_ignored
    [ -n "$DIR" ] || DIR="$(default_dir "$FLOW" "$VARIANT")"
    if [ -e "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
        if [ "$FRESH" = 0 ]; then
            if [ -f "$DIR/.deps" ]; then
                echo "deps: ${DIR#"$CWD"/} already holds a tree; what it holds:" >&2
                grep -E '^(flow|stage|ran) ' "$DIR/.deps" | sed 's/^/  /' >&2
            fi
            die "refusing to replace ${DIR#"$CWD"/}: carry on with 'next <stage>', or 'start ... --fresh' to replace it"
        fi
        chmod -R u+w "$DIR" 2>/dev/null || true
        rm -rf "${DIR:?}"
    fi
    TARGET="$(stage_target "$FLOW" "$STAGE" "$VARIANT")"
    MANIFEST="$(build_group "$TARGET" deps_files)"
    install_tree "$MANIFEST" "$DIR" all
    {
        echo "flow $FLOW"
        echo "variant ${VARIANT:-base}"
        echo "tree $(tree_id)"
        echo "stage $STAGE scripts, earlier stages' results from bazel ($(date '+%Y-%m-%d %H:%M'))"
    } >"$DIR/.deps"
    echo "$DIR" >"$WS/tmp/.deps_last"
    if [ "$STAGE" = synth ] &&
        grep -qE '^export SYNTH_NUM_PARTITIONS\??=[1-9]' "$DIR/_main/config.mk"; then
        echo
        echo "deps: note: Bazel synthesises this design on its parallel path, in"
        echo "      partitions; a tree runs ORFS's serial synthesis, which can differ"
        echo "      from it or fail (AUTO_MEMORIES with SYNTH_HIERARCHICAL does). To"
        echo "      iterate after synthesis, start the lane at floorplan."
    fi
    next_steps "$DIR" "$STAGE"
    ;;
next)
    [ ${#POS[@]} -eq 1 ] || die "usage: next <stage>"
    STAGE="${POS[0]}"
    is_stage "$STAGE" || die "'$STAGE' is not a stage; stages are: $STAGES"
    find_tree
    FLOW="$(deps_value flow)"
    VARIANT="$(deps_value variant)"
    TARGET="$(stage_target "$FLOW" "$STAGE" "$VARIANT")"
    MANIFEST="$(build_group "$TARGET" deps_inputs)"
    missing="$(results_missing "$MANIFEST" "$DIR")"
    if [ -n "$missing" ]; then
        die "$STAGE needs ${missing#_main/}, which this tree does not have yet: run the stage before it here, or 'start $FLOW $STAGE' to have Bazel build it"
    fi
    if [ -f "$DIR/_main/config.mk" ] && ! cmp -s "$DIR/_main/config.mk" "$DIR/.config.mk.installed"; then
        prev="$(sed -n 's/^stage \([a-z_]*\) .*/\1/p' "$DIR/.deps" | tail -1)"
        cp -f "$DIR/_main/config.mk" "$DIR/config.mk.${prev:-edited}"
        echo "deps: your edited config.mk is kept as config.mk.${prev:-edited}; $STAGE has its own"
    fi
    install_tree "$MANIFEST" "$DIR" keep-results
    echo "stage $STAGE scripts added by next ($(date '+%Y-%m-%d %H:%M'))" >>"$DIR/.deps"
    echo "$DIR" >"$WS/tmp/.deps_last"
    next_steps "$DIR" "$STAGE"
    ;;
status)
    [ ${#POS[@]} -eq 0 ] || die "usage: status [--dir D]"
    find_tree
    echo "${DIR#"$CWD"/} ($(deps_value flow), variant $(deps_value variant))"
    echo "source tree: $(deps_value tree)"
    sed -n 's/^\(stage\|ran\) /  \1 /p' "$DIR/.deps"
    if ! cmp -s "$DIR/_main/config.mk" "$DIR/.config.mk.installed"; then
        echo "  config.mk edited:"
        { diff "$DIR/.config.mk.installed" "$DIR/_main/config.mk" || true; } | sed -n 's/^> /    /p'
    fi
    if grep -q '^ran ' "$DIR/.deps" || ! cmp -s "$DIR/_main/config.mk" "$DIR/.config.mk.installed"; then
        echo "A number from this tree carries the caveat: from a _deps lane, not a clean build."
    fi
    ;;
archive)
    flow_and_stage
    [ ${#POS[@]} -eq 1 ] || die "usage: archive <flow> <stage> <file.tar.gz>"
    OUT="$(abspath "${POS[0]}")"
    TARGET="$(stage_target "$FLOW" "$STAGE" "$VARIANT")"
    bz build ${DEPS_BUILD_OPTS:-} --output_groups=deps "$TARGET" >&2 || die "bazelisk build --output_groups=deps $TARGET failed"
    TAR="$(bz cquery --output=files --output_groups=deps "$TARGET" 2>/dev/null | grep '\.tar\.gz$' || true)"
    [ -n "$TAR" ] || die "$TARGET has no deps archive (is it an ORFS stage target?)"
    cp -f "$(bz info execution_root 2>/dev/null)/$TAR" "$OUT"
    echo "Archived to ${OUT#"$CWD"/}"
    ;;
-h | --help | help) usage 0 ;;
*) die "unknown command '$CMD': start, next, status or archive" ;;
esac
