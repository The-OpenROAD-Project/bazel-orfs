# What the peel did to the parent, as JSON: the period (the clock minus
# the worst setup slack, placement parasitics, after CTS), the flops the
# parent placed itself, and where they sit on the line from Src's centre
# (0) to Dst's (1).
source $::env(SCRIPTS_DIR)/load.tcl
load_design 4_cts.odb 4_cts.sdc
estimate_parasitics -placement

set period [get_property [lindex [all_clocks] 0] period]
set pe [find_timing_paths -path_delay max -group_path_count 1]
set slack [get_property $pe slack]

# The two stages around the parent's own flops, from the worst paths of
# each endpoint: into a flop's D (from the core) and out of a flop (to
# Dst). A flop is a cell with a D pin outside the blocks; without one,
# "null". (all_registers crashed openroad with signal 11 on this
# hierarchical database, not isolated; the paths are classified here.)
proc is_parent_flop { pin } {
  set cell [get_cells -quiet -of_objects $pin]
  if { [llength $cell] == 0 } { return 0 }
  return [string match DFF* [get_property $cell ref_name]]
}
set in_stage null
set out_stage null
foreach p [find_timing_paths -path_delay max -group_path_count 1000 -endpoint_path_count 1] {
  set d [expr { $period - [get_property $p slack] }]
  if { [is_parent_flop [get_property $p endpoint]] && ($in_stage eq "null" || $d > $in_stage) } {
    set in_stage $d
  }
  if { [is_parent_flop [get_property $p startpoint]] && ($out_stage eq "null" || $d > $out_stage) } {
    set out_stage $d
  }
}
foreach v {in_stage out_stage} {
  if { [set $v] ne "null" } { set $v [format %.1f [set $v]] }
}

set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
proc centre { inst } {
  set b [$inst getBBox]
  return [list [expr { ([$b xMin] + [$b xMax]) / 2.0 }] [expr { ([$b yMin] + [$b yMax]) / 2.0 }]]
}
foreach inst [$block getInsts] {
  set m [[$inst getMaster] getName]
  if { $m in {Src Src_core} } { set src [centre $inst] }
  if { $m eq "Dst" } { set dst [centre $inst] }
}
lassign $src sx sy
lassign $dst dx dy
set len2 [expr { ($dx - $sx) ** 2 + ($dy - $sy) ** 2 }]
set ts {}
foreach inst [$block getInsts] {
  set m [$inst getMaster]
  if { [$m isBlock] || ![$m isSequential] } { continue }
  # clock gating and the like have no D; a peeled flop does
  if { [$inst findITerm D] eq "NULL" } { continue }
  lassign [centre $inst] x y
  lappend ts [expr { (($x - $sx) * ($dx - $sx) + ($y - $sy) * ($dy - $sy)) / $len2 }]
}
set n [llength $ts]
set mean 0
set lo 0
set hi 0
if { $n } {
  set sum 0
  foreach t $ts { set sum [expr { $sum + $t }] }
  set mean [expr { $sum / $n }]
  set lo [tcl::mathfunc::min {*}$ts]
  set hi [tcl::mathfunc::max {*}$ts]
}
set out [open $::env(OUTPUT_JSON) w]
puts $out "{"
puts $out "  \"clock_ps\": $period,"
puts $out "  \"period_ps\": [format %.1f [expr { $period - $slack }]],"
puts $out "  \"startpoint\": \"[get_full_name [get_property $pe startpoint]]\","
puts $out "  \"endpoint\": \"[get_full_name [get_property $pe endpoint]]\","
puts $out "  \"in_stage_ps\": $in_stage,"
puts $out "  \"out_stage_ps\": $out_stage,"
puts $out "  \"crossing_um\": [format %.1f [expr { sqrt($len2) / $dbu }]],"
puts $out "  \"parent_flops\": $n,"
puts $out "  \"flop_t_mean\": [format %.3f $mean],"
puts $out "  \"flop_t_min\": [format %.3f $lo],"
puts $out "  \"flop_t_max\": [format %.3f $hi]"
puts $out "}"
close $out
