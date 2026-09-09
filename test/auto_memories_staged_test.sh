#!/bin/sh
# The AUTO_MEMORIES scripts flow/Makefile names must reach the sandbox.
#
# ORFS's AUTO_MEMORIES rules (flow/Makefile, guarded by
# `ifeq ($(AUTO_MEMORIES),1)`) name two scripts as prerequisites:
#
#   results/memories_inferred.json: ... $(SCRIPTS_DIR)/memories/extract_memories.tcl
#   do-auto-memories: ...           $(SCRIPTS_DIR)/memories/gen_memories.py
#
# Both live in flow/scripts/memories/, which no `scripts/*` glob reaches
# -- a glob wildcard does not cross a directory separator. When
# extract_memories.tcl was missing from the staged set, a design with
# AUTO_MEMORIES=1 (asap7/tinyRocket) failed canonicalization with
#   make: *** No rule to make target '.../memories/extract_memories.tcl'
# which reads as a Makefile bug rather than a packaging one.
#
# The ORFS-side unit tests in the same directory must stay out, or every
# stage sandbox carries test code it never runs.
#
# The generator then shells out to FakeRAM, which ORFS vendors at
# tools/FakeRAM2.0 since the standalone repository was archived. Two
# things have to hold there and neither is self-evident:
#
#   * the tree is reachable at all. ORFS's .bazelignore ignores tools/
#     wholesale, which bazel turns into --deleted_packages, so a BUILD
#     file under it defines no package until that entry is narrowed.
#
#   * run.py accepts --orfs_asap7_backend, the flag gen_memories.py
#     invokes it with. ORFS ships the patch that adds it but nothing
#     applied it to the vendored copy, so an unpatched tree looks
#     perfectly staged and fails only once a flow runs.
set -eu

# The test runs in runfiles/_main; @orfs files are a sibling subtree
# under the runfiles root, so search from there rather than from cwd.
# -L because bazel builds the runfiles tree out of symlinks.
root="${RUNFILES_DIR:-$(dirname "$(pwd)")}"

status=0

require() {
    if find -L "$root" -path "*/flow/scripts/memories/$1" -print 2>/dev/null | grep -q .; then
        echo "ok: flow/scripts/memories/$1 is staged"
    else
        echo "FAIL: flow/scripts/memories/$1 is NOT staged"
        status=1
    fi
}

refuse() {
    if find -L "$root" -path "*/flow/scripts/memories/$1" -print 2>/dev/null | grep -q .; then
        echo "FAIL: flow/scripts/memories/$1 is staged but is ORFS's own test code"
        status=1
    else
        echo "ok: flow/scripts/memories/$1 is excluded"
    fi
}

# Named directly by flow/Makefile's AUTO_MEMORIES rules.
require extract_memories.tcl
require gen_memories.py

# Imported by gen_memories.py, so they travel with it.
require detect.py
require idiomatic.py
require schema.py

# MAKEFILE_SHARED_EXCLUDE keeps these out.
refuse detect_test.py
refuse gen_memories_test.py
refuse idiomatic_test.py
refuse schema_test.py

# --- FakeRAM, the generator gen_memories.py shells out to ---

fakeram_run=$(find -L "$root" -path "*/tools/FakeRAM2.0/run.py" -print 2>/dev/null | head -1)
if [ -n "$fakeram_run" ]; then
    echo "ok: tools/FakeRAM2.0/run.py is staged"
    if grep -q -- "--orfs_asap7_backend" "$fakeram_run"; then
        echo "ok: run.py accepts --orfs_asap7_backend"
    else
        echo "FAIL: run.py does not accept --orfs_asap7_backend;" \
             "the ORFS ASAP7 backend patch did not reach the vendored copy"
        status=1
    fi
else
    echo "FAIL: tools/FakeRAM2.0/run.py is NOT staged"
    status=1
fi

# The backend module run.py imports when that flag is given.
if find -L "$root" -path "*/tools/FakeRAM2.0/orfs_asap7/generate.py" -print 2>/dev/null | grep -q .; then
    echo "ok: orfs_asap7/generate.py is staged"
else
    echo "FAIL: orfs_asap7/generate.py is NOT staged"
    status=1
fi

exit $status
