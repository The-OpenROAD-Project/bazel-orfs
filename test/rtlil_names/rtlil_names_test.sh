#!/usr/bin/env bash
# Pin the RTLIL name-mangling rules synth_partition.sh depends on.
#
# yosys spells a module three ways and a design can contain all three:
#
#   \Foo                  unparameterized
#   $paramod\Foo\W=1      parameterized, named form
#   $paramod$<hash>\Foo   parameterized, hashed form
#
# plus `\Foo$Top.path.to.inst` for a uniquified instance. The design's
# own name is the component after the first backslash in every form.
#
# This is pure string logic with no synthesis in it, and it was wrong in
# a way that only appeared on designs which parameterize their
# submodules: the old code matched `^module \\` alone, found none of the
# parameterized spellings, and SYNTH_KEEP_MODULES then rejected names
# that were present in the design under a mangled form.
#
# cases.tsv carries the spellings as data rather than as shell literals,
# because escaping backslash-and-dollar names through several layers of
# quoting is how a test ends up asserting something other than what it
# reads.
set -euo pipefail

cases=${1:?cases.tsv}
script=${2:?synth_partition.sh}

SYNTH_PARTITION_LIB=1 . "$script"

fails=0
total=0

# Half one: demangling.
while IFS="$(printf '\t')" read -r name want; do
  [ -n "$name" ] || continue
  total=$((total + 1))
  got=$(rtlil_base_name "$name")
  if [ "$got" != "$want" ]; then
    printf 'FAIL rtlil_base_name %s\n  got  %s\n  want %s\n' "$name" "$got" "$want" >&2
    fails=$((fails + 1))
  fi
done < "$cases"

# Half two: resolution, which is what the caller actually asks for. A
# design name has to find its module whichever spelling that module
# happens to carry.
# One spelling per module, as a real checkpoint has. Reusing the
# demangling table here would put two spellings of serv_alu in the same
# design, and "which one wins" would be the assertion rather than
# "does it resolve at all" -- a distinction this test got wrong once
# already.
modules=$(mktemp)
cat > "$modules" <<'MODULES'
\cmj_imem
$paramod\serv_alu\W=1
$paramod$6d68\serv_rf_ram
\ifu_bp_ctl$swerv_wrapper.swerv.ifu.bp
MODULES

resolves() {
  total=$((total + 1))
  got=$(rtlil_module_for "$1" "$modules")
  if [ "$got" != "$2" ]; then
    printf 'FAIL rtlil_module_for %s\n  got  %s\n  want %s\n' "$1" "$got" "$2" >&2
    fails=$((fails + 1))
  fi
}

resolves serv_alu '$paramod\serv_alu\W=1'
resolves serv_rf_ram '$paramod$6d68\serv_rf_ram'
resolves cmj_imem '\cmj_imem'
# A name present only as a uniquified instance resolves to it, which is
# the second pass in rtlil_module_for.
resolves ifu_bp_ctl '\ifu_bp_ctl$swerv_wrapper.swerv.ifu.bp'
# And a name that is genuinely absent resolves to nothing, so the caller
# can report it rather than blackboxing a module that does not exist.
resolves definitely_not_here ''

rm -f "$modules"

if [ "$fails" -ne 0 ]; then
  printf '%d of %d checks failed\n' "$fails" "$total" >&2
  exit 1
fi
printf 'rtlil name mangling: %d checks OK\n' "$total"
