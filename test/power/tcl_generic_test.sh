#!/bin/bash
# Fast guard: the power TCL files are intended to be design-agnostic.
# Catch slips where someone re-introduces module-name branching ("if
# this file looks like *_FooMacro* then read_spef -path ..."), a
# hardcoded SAIF_SCOPE default tied to a specific testbench wrapper, or
# any other named-design hook. The generalization story for any of
# those is the SPEF_PATHS_TCL env var and a mandatory SAIF_SCOPE.
set -euo pipefail

violations=0
for tcl in "$@"; do
    if grep -nE 'string match \*[A-Z][A-Za-z_]+[0-9]?\*' "$tcl" | grep -v -E 'string match \*\.(v|spef)' >&2; then
        echo "FAIL: $tcl branches on a module-name glob — use SPEF_PATHS_TCL hook instead" >&2
        violations=$((violations + 1))
    fi
    # No hardcoded fallback hierarchy in the TOP/<wrapper>/<DESIGN> shape.
    if grep -nE 'TOP/[A-Z][A-Za-z]+/' "$tcl" >&2; then
        echo "FAIL: $tcl carries a hardcoded SAIF_SCOPE hierarchy literal" >&2
        violations=$((violations + 1))
    fi
done

if [ "$violations" -gt 0 ]; then
    echo "FAIL: $violations design-specific hook(s) in power TCL files" >&2
    exit 1
fi
echo "PASS: tcl_generic_test"
