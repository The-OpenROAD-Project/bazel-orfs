# Regression test for the retime-select expansion in synth.tcl.
#
# Bug: `select $::env(SYNTH_RETIME_MODULES)` passes the whole space-separated
# list as ONE Tcl argument, so `select "Foo* Bar*"` matches nothing and retime
# silently becomes a no-op. The fix is `select {*}$::env(SYNTH_RETIME_MODULES)`
# so each pattern arrives as its own argument.
#
# This test exercises both the broken and fixed forms in one yosys session and
# asserts the resulting selection sizes.

# Path to the Verilog fixture is passed via env var by the test harness.
yosys read_verilog $::env(TEST_VERILOG)

yosys select -assert-mod-count 4 *

# Space-separated list of name-mangled globs plus the top module — the shape
# of value a downstream synthesis flow would pass via SYNTH_RETIME_MODULES.
set ::env(SYNTH_RETIME_MODULES) "FooKept* BarKept* Top"

# Broken form (pre-fix): Tcl `$var` substitution passes the whole string as a
# single arg, which matches no module, so the selection must be empty.
yosys select $::env(SYNTH_RETIME_MODULES)
yosys select -assert-none %
yosys select -clear

# Fixed form: `{*}` list-expands the env var so each pattern arrives as its
# own `select` arg, matching all three named modules (and no others).
yosys select {*}$::env(SYNTH_RETIME_MODULES)
yosys select -assert-mod-count 3 %
