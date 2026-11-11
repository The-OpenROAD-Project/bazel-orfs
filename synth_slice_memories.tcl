# ORFS's extract_memories.tcl over one Verilog slice (verilog_slice.py):
# the slice's module is the top, its kept children's stubs are black
# boxes, and the netlist JSON goes to MODULE_MEMORIES_JSON for
# slice_memories.py.
#
# Environment:
#   MODULE_VERILOG_SLICE  - the module's slice
#   MODULE_TARGET_NAME    - the kept module
#   MODULE_BLACKBOXES     - the other kept modules
#   MODULE_MEMORIES_JSON  - where the netlist JSON goes

set slice $::env(MODULE_VERILOG_SLICE)
set blackboxes [expr { [info exists ::env(MODULE_BLACKBOXES)] ? $::env(MODULE_BLACKBOXES) : {} }]

set stubs {}
set fp [open $slice r]
while { [gets $fp line] >= 0 } {
  if { [regexp {^// verilog_slice: (\S+) \S+$} $line - def] } {
    if { [lsearch -exact $blackboxes $def] >= 0 } {
      lappend stubs $def
    }
  }
}
close $fp

set existing [expr { [info exists ::env(SYNTH_BLACKBOXES)] ? $::env(SYNTH_BLACKBOXES) : {} }]
set ::env(SYNTH_BLACKBOXES) [concat $existing $stubs]
set ::env(DESIGN_NAME) $::env(MODULE_TARGET_NAME)
set ::env(VERILOG_FILES) $slice
# extract_memories.tcl writes RESULTS_DIR/memories_inferred.json and
# reads nothing else there.
set ::env(RESULTS_DIR) [file dirname $::env(MODULE_MEMORIES_JSON)]

source $::env(SCRIPTS_DIR)/memories/extract_memories.tcl
