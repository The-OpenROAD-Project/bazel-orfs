# Regression test for the typo-check in SYNTH_KEEP_MODULES handling
# (synth.tcl and synth_keep.tcl).
#
# The pre-fix code used `select "${module}" "${module}\\$*"` which silently
# accepted typos: a misspelled module name matched nothing and the run
# continued without keep_hierarchy applied. The fix walks the env list via
# `rtlil::set_attr -mod $module keep_hierarchy 1`, accumulating modules that
# the call rejects, and `error`s out at the end if any remain. In partition
# synthesis (SYNTH_BLACKBOXES set) only one module's subhierarchy is present,
# so the strict check is skipped.
#
# This test reproduces the same `catch {rtlil::set_attr ...}` logic on a
# 4-module fixture and asserts:
#
#   case 1  happy path — all named modules exist, no missing accumulated.
#   case 2  typo — Misspelled module triggers the missing-list.
#   case 3  partition-mode equivalent — strict=0, missing accumulated but
#           caller would not error (we just assert the gate value).

yosys read_verilog $::env(TEST_VERILOG)

# Helper mirroring the synth.tcl / synth_keep.tcl logic. Returns the missing
# list as a Tcl list so the test can inspect it.
proc collect_missing {modules} {
  set missing [list]
  foreach module $modules {
    if { [catch {rtlil::set_attr -mod $module keep_hierarchy 1}] } {
      lappend missing $module
    }
  }
  return $missing
}

# --- case 1: happy path ---
set missing [collect_missing {FooKept$top.foo BarKept$top.bar Top}]
if { [llength $missing] != 0 } {
  error "case 1 FAIL: expected no missing, got: $missing"
}

# --- case 2: typo path ---
set missing [collect_missing {FooKept$top.foo Typo$top.nope Top}]
if { [llength $missing] != 1 || [lindex $missing 0] ne {Typo$top.nope} } {
  error "case 2 FAIL: expected single missing {Typo\$top.nope}, got: $missing"
}

# --- case 3: partition-mode (strict=0): missing is still reported by the
# helper, but synth.tcl's caller decides to ignore it. The unit guards the
# helper's behavior; the caller-side `&& $strict` guard lives in synth.tcl
# and is grep-checked separately in the .sh wrapper.
set missing [collect_missing {NotPresent Top}]
if { [llength $missing] != 1 || [lindex $missing 0] ne {NotPresent} } {
  error "case 3 FAIL: expected single missing {NotPresent}, got: $missing"
}

puts "PASS: synth_keep_modules_check_test (all cases)"
