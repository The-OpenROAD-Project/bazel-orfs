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
#   MODULE_MEMORIES_DIR            - with AUTO_MEMORIES, the directory whose
#                                    memories/ holds the slice's memories

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

# AUTO_MEMORIES: the slice's own memories (slice_memories.py), where
# read_design_sources looks for them: AUTO_MEMORIES_DIR, which synthesis
# sets to the whole design's memories.
if { [info exists ::env(MODULE_MEMORIES_DIR)] } {
  set ::env(RESULTS_DIR) $::env(MODULE_MEMORIES_DIR)
  set ::env(AUTO_MEMORIES_DIR) $::env(MODULE_MEMORIES_DIR)/memories
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
# SYNTH_CANONICALIZE_TCL runs here as it runs on the whole design, with
# the slice as the design and its top as DESIGN_NAME. A script that
# needs a module the slice does not hold fails here; the slice's top and
# stubs, which the partitions are joined by, must still be there after
# it.
if { [env_var_exists_and_non_empty SYNTH_CANONICALIZE_TCL] } {
  set ::env(DESIGN_NAME) [dict get $elaborated $target]
  set ::env(SYNTH_CANONICALIZE_SLICE) $target
  if { [catch { source $::env(SYNTH_CANONICALIZE_TCL) } err] } {
    error "synth_canonicalize_slice: SYNTH_CANONICALIZE_TCL failed on the slice\
      of $target: $err\nA script that needs the whole design cannot run on a\
      slice; set verilog_slices = False"
  }
  foreach m [concat [list $target] $stubs] {
    set found [yosys tee -q -s result.string select -list-mod "=$m" "=$m\\\$*"]
    if { [regexp -line {^(?!Warning: )\S} $found] == 0 } {
      error "synth_canonicalize_slice: SYNTH_CANONICALIZE_TCL removed $m from\
        the slice of $target, which joins it to its partition; set\
        verilog_slices = False"
    }
  }
  set ::env(DESIGN_NAME) $target
}
setattr -unset src *
setattr -mod -unset src *
write_rtlil $checkpoint

design -reset
set ::env(SYNTH_CHECKPOINT) $checkpoint
set ::env(MODULE_BLACKBOXES) $stubs
source $module_tcl
