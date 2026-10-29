# A macro's abstract with exact obstructions: write_abstract_lef without
# -bloat_occupied_layers obstructs only what the macro's cells and wires
# occupy, so a parent macro's notch stays free for the macros that
# abut it. The timing model as ORFS writes it.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 5_1_grt.odb 5_1_grt.sdc
# The block's routing obstructions, a parent's over its notch
# (io_notch.tcl), kept the macro's own router out; they are nothing the
# macro occupies, and the level above routes there.
foreach obs [[ord::get_db_block] getObstructions] {
  odb::dbObstruction_destroy $obs
}
# A supply net's straps on a layer it has pins on are those pins
# (pdn_macro.tcl's M8): stated once, as pins. As obstructions too they
# would, being on the layer under the level above's top routing layer,
# block that layer over the whole macro for its global router (grt
# blocks the top layer wherever a macro obstructs the one below).
foreach net [[ord::get_db_block] getNets] {
  if { ![$net isSpecial] } { continue }
  set pin_layers {}
  foreach bt [$net getBTerms] {
    foreach bp [$bt getBPins] {
      foreach box [$bp getBoxes] { lappend pin_layers [[$box getTechLayer] getName] }
    }
  }
  foreach sw [$net getSWires] {
    foreach box [$sw getWires] {
      if { [$box isVia] } { continue }
      if { [[$box getTechLayer] getName] in $pin_layers } { odb::dbSBox_destroy $box }
    }
  }
}
# LEF_OUT and LIB_OUT each optional: a parent macro's top level reads
# only the LEF (it dissolves the parent at floorplan), and the timing
# model, an hour serial on XSTile's parent, is left off its path.
if { [info exists ::env(LEF_OUT)] } {
  write_abstract_lef $::env(LEF_OUT)
}
if { [info exists ::env(LIB_OUT)] } {
  set_propagated_clock [all_clocks]
  estimate_parasitics -global_routing
  write_timing_model $::env(LIB_OUT)
}
