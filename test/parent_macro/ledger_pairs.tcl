# The crossing ledger's feed-throughs as a direct search reads them, for
# crossing_ledger_check.py --pairs: every input and output a path is
# timed between, each pair asked for by itself (find_timing_paths -from
# <in> -to <out>), its slowest path, as routed and with every wire at
# zero, in the part's own constraints.
#
#   PAIRS_OUT  written: pair <in> <out> <d> <d zero>, ps
#   HR_TCL     tools/odb_debug/headroom.tcl, for the zero wires
source $::env(SCRIPTS_DIR)/load.tcl
source $::env(HR_TCL)
load_design 5_1_grt.odb 5_1_grt.sdc
estimate_parasitics -global_routing

# "<in> <out>" -> ps, the slowest path of each pair a path is timed for
proc pairs_read { } {
  set got [dict create]
  foreach i [all_inputs -no_clocks] {
    foreach o [all_outputs] {
      foreach end [find_timing_paths -from $i -to $o -unconstrained -path_delay max \
        -endpoint_path_count 1 -group_path_count 100] {
        set pair "[get_full_name $i] [get_full_name $o]"
        set d [expr { [$end data_arrival_time] * 1e12 }]
        if { ![dict exists $got $pair] || $d > [dict get $got $pair] } {
          dict set got $pair $d
        }
      }
    }
  }
  return $got
}
set routed [pairs_read]
hr_wires_zero global_routing
set zero [pairs_read]

set f [open $::env(PAIRS_OUT) w]
puts $f "# pair <in> <out> <d> <d zero>, ps: a direct search per pair"
foreach pair [lsort [dict keys $routed]] {
  # not an expr: it would read the formatted number back, and drop a zero
  set z -
  if { [dict exists $zero $pair] } {
    set z [format %.2f [dict get $zero $pair]]
  }
  puts $f "pair $pair [format %.2f [dict get $routed $pair]] $z"
}
close $f
puts "ledger_pairs: [dict size $routed] pairs"
