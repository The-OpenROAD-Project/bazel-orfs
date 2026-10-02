# The multiplier example's numbers for one design (a macro or a parent)
# after CTS, placement parasitics, as JSON: the period (the clock minus
# the worst setup slack), the instance count, and, where the parent
# holds peeled flops (cells of a u_mac instance outside the macros), the
# stage into them and the stage out of them.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 4_cts.odb 4_cts.sdc
estimate_parasitics -placement

set period [get_property [lindex [all_clocks] 0] period]
set pe [find_timing_paths -path_delay max -group_path_count 1]
set slack [get_property $pe slack]

proc is_peeled { pin } {
  set cell [get_cells -quiet -of_objects $pin]
  if { [llength $cell] == 0 } { return 0 }
  return [expr { [string match DFF* [get_property $cell ref_name]]
    && [string match *u_mac* [get_full_name $cell]] }]
}
set in_stage null
set out_stage null
foreach p [find_timing_paths -path_delay max -group_path_count 2000 -endpoint_path_count 1] {
  set d [expr { $period - [get_property $p slack] }]
  if { [is_peeled [get_property $p endpoint]] && ($in_stage eq "null" || $d > $in_stage) } {
    set in_stage $d
  }
  if { [is_peeled [get_property $p startpoint]] && ($out_stage eq "null" || $d > $out_stage) } {
    set out_stage $d
  }
}
foreach v {in_stage out_stage} {
  if { [set $v] ne "null" } { set $v [format %.1f [set $v]] }
}
set peeled 0
foreach inst [[ord::get_db_block] getInsts] {
  set m [$inst getMaster]
  if { ![$m isBlock] && [$m isSequential] && [string match *u_mac* [$inst getName]] } { incr peeled }
}
set out [open $::env(OUTPUT_JSON) w]
puts $out "{"
puts $out "  \"period_ps\": [format %.1f [expr { $period - $slack }]],"
puts $out "  \"startpoint\": \"[get_full_name [get_property $pe startpoint]]\","
puts $out "  \"endpoint\": \"[get_full_name [get_property $pe endpoint]]\","
puts $out "  \"instances\": [llength [[ord::get_db_block] getInsts]],"
puts $out "  \"peeled_flops\": $peeled,"
puts $out "  \"in_stage_ps\": $in_stage,"
puts $out "  \"out_stage_ps\": $out_stage"
puts $out "}"
close $out
