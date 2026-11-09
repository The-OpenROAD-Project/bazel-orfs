# The crossing ledger of one part of a parent macro, the parent or a
# block, at its own global route: for every boundary pin, the half of a
# crossing path that lies in this part, in ps, as routed and with every
# wire at zero.
#
#   launch   L(o)    the slowest register behind output o, clock pin to o
#   capture  C(i)    input i to the slowest register behind it, its setup
#                    included
#   feed-through d(i,o)  input i to output o, no register between
#
# Each is the worst of every register behind the pin, not of the paths a
# search happened to report: L and the feed-throughs' worst are read off
# the output's arrivals, C off the input's slack, one read per pin and no
# path search. crossing_ledger.py sums the halves along each crossing net
# into the period a path through it needs, before there is a top level to
# time it on.
#
# The halves must not depend on the part's own boundary constraints or
# on its clock tree, so they are read in a state of the ledger's own:
#
#   - the clocks ideal, every register's clock pin at the median clock
#     slew as built (clk_slew in the header), so a launch starts at its
#     register's clock pin;
#   - every input to every endpoint and to every output a path delay of
#     zero (set_max_delay 0, -ignore_clock_latency to the endpoints): the
#     tightest path delay wins, so the part's own in2reg and in2out
#     budgets do not change a half, and an input's slack is minus the
#     longest path from it, setup included;
#   - for C, the inputs to the outputs false paths, so an input's slack
#     is its registers' alone, and an input no register captures has none.
#
# What it does not see: a path delay of the part's own SDC that is more
# specific than from-pin to-pin (a -through) keeps its own budget; an
# input the SDC makes a false path start (a reset) has no capture half,
# by the SDC's intent; `mcp` on an output says a launch behind it is
# under a multicycle exception, not which.
#
#   LEDGER_OUT         the ledger written (below)
#   HR_TCL             tools/odb_debug/headroom.tcl, for the zero wires
#   LEDGER_PART        the part's name in the header; the design's
#   LEDGER_ODB, LEDGER_SDC  a routed design elsewhere, the two in one
#                      directory; RESULTS_DIR's 5_1_grt by default
#   LEDGER_ARCS_K      the worst paths kept per output and path group for
#                      the feed-throughs (16); an output with that many is
#                      `truncated`, its other feed-throughs not listed
#   LEDGER_SPOT_K      pins per direction checked against a path search
#                      (3; 0: none), the worst ones, and LEDGER_SPOT_PINS
#   LEDGER_SPOT_PINS   further pins to check, by name
#   LEDGER_SKEW        1: the part's setup skew in the header (a search of
#                      its own on the propagated clock)
#   LEDGER_IN2REG_PS, LEDGER_REG2OUT_PS, LEDGER_IN2OUT_PS  the part's
#                      boundary budgets: the pins over them are counted,
#                      loudly, in the log and in `# miss` lines
#   LEDGER_MISS_FATAL  1: a pin over its budget is an error
#   LEDGER_EXTRA_SDC   constraints read on top of the SDC
#   LEDGER_NOTE        a note carried in the ledger (what build this is)
#
# LEDGER_OUT, ps, `-` where a pin has none:
#
#   # part <name> clock <c> period <p> clk_slew <T> skew <s> arcs_k <K>
#   out <pin> <L> <L zero> <ft> <ft zero> <lat> <flags>
#   in <pin> <C> <C zero> <flags>
#   arc <in> <out> <d> <d zero> <complete|truncated>
#
# ft: the slowest feed-through into the output. lat: the clock latency of
# the output's slowest launch as built, what L leaves out. And `# note`,
# `# miss` and `# spot` lines: `# spot <in|out> <pin> <n> min <ps> max
# <ps> half <ps>`, the n registers a path search found behind a checked
# pin, the fastest and the slowest of them, and the half the ledger
# holds, which must be the slowest.
#
# Outside Bazel, in a dirty-lane tree at its global route:
#
#   <tree>/make run RUN_SCRIPT=<bazel-orfs>/tools/carve/crossing_ledger.tcl \
#     HR_TCL=<bazel-orfs>/tools/odb_debug/headroom.tcl LEDGER_OUT=<file>
source $::env(SCRIPTS_DIR)/load.tcl
source $::env(HR_TCL)

set ::ledger_clock [clock milliseconds]
proc ledger_phase { what } {
  set now [clock milliseconds]
  puts [format "crossing_ledger: %-34s %7.1f s" $what [expr { ($now - $::ledger_clock) / 1000.0 }]]
  set ::ledger_clock $now
}

set odb 5_1_grt.odb
set sdc 5_1_grt.sdc
if { [env_var_exists_and_non_empty LEDGER_ODB] } {
  set ::env(RESULTS_DIR) [file dirname $::env(LEDGER_ODB)]
  set odb [file tail $::env(LEDGER_ODB)]
  set sdc [file rootname $odb].sdc
  if { [env_var_exists_and_non_empty LEDGER_SDC] } {
    if { [file dirname $::env(LEDGER_SDC)] ne $::env(RESULTS_DIR) } {
      utl::error FLW 42 "crossing_ledger: LEDGER_SDC is not beside LEDGER_ODB"
    }
    set sdc [file tail $::env(LEDGER_SDC)]
  }
}

# a delay on a port or a latency on a clock would be part of every half
proc ledger_sdc_check { file } {
  set f [open $file]
  set text [read $f]
  close $f
  foreach cmd {set_input_delay set_output_delay set_clock_latency} {
    if { [regexp -line "^\\s*$cmd\\M" $text] } {
      utl::error FLW 43 "crossing_ledger: $file has a $cmd, which every half\
        behind it would carry"
    }
  }
}
ledger_sdc_check $::env(RESULTS_DIR)/$sdc
load_design $odb $sdc
if { [env_var_exists_and_non_empty LEDGER_EXTRA_SDC] } {
  ledger_sdc_check $::env(LEDGER_EXTRA_SDC)
  log_cmd source $::env(LEDGER_EXTRA_SDC)
}
set_propagated_clock [all_clocks]
estimate_parasitics -global_routing
ledger_phase "loaded and estimated"

set part [env_var_or_empty LEDGER_PART]
if { $part eq "" } {
  set part [[ord::get_db_block] getName]
}
set arcs_k [expr { [env_var_exists_and_non_empty LEDGER_ARCS_K] ? $::env(LEDGER_ARCS_K) : 16 }]
set spot_k [expr { [env_var_exists_and_non_empty LEDGER_SPOT_K] ? $::env(LEDGER_SPOT_K) : 3 }]
set clocks [all_clocks]
set clock [lindex $clocks 0]
set ins {}
foreach port [all_inputs -no_clocks] {
  lappend ins [get_full_name $port]
}
set outs {}
foreach port [all_outputs] {
  lappend outs [get_full_name $port]
}
# a clock's edges, s, by its name and the edge as an arrival's tag spells it
set ::ledger_edges [dict create]
foreach c $clocks {
  dict set ::ledger_edges [get_name $c] ^ [$c time rise]
  dict set ::ledger_edges [get_name $c] v [$c time fall]
}

proc ledger_ps { seconds } {
  return [expr { $seconds * 1e12 }]
}

# The arrivals at a port: {launch feed mcp}, the slowest clocked one from
# its clock edge on and the slowest unclocked one, ps, "" where none; mcp
# 1 when a clocked one is under a multicycle exception. An arrival's tag
# reads "<n> <scene> <edge><min|max> unclocked ..." or "... <clock>
# <clock edge> clk_src ...", then its exceptions.
proc ledger_arrivals { port } {
  set launch ""
  set feed ""
  set mcp 0
  foreach vertex [[sta::get_port_pin [get_ports $port]] vertices] {
    foreach rf {rise fall} {
      set it [$vertex path_iterator $rf max]
      while { [$it has_next] } {
        set path [$it next]
        set tag [$path tag]
        if { ![regexp {^\S+ \S+ \S+ (\S+) (\S+)} $tag -> who edge] } {
          utl::error FLW 44 "crossing_ledger: $port: an arrival's tag is not read: $tag"
        }
        if { $who eq "unclocked" } {
          set t [ledger_ps [$path arrival]]
          if { $feed eq "" || $t > $feed } { set feed $t }
          continue
        }
        if { ![dict exists $::ledger_edges $who $edge] } {
          utl::error FLW 44 "crossing_ledger: $port: an arrival's tag is not read: $tag"
        }
        set t [ledger_ps [expr { [$path arrival] - [dict get $::ledger_edges $who $edge] }]]
        if { $launch eq "" || $t > $launch } { set launch $t }
        if { [string match -nocase "*multicycle*" $tag] } { set mcp 1 }
      }
      $it finish
    }
  }
  return [list $launch $feed $mcp]
}

# Every output's arrivals: a dict, output -> {launch feed mcp}.
proc ledger_outs { outs } {
  # arrivals only: no required time is read here
  sta::find_timing_cmd 0
  set got [dict create]
  foreach port $outs {
    dict set got $port [ledger_arrivals $port]
  }
  return $got
}

# The feed-throughs, the k worst paths into every output from each path
# group: {arcs cut}, arcs a dict "<in> <out>" -> ps, the slowest path of
# the pair, and cut the outputs a group held k paths for, whose other
# feed-throughs are not listed. A search to pins needs no arrival but the
# ones found already; a group's k are its own, so register paths in
# another group take none of the feed-throughs' places.
proc ledger_arcs { ins outs k } {
  set is_in [dict create]
  foreach port $ins {
    dict set is_in $port 1
  }
  set arcs [dict create]
  set cut [dict create]
  set to [get_ports $outs]
  if { ![llength $to] } {
    return [list $arcs $cut]
  }
  foreach group [sta::path_group_names] {
    set ends [find_timing_paths -to $to -path_delay max -endpoint_path_count $k \
      -unique_paths_to_endpoint -group_path_count [expr { $k * [llength $outs] }] \
      -path_group [list $group]]
    set count [dict create]
    set feeds 0
    foreach end $ends {
      set o [get_full_name [get_property $end endpoint]]
      dict incr count $o
      set i [get_full_name [get_property $end startpoint]]
      if { ![dict exists $is_in $i] } { continue }
      incr feeds
      set d [ledger_ps [$end data_arrival_time]]
      if { ![dict exists $arcs "$i $o"] || $d > [dict get $arcs "$i $o"] } {
        dict set arcs "$i $o" $d
      }
    }
    if { !$feeds } { continue }
    dict for {o n} $count {
      if { $n >= $k } { dict set cut $o 1 }
    }
  }
  return [list $arcs $cut]
}

# An output's slowest feed-through is its slowest unclocked arrival:
# otherwise something but an input arrives unclocked, or the search
# missed a path.
proc ledger_arcs_check { what got arcs } {
  set worst [dict create]
  dict for {pair d} $arcs {
    set o [lindex $pair 1]
    if { ![dict exists $worst $o] || $d > [dict get $worst $o] } {
      dict set worst $o $d
    }
  }
  dict for {o reads} $got {
    set feed [lindex $reads 1]
    set arc [expr { [dict exists $worst $o] ? [dict get $worst $o] : "" }]
    if { ($feed eq "") != ($arc eq "") || ($feed ne "" && abs($feed - $arc) > 0.1) } {
      utl::error FLW 45 "crossing_ledger: $what: output $o: its slowest unclocked\
        arrival is [expr { $feed eq "" ? "none" : [format %.2f $feed] }] ps, its slowest\
        feed-through [expr { $arc eq "" ? "none" : [format %.2f $arc] }] ps"
    }
  }
}

# Every input's capture half: a dict, input -> ps, "" where no register
# is behind it. Its slack is minus the longest path from it, setup
# included: the path delay asked for is zero.
proc ledger_ins { ins } {
  set got [dict create]
  foreach port $ins {
    set slack [get_property [sta::get_port_pin [get_ports $port]] slack_max]
    # no constrained path: the slack is infinite
    if { ![string is double -strict $slack] || abs($slack) > 1e15 } {
      dict set got $port ""
    } else {
      dict set got $port [ledger_ps [expr { -[sta::time_ui_sta $slack] }]]
    }
  }
  return $got
}

# as built: the clock slew at the registers, the setup skew, and each
# output's slowest launch with its clock latency
set slews {}
foreach pin [all_registers -clock_pins] {
  lappend slews [get_property $pin slew_max_rise]
}
set clk_slew [expr { [llength $slews] ? [lindex [lsort -real $slews] [expr { [llength $slews] / 2 }]] : 0 }]
set skew -
if { [env_var_equals LEDGER_SKEW 1] } {
  set skew [format %.2f [ledger_ps [sta::time_ui_sta [worst_clock_skew -setup]]]]
}
set built [ledger_outs $outs]
ledger_phase "as built: slew, skew, latency"

# the measuring state. The endpoints: every pin a path ends at but the
# ports (and sta::endpoints lists a dangling output pin, which is none)
unset_propagated_clock $clocks
set_clock_transition $clk_slew $clocks
set ends {}
foreach pin [sta::endpoints] {
  if { ![$pin is_top_level_port] && [get_property $pin direction] eq "input" } {
    lappend ends $pin
  }
}
if { [llength $ins] && [llength $ends] } {
  set_max_delay 0 -ignore_clock_latency -from [get_ports $ins] -to $ends
}
if { [llength $ins] && [llength $outs] } {
  set_max_delay 0 -from [get_ports $ins] -to [get_ports $outs]
}

set rc_file [expr {
  [env_var_exists_and_non_empty LAYER_PARASITICS_FILE]
  ? $::env(LAYER_PARASITICS_FILE) : "$::env(PLATFORM_DIR)/setRC.tcl"
}]
set routed_outs [ledger_outs $outs]
lassign [ledger_arcs $ins $outs $arcs_k] routed_arcs routed_cut
ledger_arcs_check routed $routed_outs $routed_arcs
ledger_phase "routed: launches, feed-throughs"
hr_wires_zero global_routing
set zero_outs [ledger_outs $outs]
lassign [ledger_arcs $ins $outs $arcs_k] zero_arcs zero_cut
ledger_arcs_check "zero wire" $zero_outs $zero_arcs
ledger_phase "zero wire: launches, feed-throughs"
# the captures: the inputs' paths to the outputs out of their slacks
if { [llength $ins] && [llength $outs] } {
  set_false_path -from [get_ports $ins] -to [get_ports $outs]
}
set zero_ins [ledger_ins $ins]
ledger_phase "zero wire: captures"
hr_wires_back $rc_file global_routing
set routed_ins [ledger_ins $ins]
ledger_phase "routed: captures"
# the wires are back: every launch reads as it did
dict for {o reads} [ledger_outs $outs] {
  set was [lindex [dict get $routed_outs $o] 0]
  set is [lindex $reads 0]
  if { ($was eq "") != ($is eq "") || ($was ne "" && abs($was - $is) > 0.1) } {
    utl::error FLW 46 "crossing_ledger: output $o launched at $was ps before the\
      zero-wire reading and at $is ps after it: the wires did not come back"
  }
}

# A feed-through one reading listed and the other cut: the delay the cut
# reading's list ends at bounds it from above (the output is `truncated`).
proc ledger_arc_bound { arcs o } {
  set least ""
  dict for {pair d} $arcs {
    if { [lindex $pair 1] eq $o && ($least eq "" || $d < $least) } {
      set least $d
    }
  }
  return $least
}
set pairs [lsort -unique [concat [dict keys $routed_arcs] [dict keys $zero_arcs]]]
set arcs {}
foreach pair $pairs {
  lassign $pair i o
  set cut [expr { [dict exists $routed_cut $o] || [dict exists $zero_cut $o] }]
  set d [expr { [dict exists $routed_arcs $pair] ? [dict get $routed_arcs $pair] : "" }]
  set z [expr { [dict exists $zero_arcs $pair] ? [dict get $zero_arcs $pair] : "" }]
  if { $d eq "" || $z eq "" } {
    if { !$cut } {
      utl::error FLW 47 "crossing_ledger: feed-through $i to $o is in one reading\
        only, and its output was not cut at the $arcs_k worst"
    }
    if { $d eq "" } { set d [ledger_arc_bound $routed_arcs $o] }
    if { $z eq "" } { set z [expr { min($d, [ledger_arc_bound $zero_arcs $o]) }] }
  }
  lappend arcs [list $i $o $d $z [expr { $cut ? "truncated" : "complete" }]]
}

proc ledger_field { value } {
  # not an expr: it would read the formatted number back, and drop a zero
  if { $value eq "" } {
    return -
  }
  return [format %.2f $value]
}

# the pins a path search checks: the worst of each direction, and the
# ones asked for
proc ledger_worst { halves k } {
  set rows {}
  dict for {pin value} $halves {
    if { $value ne "" } { lappend rows [list $pin $value] }
  }
  set pins {}
  foreach row [lrange [lsort -real -decreasing -index 1 $rows] 0 [expr { $k - 1 }]] {
    lappend pins [lindex $row 0]
  }
  return $pins
}
set launches [dict create]
dict for {o reads} $routed_outs {
  dict set launches $o [lindex $reads 0]
}
set spot_outs [ledger_worst $launches $spot_k]
set spot_ins [ledger_worst $routed_ins $spot_k]
foreach pin [env_var_or_empty LEDGER_SPOT_PINS] {
  if { [dict exists $launches $pin] && [dict get $launches $pin] ne "" } {
    if { $pin ni $spot_outs } { lappend spot_outs $pin }
  } elseif { [dict exists $routed_ins $pin] && [dict get $routed_ins $pin] ne "" } {
    if { $pin ni $spot_ins } { lappend spot_ins $pin }
  } else {
    utl::error FLW 48 "crossing_ledger: LEDGER_SPOT_PINS: $pin has no half to check"
  }
}
set spots {}
# an input: every endpoint behind it, each one's worst path from it. The
# half is the slowest, and each is timed by the ledger's path delay: it
# ends at zero less the endpoint's setup.
foreach pin $spot_ins {
  report_checks -from [get_ports $pin] -path_delay max -fields {slew cap} -digits 2
  set found {}
  foreach end [find_timing_paths -from [get_ports $pin] -path_delay max \
    -endpoint_path_count 1 -group_path_count 1000000] {
    if { ![$end is_path_delay] || abs([$end data_required_time] + [$end margin]) > 1e-13 } {
      utl::error FLW 49 "crossing_ledger: input $pin to\
        [get_full_name [get_property $end endpoint]] is not timed by the ledger's\
        path delay of zero"
    }
    lappend found [ledger_ps [expr { [$end data_arrival_time] + [$end margin] }]]
  }
  lappend spots [list in $pin $found [dict get $routed_ins $pin]]
}
# an output: its slowest paths from registers, as many as the
# feed-throughs' k, and the registers they start at
if { [llength $spot_outs] } {
  set by_out [dict create]
  set n [expr { max($arcs_k, 2) }]
  foreach end [find_timing_paths -from $clocks -to [get_ports $spot_outs] -unconstrained \
    -path_delay max -endpoint_path_count $n -unique_paths_to_endpoint \
    -group_path_count [expr { $n * [llength $spot_outs] }]] {
    set c [get_property $end startpoint_clock]
    set edge [dict get $::ledger_edges [get_name $c] ^]
    set o [get_full_name [get_property $end endpoint]]
    # a register's slowest path only: one entry per register
    set start [get_full_name [get_property $end startpoint]]
    set d [ledger_ps [expr { [$end data_arrival_time] - $edge }]]
    if { ![dict exists $by_out $o $start] || $d > [dict get $by_out $o $start] } {
      dict set by_out $o $start $d
    }
  }
  foreach pin $spot_outs {
    report_checks -from $clocks -to [get_ports $pin] -unconstrained -path_delay max \
      -fields {slew cap} -digits 2
    set found [expr { [dict exists $by_out $pin] ? [dict values [dict get $by_out $pin]] : {} }]
    lappend spots [list out $pin $found [dict get $launches $pin]]
  }
}
set spot_lines {}
foreach spot $spots {
  lassign $spot dir pin found half
  set found [lsort -real $found]
  if { ![llength $found] || abs([lindex $found end] - $half) > 0.1 } {
    utl::error FLW 50 "crossing_ledger: $dir $pin: the ledger holds\
      [format %.2f $half] ps, a path search finds\
      [expr { [llength $found] ? [format %.2f [lindex $found end]] : "nothing" }]"
  }
  lappend spot_lines [format "# spot %s %s %d min %.2f max %.2f half %.2f" $dir $pin \
    [llength $found] [lindex $found 0] [lindex $found end] $half]
}
ledger_phase "spot checks"

# the boundary's budgets: the pins over them, counted and named
set misses {}
set over_total 0
foreach {kind var halves} [list \
  in2reg LEDGER_IN2REG_PS $routed_ins \
  reg2out LEDGER_REG2OUT_PS $launches \
  in2out LEDGER_IN2OUT_PS [dict map {o reads} $routed_outs { lindex $reads 1 }]] {
  if { ![env_var_exists_and_non_empty $var] } { continue }
  set budget $::env($var)
  set pins 0
  set over 0
  set worst ""
  dict for {pin value} $halves {
    if { $value eq "" } { continue }
    incr pins
    if { $value > $budget } { incr over }
    if { $worst eq "" || $value > [lindex $worst 1] } { set worst [list $pin $value] }
  }
  if { !$pins } { continue }
  incr over_total $over
  lappend misses [format "# miss %s %d/%d worst %s %.2f budget %s" $kind $over $pins \
    [lindex $worst 0] [lindex $worst 1] $budget]
}
if { ![llength $misses] } {
  lappend misses "# miss - no boundary budget given"
}

set f [open $::env(LEDGER_OUT) w]
puts $f "# part $part clock [get_name $clock] period\
  [format %.2f [ledger_ps [$clock period]]] clk_slew\
  [format %.2f [ledger_ps [sta::time_ui_sta $clk_slew]]] skew $skew arcs_k $arcs_k"
puts $f "# ps, routed and zero-wire: out <pin> <L> <L zero> <ft> <ft zero> <lat> <flags>;\
  in <pin> <C> <C zero> <flags>; arc <in> <out> <d> <d zero> <complete|truncated>"
if { [env_var_exists_and_non_empty LEDGER_NOTE] } {
  puts $f "# note $::env(LEDGER_NOTE)"
}
if { [llength $clocks] > 1 } {
  puts $f "# note [llength $clocks] clocks: a launch is the slowest of any of them"
}
foreach line [concat $misses $spot_lines] {
  puts $f $line
}
foreach o $outs {
  lassign [dict get $routed_outs $o] launch feed mcp
  lassign [dict get $zero_outs $o] launch_zero feed_zero
  set lat ""
  if { $launch ne "" } {
    set lat [expr { [lindex [dict get $built $o] 0] - $launch }]
  }
  puts $f "out $o [ledger_field $launch] [ledger_field $launch_zero] [ledger_field $feed]\
    [ledger_field $feed_zero] [ledger_field $lat] [expr { $mcp ? "mcp" : "-" }]"
}
foreach i $ins {
  puts $f "in $i [ledger_field [dict get $routed_ins $i]] [ledger_field [dict get $zero_ins $i]] -"
}
foreach arc $arcs {
  lassign $arc i o d z state
  puts $f "arc $i $o [ledger_field $d] [ledger_field $z] $state"
}
close $f

puts "crossing_ledger: $part: [llength $outs] outputs, [llength $ins] inputs,\
  [llength $arcs] feed-throughs, [dict size $routed_cut] outputs cut at the $arcs_k worst"
if { $over_total } {
  puts "# ---------------------------------------------------------------------"
  puts "# crossing_ledger: BOUNDARY MISS: $part has $over_total pins over its budgets"
} elseif { [lindex $misses 0] eq "# miss - no boundary budget given" } {
  puts "crossing_ledger: $part: no boundary budget given, no miss counted"
}
foreach line $misses {
  if { $over_total } { puts $line }
}
if { $over_total } {
  puts "# ---------------------------------------------------------------------"
  if { [env_var_equals LEDGER_MISS_FATAL 1] } {
    utl::error FLW 51 "crossing_ledger: $part has $over_total boundary pins over\
      their budgets (LEDGER_MISS_FATAL)"
  }
}
