# A part's pieces for the stitched timing of a parent and its blocks
# (headroom_flat.tcl, private/headroom.bzl; XiangShan's sta_flat.tcl reads
# its own copy of this file, kept apart so its cached results stay keyed): its
# netlist, its global route's parasitics, its SDC, and the liberty files its
# own timing reads, so the parent can be timed with every block's real cells
# instead of the block's abstract. The netlist is written as the flow reads
# the design, hierarchically, so its names are the SPEF's: read flat, a name
# holding the divider is escaped in one and not the other, and every SPEF
# net becomes a slow, sometimes failing, lookup.
source $::env(SCRIPTS_DIR)/load.tcl
# PART_STAGE reads a stage before global route: placement parasitics at
# place and cts; at floorplan, nothing is placed and the SPEF is empty,
# for a zero-wire read of the logic alone.
set part_stage [expr { [info exists ::env(PART_STAGE)] ? $::env(PART_STAGE) : "grt" }]
set part_files [dict create grt 5_1_grt cts 4_cts place 3_place floorplan 2_floorplan]
if { ![dict exists $part_files $part_stage] } { error "PART_STAGE is grt, cts, place or floorplan, not $part_stage" }
set part_base [dict get $part_files $part_stage]
load_design $part_base.odb $part_base.sdc
# A block keeps its interface logic only (STA_ILM=1): the cells from its data
# inputs to the first flops and from the last flops to its outputs, every load
# of a net those cells drive (the wire's load stays whole), and the clock tree
# of the flops it keeps. A path that crosses the block's boundary times as in
# the whole block; a path inside it is the block's own KPI.
if { [env_var_equals STA_ILM 1] } {
  set cells [concat [get_fanout -from [all_inputs -no_clocks] -flat -only_cells] \
    [get_fanin -to [all_outputs] -flat -only_cells]]
  set ckpins [get_pins -quiet -of_objects $cells -filter "is_register_clock == 1"]
  # the clock trees, walked back in the database from each kept clock pin:
  # a register's clock pin is a timing endpoint, so get_fanin stops there.
  # Each step goes to the net's driver and on through its clock input (A of
  # a buffer or inverter, CLK of a clock gate), never into a gate's enable.
  set block [ord::get_db_block]
  set todo {}
  set missing 0
  foreach pin $ckpins {
    set it [sta::sta_to_db_pin $pin]
    if { $it eq "NULL" } { incr missing } else { lappend todo $it }
  }
  set tree [dict create]
  while { [llength $todo] } {
    set iterm [lindex $todo end]
    set todo [lrange $todo 0 end-1]
    set net [$iterm getNet]
    if { $net eq "NULL" } { continue }
    foreach driver [$net getITerms] {
      if { ![$driver isOutputSignal] } { continue }
      set inst [$driver getInst]
      if { [dict exists $tree [$inst getName]] } { continue }
      dict set tree [$inst getName] 1
      foreach in [$inst getITerms] {
        if { [lsearch -exact {A CLK} [[$in getMTerm] getName]] >= 0 } { lappend todo $in }
      }
    }
  }
  puts "sta_part: [llength $ckpins] register clock pins ($missing not found in the database), [dict size $tree] cells on their clock trees"
  set cells [concat $cells [get_cells -quiet [dict keys $tree]]]
  set loads [get_cells -quiet -of_objects [get_pins -quiet -filter "direction == input" \
    -of_objects [get_nets -quiet -of_objects [get_pins -quiet -of_objects $cells \
      -filter "direction == output"]]]]
  set keep [dict create]
  foreach c [concat $cells $loads] { dict set keep [get_full_name $c] 1 }
  set gone 0
  foreach inst [[ord::get_db_block] getInsts] {
    if { ![dict exists $keep [$inst getName]] } {
      odb::dbInst_destroy $inst
      incr gone
    }
  }
  # and the wires left with one end or none: no path runs on them, and the
  # SPEF would carry them all
  set nets 0
  foreach net [[ord::get_db_block] getNets] {
    if { [llength [$net getITerms]] + [llength [$net getBTerms]] < 2 } {
      odb::dbNet_destroy $net
      incr nets
    }
  }
  puts "sta_part: interface logic model keeps [dict size $keep] cells, removes $gone and $nets nets"
}
if { $part_stage eq "grt" } {
  estimate_parasitics -global_routing -spef_file $::env(PART_SPEF)
} elseif { $part_stage eq "floorplan" } {
  close [open $::env(PART_SPEF) w]
} else {
  estimate_parasitics -placement -spef_file $::env(PART_SPEF)
}
write_verilog $::env(PART_V)
file copy -force $::env(RESULTS_DIR)/$part_base.sdc $::env(PART_SDC)
set libs $::env(LIB_FILES)
if { [env_var_equals AUTO_MEMORIES 1] } {
  foreach f [glob -nocomplain $::env(RESULTS_DIR)/memories/*.lib] {
    if { ![string match *_pre_layout.lib $f] } { lappend libs $f }
  }
}
exec -ignorestderr tar -chf $::env(PART_LIBS) --transform {s,.*/,,} {*}$libs
