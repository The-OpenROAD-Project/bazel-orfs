#!/bin/bash
# Opens a .blend file in the hermetic Blender extracted by @blender//.
# Invoked via `bazel run` on the sh_binary wrapper emitted by
# orfs_blender(). Both arguments are rootpath-relative:
#   $1 — the .blend file (lives under _main/ in the runfiles tree)
#   $2 — the Blender ELF (@blender//:blender — passed as
#        external/+_repo_rules+blender/blender or similar, lives at the
#        external-repo dir in the runfiles tree)
# The LD_LIBRARY_PATH shim is inlined here rather than going through the
# //tools/blender:blender sh_binary wrapper because nested sh_binaries
# lose their runfiles context when exec'd by `bazel run`.
set -euo pipefail

# Resolve a Bazel rootpath into a real filesystem path inside the
# runfiles tree. Tries, in order:
#   - <runfiles>/<rel with `external/` stripped>   (external repo)
#   - <runfiles>/_main/<rel>                       (main workspace)
# Falls back to <rel> verbatim so the script is debuggable outside
# `bazel run`.
resolve() {
    local rel="$1"
    local stripped="${rel#external/}"
    local roots=()
    if [[ -n "${RUNFILES_DIR:-}" && -d "${RUNFILES_DIR}" ]]; then
        roots+=("${RUNFILES_DIR}")
    fi
    if [[ -d "$0.runfiles" ]]; then
        roots+=("$0.runfiles")
    fi
    for r in "${roots[@]}"; do
        if [[ -f "${r}/${stripped}" ]]; then
            printf '%s\n' "${r}/${stripped}"
            return
        fi
        if [[ -f "${r}/_main/${rel}" ]]; then
            printf '%s\n' "${r}/_main/${rel}"
            return
        fi
    done
    printf '%s\n' "${rel}"
}

blend="$(resolve "$1")"
blender="$(resolve "$2")"
shift 2

if [[ ! -x "${blender}" ]]; then
    echo "open_blend.sh: blender ELF not executable at ${blender}" >&2
    exit 1
fi

export LD_LIBRARY_PATH="$(dirname "${blender}")/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
# Extra args from `bazel run -- ...` go BEFORE the .blend so flags like
# --background can take effect on the load.
exec "${blender}" "$@" "${blend}"
