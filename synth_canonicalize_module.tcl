# Per-module re-canonicalization for parallel partition synthesis.
#
# Reads the global canonicalize/keep RTLIL, prunes to the single
# hierarchy rooted at the target module, blackboxes the kept-module
# children to preserve partition boundaries, and writes a self-contained
# per-module RTLIL slice. The resulting file is byte-stable under
# upstream Chisel/Verilog edits that don't touch the target module's
# body, restoring incremental synth cache hits for the partition action
# that consumes it.
#
# Environment:
#   SYNTH_CHECKPOINT       - global RTLIL (canonicalize.rtlil or keep.rtlil)
#   MODULE_TARGET_NAME     - bare name (from SYNTH_KEEP_MODULES) of the target module
#   MODULE_BLACKBOXES      - space-separated bare names to blackbox
#   MODULE_RTLIL_OUT       - output path for the per-module RTLIL slice
#   MODULE_NAME_OUT        - sidecar that receives the canonical name of the target
#
# We do NOT override DESIGN_NAME because ORFS's Makefile derives
# RESULTS_DIR/LOG_DIR/etc. from it; the surrounding macro's DESIGN_NAME
# stays in effect so paths resolve correctly. The actual yosys top after
# hierarchy -top is the resolved canonical form of MODULE_TARGET_NAME,
# written to MODULE_NAME_OUT for the partition action to pass as
# DESIGN_NAME to synth.tcl downstream.

# Deliberately do NOT source synth_preamble.tcl: that script sets up ABC,
# lib files, SDC clock period, and yosys-slang plugin — none of which this
# pure read_rtlil → blackbox → write_rtlil step needs, and several of which
# expect inputs (clock_period.txt, .lib files) that aren't materialised
# until the surrounding macro's actual synth runs.
#
# `yosys -import` makes the yosys built-in commands callable without the
# `yosys::` namespace prefix; normally synth_preamble.tcl does it for us.
yosys -import

proc env_var_set_nonempty {name} {
    return [expr {[info exists ::env($name)] && $::env($name) ne ""}]
}

# Resolve a bare module name (e.g. "Foo") to its canonical form
# (e.g. "Foo$Top.path.to.inst") by scanning
# the checkpoint RTLIL for `module \X` lines. Same algorithm as
# synth_partition.sh, kept here so this script is self-contained.
set rtlil_modules [list]
set fp [open $::env(SYNTH_CHECKPOINT) r]
while {[gets $fp line] >= 0} {
    if {[regexp {^module \\(\S+)} $line _ name]} {
        lappend rtlil_modules $name
    }
}
close $fp

proc resolve_canonical {bare modules} {
    foreach m $modules {
        if {$m eq $bare} { return $m }
    }
    foreach m $modules {
        if {[string match "${bare}\$*" $m]} { return $m }
    }
    error "synth_canonicalize_module: '$bare' not present in checkpoint"
}

set bare_design $::env(MODULE_TARGET_NAME)
set canonical_design [resolve_canonical $bare_design $rtlil_modules]

read_rtlil $::env(SYNTH_CHECKPOINT)

# Step 1: prune to the target's hierarchy.
#
# `hierarchy -check -top X` deletes every non-blackbox module not in X's
# call tree (same mechanism ORFS uses in synth_canonicalize.tcl to scope
# the design to DESIGN_NAME). Library blackboxes (stdcells, SRAMs,
# SHARED_LOGIC_MACRO .lib stubs) survive — that's intentional, downstream
# synth maps cells to them.
#
# This runs BEFORE blackboxing kept modules so the kept-module bodies
# outside X's tree are pruned in this single step. If we blackboxed first
# they would become library blackboxes and survive the hierarchy pass
# (the contamination that motivated the earlier "selective delete" hack).
hierarchy -check -top $canonical_design

# Step 2: blackbox kept-module children that survive inside X's tree, so
# the partition boundary is preserved (each kept module is its own synth
# partition; the slice shouldn't pull in their bodies). `catch` silently
# skips names that aren't in X's call tree — they were pruned in step 1.
if { [env_var_set_nonempty MODULE_BLACKBOXES] } {
    foreach m $::env(MODULE_BLACKBOXES) {
        set canonical [resolve_canonical $m $rtlil_modules]
        catch { blackbox $canonical }
    }
}

opt_clean -purge

# Step 3: strip volatile attributes that vary across runs but don't
# affect downstream synthesis correctness:
#
#  - `src`: file path + line number, shifts when upstream files edit.
#    Stripped by ORFS canonicalize too when SYNTH_REPEATABLE_BUILD=1.
#  - `area` (module-level) + `capacitance` (wire-level): come from the
#    .lib characterisation of SHARED_LOGIC_MACRO blackboxes. The macro
#    PnR is non-deterministic at the picosecond / nanometre level, so
#    these values drift between runs even when the macro's RTL is
#    byte-identical. Downstream synth.tcl re-reads the .lib via
#    LIB_FILES, so dropping the embedded values from the .rtlil is safe.
#
# SYNTH_REPEATABLE_BUILD is forced to "1" by the parallel-synth Bazel
# action regardless of the user's variables.yaml default (which is 0),
# because byte-stability IS this action's reason for existing.
if { [env_var_set_nonempty SYNTH_REPEATABLE_BUILD] && $::env(SYNTH_REPEATABLE_BUILD) != "0" } {
    # The `=*` selection includes blackbox modules; default `*` skips
    # them, which is wrong here because the SHARED_LOGIC_MACRO .lib
    # stubs are
    # exactly the blackbox modules we need to scrub.
    setattr -unset src =*
    setattr -mod -unset src =*
    setattr -mod -unset area =*
    setattr -unset capacitance =*
}

# Persist the canonical name in a sidecar so synth_partition.sh can pass
# DESIGN_NAME=<canonical> to synth.tcl downstream. We deliberately do NOT
# rename the module to its bare name here: the downstream synth output
# (1_2_yosys.v) feeds OpenROAD, whose macro placement and parent-netlist
# references use canonical (slang-elaborated) names. Renaming would
# desync the netlist module names from the parent's instance references.
set fp [open $::env(MODULE_NAME_OUT) w]
puts $fp $canonical_design
close $fp

write_rtlil $::env(MODULE_RTLIL_OUT)
