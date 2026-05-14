#!/bin/bash
# Hermetic Blender wrapper. Locates the Blender tree extracted by
# http_archive(name = "blender", ...), points LD_LIBRARY_PATH at its bundled
# lib/, and exec's the real binary. The Blender tarball is self-contained
# (no system libs assumed), but we set LD_LIBRARY_PATH explicitly so the
# launch is robust to hosts whose ld.so doesn't honour the binary's
# $ORIGIN-relative rpath — the same trick oss-cad-suite uses.
set -euo pipefail

# Locate the runfiles tree. Bazel sets RUNFILES_DIR or RUNFILES_MANIFEST_FILE;
# we cope with both, plus the legacy `$0.runfiles/` layout.
if [[ -n "${RUNFILES_DIR:-}" && -d "${RUNFILES_DIR}" ]]; then
    runfiles="${RUNFILES_DIR}"
elif [[ -d "${0}.runfiles" ]]; then
    runfiles="${0}.runfiles"
else
    echo "blender_wrapper.sh: cannot locate runfiles" >&2
    exit 1
fi

# The Blender repo's canonical name varies between Bazel versions:
#   bzlmod canonical:           +_repo_rules+blender
#   shorter canonical form:     blender+
#   bare repo name:             blender
# Try each candidate in turn before scanning runfiles.
blender_root=""
for cand in \
    "${runfiles}/+_repo_rules+blender" \
    "${runfiles}/blender+" \
    "${runfiles}/blender"; do
    if [[ -x "${cand}/blender" ]]; then
        blender_root="${cand}"
        break
    fi
done
if [[ -z "${blender_root}" ]]; then
    # Last resort: any sibling that contains an executable `blender`.
    for cand in "${runfiles}"/*; do
        if [[ -x "${cand}/blender" ]]; then
            blender_root="${cand}"
            break
        fi
    done
fi
if [[ -z "${blender_root}" ]]; then
    echo "blender_wrapper.sh: blender binary not found under ${runfiles}" >&2
    exit 1
fi

export LD_LIBRARY_PATH="${blender_root}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
exec "${blender_root}/blender" "$@"
