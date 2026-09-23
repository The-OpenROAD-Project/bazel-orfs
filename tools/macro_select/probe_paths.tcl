# Boundary probe, timing half. Run in an odb-debug session with timing on
# a hierarchical synthesis ODB. Dumps the PROBE_COUNT (default 20000)
# worst path ends of every group as one line each to PROBE_OUT:
#
#   <slack ps> <priced slack ps> <pins on the path> <max fanout> <endpoint pin> <startpoint pin>
#
# The startpoint is the path's first point, the launching register's
# clock pin or an input port (a port has no "/": that is how a boundary
# crossing is told apart). Module attribution from instance names is
# timing_table.py's job.
#
# Synthesis-stage slack is a fanout artefact until something buffers: a
# net of fanout 1410 charges its driver with a delay no placed design
# will see, because the resizer will turn it into a tree under the SDC's
# max_fanout. Running repair_design on a whole core does not return in a
# day (ideas/xiangshan-timing.md, entry 4), so the priced slack charges
# each such stage what the tree will cost instead: ceil(log_N(fanout))
# levels of PROBE_BUF_PS each, N = PROBE_MAX_FANOUT (default 32, the
# SDC's max_fanout), and gives the rest of the stage's delay back. A stage
# whose driver fans out to N or fewer keeps its delay. PROBE_BUF_PS
# defaults to 40 and is calibrated against a real repair_design
# -pre_placement on one block (the table's docstring says how).
set out [open $::env(PROBE_OUT) w]
set count [expr { [info exists ::env(PROBE_COUNT)] ? $::env(PROBE_COUNT) : 20000 }]
set max_fanout [expr { [info exists ::env(PROBE_MAX_FANOUT)] ? $::env(PROBE_MAX_FANOUT) : 32 }]
set buf_ps [expr { [info exists ::env(PROBE_BUF_PS)] ? $::env(PROBE_BUF_PS) : 40.0 }]

# fanout of the net a pin drives, from odb (the ITerm count of its net,
# minus the driver); ports drive through BTerms and count their ITerms
proc probe_fanout {pin} {
  set name [sta::get_full_name $pin]
  set block [ord::get_db_block]
  set it [$block findITerm $name]
  if { $it != "NULL" } {
    set net [$it getNet]
    if { $net == "NULL" } { return 0 }
    return [expr { [llength [$net getITerms]] - 1 + [llength [$net getBTerms]] }]
  }
  set bt [$block findBTerm $name]
  if { $bt != "NULL" } {
    set net [$bt getNet]
    if { $net == "NULL" } { return 0 }
    return [llength [$net getITerms]]
  }
  return 0
}

set ends [sta::find_timing_paths -path_delay max -group_path_count $count -sort_by_slack]
set n 0
set priced_stages 0
foreach pe $ends {
  set p [$pe path]
  set pins [$p pins]
  set endp [sta::get_full_name [$pe pin]]
  set slack [expr { [$pe slack] * 1e12 }]
  # walk the points launch to capture: the first point is the startpoint
  # (a register's clock pin or an input port); a driver's stage delay is
  # the arrival step onto its output pin
  set start ""
  set phantom 0.0
  set max_fo 0
  set prev ""
  foreach pt [get_property $pe points] {
    set arr [expr { [get_property $pt arrival] * 1e12 }]
    set pin [get_property $pt pin]
    if { $start eq "" } { set start [sta::get_full_name $pin] }
    if { $prev ne "" } {
      set delay [expr { $arr - $prev }]
      if { [get_property $pin direction] eq "output" } {
        set fo [probe_fanout $pin]
        if { $fo > $max_fo } { set max_fo $fo }
        if { $fo > $max_fanout } {
          set levels [expr { int(ceil(log($fo) / log($max_fanout))) }]
          set priced [expr { $levels * $buf_ps }]
          if { $delay > $priced } {
            set phantom [expr { $phantom + $delay - $priced }]
            incr priced_stages
          }
        }
      }
    }
    set prev $arr
  }
  puts $out "[format %.1f $slack] [format %.1f [expr { $slack + $phantom }]] [llength $pins] $max_fo $endp $start"
  incr n
}
close $out
puts "paths: $n path ends written to $::env(PROBE_OUT); $priced_stages stages priced as fanout trees (max_fanout $max_fanout, $buf_ps ps per level)"
