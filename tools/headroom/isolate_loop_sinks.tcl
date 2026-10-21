# Critical-sink isolation for one-flop loops, a prototype: for every buffer
# on the worst loops, reconnect the loop's own sink from the buffer's output
# to the net the buffer chain starts from. The buffer keeps serving every
# other sink; only the critical one moves ahead of it.
proc isolate_loop_sinks { {loops 100} } {
  set r2r [list -from [all_registers -clock_pins] -to [all_registers -data_pins]]
  set regs {}
  foreach pe [find_timing_paths {*}$r2r -sort_by_slack -endpoint_path_count 1 \
                -group_path_count $loops -unique_paths_to_endpoint] {
    lappend regs [get_full_name [get_cells -of_objects [get_property $pe endpoint]]]
  }
  set moved 0
  foreach reg [lsort -unique $regs] {
    set cell [get_cells $reg]
    set ck [get_pins -quiet -of_objects $cell -filter "is_register_clock == 1"]
    set d [get_pins -quiet -of_objects $cell -filter "direction == input && is_register_clock == 0"]
    if { [llength $ck] != 1 || ![llength $d] } { continue }
    set loop [lindex [find_timing_paths -from $ck -to $d -group_path_count 1] 0]
    if { $loop eq "" } { continue }
    # the loop's input pins that sit right after a buffer output
    set prev ""
    set pins {}
    foreach p [get_property $loop points] { lappend pins [get_full_name [get_property $p pin]] }
    for { set i 1 } { $i < [llength $pins] } { incr i } {
      set pin [get_pins [lindex $pins $i]]
      if { [get_property $pin direction] ne "input" } { continue }
      set drv [get_pins [lindex $pins [expr { $i - 1 }]]]
      set lib [get_property [get_cells -of_objects $drv] liberty_cell]
      if { ![get_property $lib is_buffer] } { continue }
      # walk back through the chain of buffers to the net that feeds it
      set root_in ""
      set c [get_cells -of_objects $drv]
      while { 1 } {
        set a [get_pins -of_objects $c -filter "direction == input"]
        set root_in $a
        set up [get_pins -quiet -of_objects [get_nets -of_objects $a] -filter "direction == output"]
        if { [llength $up] != 1 } { break }
        set uc [get_cells -of_objects $up]
        if { ![get_property [get_property $uc liberty_cell] is_buffer] } { break }
        set c $uc
      }
      set root_net [[sta::sta_to_db_pin $root_in] getNet]
      set iterm [sta::sta_to_db_pin $pin]
      $iterm disconnect
      $iterm connect $root_net
      incr moved
    }
  }
  return $moved
}

# As a flow hook (PRE_CTS_TCL): isolate, then re-estimate.
if { [info exists ::env(ISOLATE_LOOP_SINKS)] && $::env(ISOLATE_LOOP_SINKS) } {
  puts "Isolated [isolate_loop_sinks $::env(ISOLATE_LOOP_SINKS)] loop sinks"
  estimate_parasitics -placement
}
