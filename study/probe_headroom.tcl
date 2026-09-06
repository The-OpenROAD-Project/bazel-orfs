# Is a design suitable for studying PR 11320?
#
# The PR does two things: it stops rejecting drivers with fanout >= 10,
# and it steps one drive size down instead of jumping to the minimum-cap
# cell. Both are inert on a design that has nothing to downsize. On
# asap7/riscv32i the move was rejected 21304 times with "Couldn't size
# down any gates" and committed 19 downsizes, and the arms came out
# bit-identical.
#
# So suitability is not "big" or "slow", it is two measurable properties:
#
#   1. HIGH-FANOUT DRIVERS -- nets with fanout >= 10. Below that
#      threshold the old code and the new code consider the same drivers
#      and change (a) cannot bite.
#   2. DOWNSIZE HEADROOM among the loads of those nets -- a load whose
#      liberty cell has a smaller-area swappable sibling. Without it the
#      move is rejected however it is reached, and change (b) cannot
#      bite either.
#
# A design scores well only on BOTH. Reported per design so the choice of
# designs is a measurement rather than an intuition.

source $::env(SCRIPTS_DIR)/load.tcl
load_design 3_place.odb 3_place.sdc

set fanout_threshold 10
if { [info exists ::env(PROBE_FANOUT_THRESHOLD)] } {
  set fanout_threshold $::env(PROBE_FANOUT_THRESHOLD)
}

# cell name -> 1 if some swappable sibling has strictly smaller area.
# report_equiv_cells is OpenROAD's own notion of swappability, so this
# does not re-derive one from cell-name conventions.
# Area comes from the db master (width * height), not the liberty cell:
# the Tcl LibertyCell object exposes no area method. Physical area is the
# quantity the move trades against anyway.
proc master_area { name } {
  set master [[ord::get_db] findMaster $name]
  if { $master eq "NULL" || $master eq "" } {
    return -1
  }
  return [expr { [$master getWidth] * [$master getHeight] }]
}

# cell name -> 1 if some swappable sibling has strictly smaller area.
# report_equiv_cells is OpenROAD's own notion of swappability, so this
# does not re-derive one from cell-name conventions.
proc has_smaller_sibling { cell_name cache_var } {
  upvar 1 $cache_var cache
  if { [info exists cache($cell_name)] } {
    return $cache($cell_name)
  }
  set cache($cell_name) 0
  set cells [get_lib_cells -quiet $cell_name]
  if { [llength $cells] == 0 } {
    return 0
  }
  set self_area [master_area $cell_name]
  if { $self_area < 0 } {
    return 0
  }
  # [list ...]: tee evaluates its body as `{*}$body`, which splits a braced
  # body into words WITHOUT substituting them, so an unbraced command would
  # reach report_equiv_cells as the literal words "[lindex" "$cells" "0]".
  # tee STORES the captured text in the named variable and RETURNS the
  # wrapped command's own result -- reading the return value yields "".
  tee -variable captured -quiet [list report_equiv_cells -all [lindex $cells 0]]
  set out $captured
  # report_equiv_cells prints a TABLE (header, separators, then one row per
  # cell: name, area, area ratio, leakage, leakage ratio, VT), not bare
  # names -- so take the row's first token. Treating whole lines as names
  # silently matched nothing and reported 0% headroom on every design.
  foreach line [split $out "\n"] {
    set name [lindex [string trim $line] 0]
    if { $name eq "" || $name eq $cell_name } {
      continue
    }
    set sib_area [master_area $name]
    if { $sib_area >= 0 && $sib_area < $self_area } {
      set cache($cell_name) 1
      return 1
    }
  }
  return 0
}

set block [ord::get_db_block]
array set cache {}

set nets_total 0
set nets_high 0
set loads_high 0
set loads_high_with_headroom 0
set loads_all 0
set loads_all_with_headroom 0

foreach net [$block getNets] {
  if { [$net isSpecial] } {
    continue
  }
  set loads {}
  foreach iterm [$net getITerms] {
    if { [[$iterm getMTerm] getIoType] eq "INPUT" } {
      lappend loads $iterm
    }
  }
  set fanout [llength $loads]
  if { $fanout == 0 } {
    continue
  }
  incr nets_total
  set high [expr { $fanout >= $fanout_threshold }]
  if { $high } {
    incr nets_high
  }
  foreach iterm $loads {
    set cell_name [[[$iterm getInst] getMaster] getName]
    set headroom [has_smaller_sibling $cell_name cache]
    incr loads_all
    incr loads_all_with_headroom $headroom
    if { $high } {
      incr loads_high
      incr loads_high_with_headroom $headroom
    }
  }
}

proc pct { n d } {
  if { $d == 0 } {
    return 0.0
  }
  return [format %.1f [expr { 100.0 * $n / $d }]]
}

set report [list \
  design $::env(STUDY_DESIGN) \
  fanout_threshold $fanout_threshold \
  nets $nets_total \
  nets_high_fanout $nets_high \
  pct_nets_high_fanout [pct $nets_high $nets_total] \
  loads $loads_all \
  pct_loads_with_headroom [pct $loads_all_with_headroom $loads_all] \
  loads_on_high_fanout_nets $loads_high \
  loads_on_high_fanout_nets_with_headroom $loads_high_with_headroom \
  pct_high_fanout_loads_with_headroom [pct $loads_high_with_headroom $loads_high]]

puts "PROBE: $report"
set fd [open $::env(RESULTS_OUT)/probe.txt w]
puts $fd $report
close $fd
