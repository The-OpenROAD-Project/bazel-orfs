# The worst setup paths of a stage checkpoint, each pin with its cell's
# master, placement status and dont_touch: which cells of a path through a
# dissolved register file the resizer was not allowed to touch. Also the
# failing endpoints counted by where they are (u_rf/ or riscv.dp/ cells of
# the array, or elsewhere). Text, a few kilobytes.
source $::env(SCRIPTS_DIR)/util.tcl
source $::env(SCRIPTS_DIR)/read_liberty.tcl
read_db $::env(ODB_FILE)
read_sdc $::env(SDC_FILE)
source $::env(PLATFORM_DIR)/setRC.tcl
set_propagated_clock [all_clocks]
estimate_parasitics -placement
set out [open $::env(OUTPUT) w]
set block [ord::get_db_block]
set paths [find_timing_paths -path_delay max -group_path_count 5 -endpoint_path_count 1 -sort_by_slack]
foreach path $paths {
  puts $out "== slack [get_property $path slack] ps, endpoint [get_full_name [get_property $path endpoint]]"
  foreach pt [get_property $path points] {
    set pin [get_property $pt pin]
    set name [get_full_name $pin]
    set arr [get_property $pt arrival]
    set info ""
    set inst_name [file dirname [string map {/ /} $name]]
    if { [get_property $pin is_port] } {
      set info "port"
    } else {
      set inst [$block findInst [get_full_name [get_cells -of_objects $pin]]]
      if { $inst ne "NULL" } {
        set info "[[$inst getMaster] getName] [$inst getPlacementStatus][expr {[$inst isDoNotTouch] ? " dont_touch" : ""}]"
      }
    }
    puts $out [format "  %8.1f  %-60s %s" $arr $name $info]
  }
}
set rf 0
set other 0
foreach path [find_timing_paths -path_delay max -group_path_count 100000 -endpoint_path_count 1 -slack_max 0] {
  set ep [get_full_name [get_property $path endpoint]]
  if { [string match *_ff/D $ep] } { incr rf } else { incr other }
}
puts $out "failing endpoints: $rf on array flops (*_ff/D), $other elsewhere"
close $out
