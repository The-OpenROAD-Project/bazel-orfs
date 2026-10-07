# The worst register-to-register paths of a stage, for the ladder's
# debug loop: per path its slack, start and end, and the driving pins
# with arrival and cell, so a path through the generated register file
# (its cells are named w<word>_b<bit>_..., w<word>_rsel..., ...) can be
# told from one through the rest of the design. Global-route parasitics
# when the ODB has the routes, else placement's; the output says which.
source $::env(STAGE_SRC_TCL)
source $::env(SCRIPTS_DIR)/load.tcl
load_design [file tail $stage_src_staged] [file rootname [file tail $stage_src_staged]].sdc
set rc global_routing
if { [catch { estimate_parasitics -global_routing }] } {
  set rc placement
  estimate_parasitics -placement
}
set out [open $::env(OUTPUT_TXT) w]
set clk [lindex [all_clocks] 0]
puts $out "parasitics $rc, clock [get_name $clk] period [get_property $clk period]"
# find_clk_min_period's second argument is include_port_paths.
puts $out "min period, all paths: [sta::find_clk_min_period $clk 1]"
puts $out "min period, register to register: [sta::find_clk_min_period $clk 0]"
set regs [all_registers]
set paths [find_timing_paths -path_delay max -from $regs -to $regs \
  -group_path_count 5 -endpoint_path_count 1 -sort_by_slack]
foreach t $paths {
  puts $out "\nslack [get_property $t slack]\
 from [get_full_name [get_property $t startpoint]]\
 to [get_full_name [get_property $t endpoint]]"
  foreach pt [get_property $t points] {
    set p [get_property $pt pin]
    if { [get_property $p is_port] } {
      continue
    }
    if { [get_property $p direction] ne "output" } {
      continue
    }
    set c [get_cells -of_objects $p]
    puts $out [format "  %8.1f  %-12s %s" [get_property $pt arrival] \
      [get_property $c ref_name] [get_full_name $p]]
  }
}
close $out
