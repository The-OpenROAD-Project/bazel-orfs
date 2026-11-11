# Canonicalize one kept module from its Verilog slice (verilog_slice.py),
# then cut its partition's RTLIL from that with synth_canonicalize_module.tcl.
#
# The slice holds the module, the modules under it and a port-only stub
# of each kept module under it, so this reads the sources the way ORFS's
# synth_canonicalize.tcl reads the whole design, with the module as the
# top and the stubs as black boxes, and hands the result on as the
# checkpoint the per-module step otherwise takes from the global
# canonicalize.
#
# Environment, beyond synth_canonicalize_module.tcl's:
#   MODULE_VERILOG_SLICE           - the module's slice
#   MODULE_SLICE_CHECKPOINT        - where the slice's canonicalized RTLIL goes
#   SYNTH_CANONICALIZE_MODULE_TCL  - synth_canonicalize_module.tcl

set slice $::env(MODULE_VERILOG_SLICE)
set target $::env(MODULE_TARGET_NAME)
set checkpoint $::env(MODULE_SLICE_CHECKPOINT)
set blackboxes [expr { [info exists ::env(MODULE_BLACKBOXES)] ? $::env(MODULE_BLACKBOXES) : {} }]
set module_tcl $::env(SYNTH_CANONICALIZE_MODULE_TCL)

source $::env(SCRIPTS_DIR)/synth_preamble.tcl

set slice_modules {}
set elaborated {}
set fp [open $slice r]
while { [gets $fp line] >= 0 } {
  if { [regexp {^// verilog_slice: (\S+) (\S+)$} $line - def name] } {
    dict set elaborated $def $name
  } elseif {
    [regexp {^(?:\(\*.*\*\)\s*)?(?:macro)?module\s+(?:(?:static|automatic)\s+)?(\\\S+|[A-Za-z_][A-Za-z0-9_$]*)} \
      $line - name]
  } {
    lappend slice_modules [regsub {^\\} $name {}]
  }
}
close $fp

# The kept modules in the slice are stubs: black boxes, as the global
# canonicalize's slice of this module has them.
set stubs {}
foreach m $blackboxes {
  if { [lsearch -exact $slice_modules $m] >= 0 } {
    lappend stubs $m
  }
}
set ::env(SYNTH_BLACKBOXES) [concat [env_var_or_empty SYNTH_BLACKBOXES] $stubs]
set ::env(DESIGN_NAME) $target
set ::env(VERILOG_FILES) $slice

# AUTO_MEMORIES lists the memories of the whole design; a slice holds
# only those under its module, and the check that each is a black box
# holds for those.
rename auto_memories_check_blackboxed design_auto_memories_check_blackboxed
proc auto_memories_check_blackboxed { names } {
  set present {}
  foreach m [split [tee -q -s result.string select -list-mod =*] "\n"] {
    lappend present [regsub {^\\} [string trim $m] {}]
  }
  design_auto_memories_check_blackboxed \
    [lmap m $names { expr { [lsearch -exact $present $m] >= 0 ? $m : [continue] } }]
}

read_design_sources

hierarchy -check -top $target
opt_clean -purge

# The slice's top and stubs take the names the whole design's
# elaboration gives them, which its parent partitions instantiate.
dict for {def name} $elaborated {
  if { $def ne $name } {
    yosys rename $def $name
    chtype -map $def $name
  }
}
setattr -unset src *
setattr -mod -unset src *
write_rtlil $checkpoint

design -reset
set ::env(SYNTH_CHECKPOINT) $checkpoint
set ::env(MODULE_BLACKBOXES) $stubs
source $module_tcl
