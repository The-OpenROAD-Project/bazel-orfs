# Peel probe, the parent's half. Run in a timing session (GUI_TIMING=1)
# on the parent's global-route ODB. For the worst reg2reg paths, one
# per endpoint: the path's delay (the period minus its slack), the block
# and port that launch it when a hardened block does, and the crossing:
# the delay from that port to the first cell that is not a repeater
# (BUF, INV, HB, CKINV). The crossing is how far a flop peeled out of
# the block could slide toward the capture side. peel_bound.py joins
# this with each block's probe_peel.tcl output.
#
# PEEL_PATHS_OUT the tab-separated file to write
# PEEL_PATHS_COUNT how many endpoints (default 1000)
# PEEL_PATH_GROUP the path group (default reg2reg)

proc peel_repeater { ref } {
  return [regexp {^(BUF|INV|HB|CKINV)} $ref]
}

set count 1000
if { [info exists ::env(PEEL_PATHS_COUNT)] } { set count $::env(PEEL_PATHS_COUNT) }
set group reg2reg
if { [info exists ::env(PEEL_PATH_GROUP)] } { set group $::env(PEEL_PATH_GROUP) }

# The hardened blocks by master name: what a launching pin's cell must be.
array set blocks {}
foreach inst [[ord::get_db_block] getInsts] {
  set m [$inst getMaster]
  if { [$m isBlock] } { set blocks([$m getName]) 1 }
}

set period [get_property [lindex [all_clocks] 0] period]
set pes [find_timing_paths -path_delay max -path_group $group \
  -group_path_count $count -endpoint_path_count 1 -sort_by_slack]
set out [open $::env(PEEL_PATHS_OUT) w]
puts $out "rank\tpath_ps\tlaunch_block\tlaunch_port\tcrossing_ps\tstartpoint\tendpoint"
set rank 0
foreach pe $pes {
  incr rank
  set slack [get_property $pe slack]
  set block ""
  set port ""
  set crossing ""
  set a0 ""
  foreach pt [get_property $pe points] {
    set pin [get_property $pt pin]
    set cell [get_cells -quiet -of_objects $pin]
    if { [llength $cell] == 0 } { break }
    set ref [get_property $cell ref_name]
    set dir [get_property $pin direction]
    if { $a0 eq "" } {
      # Before the launch: a block's output pin starts the crossing.
      if { $dir eq "output" && [info exists blocks($ref)] } {
        set block $ref
        set port [get_property $pin lib_pin_name]
        set a0 [get_property $pt arrival]
      } elseif { $dir eq "input" && ![info exists blocks($ref)] } {
        # the first cell input past the launch without a block: not ours
        break
      }
      continue
    }
    if { $dir ne "input" } { continue }
    if { [info exists blocks($ref)] || ![peel_repeater $ref] } {
      set crossing [format %.0f [expr { [get_property $pt arrival] - $a0 }]]
      break
    }
  }
  # A path that ends at a repeater's input never reaches a stop; the
  # endpoint is a register, so the walk always stops before the end.
  puts $out [join [list $rank [format %.0f [expr { $period - $slack }]] \
    $block $port $crossing \
    [get_full_name [get_property $pe startpoint]] \
    [get_full_name [get_property $pe endpoint]]] "\t"]
}
close $out
puts "peel paths: $rank endpoints of $group written to $::env(PEEL_PATHS_OUT)"
