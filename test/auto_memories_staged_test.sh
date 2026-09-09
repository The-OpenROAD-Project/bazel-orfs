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

exit $status
