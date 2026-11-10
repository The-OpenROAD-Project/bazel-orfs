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
# search happened to report: L is read off the output's slack, C off the
# input's, one read per pin, no path search and no path or tag walked.
# crossing_ledger.py sums the halves along each crossing net into the
# path a crossing through it has to fit in a period, before there is a
# top level to time it on. A half holds no clock: not the latency of the
# part's own tree, not the skew a top level adds between two parts.
#
# The halves must not depend on the part's own boundary constraints or
# on its clock tree, so they are read in a state of the ledger's own:
#
#   - the clocks ideal, every register's clock pin at the median clock
#     slew as built (clk_slew in the header), so a launch starts at its
#     register's clock pin;
#   - every register and clock to every output, and every input to
#     every endpoint, a path delay of zero (set_max_delay 0,
#     -ignore_clock_latency to the endpoints): the tightest path delay
#     wins, so the part's own in2reg and reg2out budgets do not change a
#     half, and a pin's slack is minus the longest path from or to it,
#     setup included;
#   - every input to every output a path delay far under zero, so a pin
#     a feed-through passes reads apart from one none does: its slack
#     then holds the slowest feed-through into the output (ft) or out of
#     the input (F);
#   - for L and C, the inputs to the outputs false paths, so a pin's
#     slack is its registers' alone, and a pin with no register behind it
#     has none.
#
# The feed-throughs listed are every input and output with a path between
# them, each pair's slowest path: the inputs in the fan-in of each output
# a feed-through passes, by the timing arcs. A first pass lists the worst
# paths into those outputs, and a pair it lists is kept when it is its
# output's slowest, as the output's slack reads it; every other pair is
# asked for by itself, one search from each input to its outputs. The
# first pass alone is no list: OpenSTA's path enumeration follows one
# transition and one set of exception states into each output, so a pair
# under another set_max_delay -from than the output's slowest, or behind
# the k worst into it, is not in it, and a pair it lists may be one of
# the pair's faster paths. A delay this far from zero is read to within
# OpenSTA's fuzzy equal, a millionth: every arc is within twice that,
# ledger_fuzz, of its pair's slowest path.
#
# What it does not see: a path delay of the part's own SDC that is more
# specific than from-pin to-pin (a -through) keeps its own budget; a pin
# the SDC makes a false path's start or end (a reset) has no half, by
# the SDC's intent; `mcp` on the outputs says the SDC has a multicycle
# exception, not on which path.
#
#   LEDGER_OUT         the ledger written (below)
#   HR_TCL             tools/odb_debug/headroom.tcl, for the zero wires
#   LEDGER_PART        the part's name in the header; the design's
#   LEDGER_ODB, LEDGER_SDC  a routed design elsewhere, the two in one
#                      directory; RESULTS_DIR's 5_1_grt by default
#   LEDGER_ARCS_K      the worst paths per output and path group the
#                      feed-throughs' first pass lists (1; 0: no first
#                      pass, every pair asked for): what it costs, not
#                      what is listed. It keeps only an output's slowest,
#                      so more keep only the ties with it
#   LEDGER_SPOT_K      pins per direction checked against a path search
#                      (3; 0: none, on a part the size of a hub: each is a
#                      search), the worst ones, and LEDGER_SPOT_PINS
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
#     feeds <n>
#   out <pin> <L> <L zero> <ft> <ft zero> <lat> <flags>
#   in <pin> <C> <C zero> <flags>
#   feed <in> <F> <F zero>
#   arc <in> <out> <d> <d zero>
#
# ft: the slowest feed-through into the output, and its slowest arc. F:
# the slowest out of the input, on the n inputs that have one, its
# slowest arc or under it. lat: the clock latency of the output's
# slowest launch as built, what L leaves out; none behind an output a
# feed-through passes. The ledger is written as <LEDGER_OUT>.unchecked
# first, and under its name once its checks passed. And `# note`,
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
set ::ledger_mcp 0
proc ledger_sdc_check { file } {
  set f [open $file]
  set text [read $f]
  close $f
  if { [regexp -line {^\s*set_multicycle_path\M} $text] } {
    set ::ledger_mcp 1
  }
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
set arcs_k [expr { [env_var_exists_and_non_empty LEDGER_ARCS_K] ? $::env(LEDGER_ARCS_K) : 1 }]
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
# a clock's edges, s, by its name: where a spot check's launch starts
set ::ledger_edges [dict create]
foreach c $clocks {
  dict set ::ledger_edges [get_name $c] ^ [$c time rise]
  dict set ::ledger_edges [get_name $c] v [$c time fall]
}

proc ledger_ps { seconds } {
  return [expr { $seconds * 1e12 }]
}

# While the feed-throughs are timed they are asked for this much less
# than zero, ps: a port one passes reads over it and any other port far
# under it, so no path and no tag is read to tell the two apart.
set ::ledger_apart 100000.0

# OpenSTA calls two delays equal when they are within a millionth of the
# larger (fuzzyEqual), which this far from zero is 0.1 ps: of two
# feed-throughs into one output that close, a slack reads either one.
set ::ledger_fuzz [expr { 2e-6 * $::ledger_apart }]

# what the readings do not agree on, {code message}: raised once the
# readings are on disk
set ::ledger_errors {}

# Every port's slack, as the path it stands for: a dict, port -> ps,
# minus the slack, "" where no timed path starts or ends at it. The path
# delay asked for is zero: an input's slack is minus the longest path
# from it, setup included, an output's minus the longest path to it from
# its launching clock edge on, each over every register behind the pin.
proc ledger_slacks { ports } {
  set got [dict create]
  foreach port $ports {
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

# A half that could be taken for a feed-through: none is that long.
proc ledger_short { what halves } {
  dict for {port t} $halves {
    if { $t ne "" && $t >= $::ledger_apart / 2 } {
      utl::error FLW 44 "crossing_ledger: $what: $port holds a path of\
        [format %.0f $t] ps, which the feed-throughs are not told apart from"
    }
  }
}

# A reading while the feed-throughs are timed, split: {feeds others},
# feeds the ports a feed-through passes -> the slowest one, others the
# rest -> their launch or capture, or "".
proc ledger_split { what reads } {
  set feeds [dict create]
  set others [dict create]
  dict for {port t} $reads {
    if { $t ne "" && $t >= $::ledger_apart - 1.0 } {
      dict set feeds $port [expr { max($t - $::ledger_apart, 0.0) }]
    } else {
      dict set others $port $t
    }
  }
  ledger_short $what $others
  return [list $feeds $others]
}

# The inputs in an output's fan-in, by the timing arcs that are neither
# disabled nor behind a constant, across the hierarchy: the pairs the
# feed-throughs into it are listed for. The netlist's, so both readings
# share one walk per output.
set ::ledger_fanin [dict create]
proc ledger_fanin { o is_in } {
  if { ![dict exists $::ledger_fanin $o] } {
    set got {}
    # the registers' clock pins, by the thousand behind an output, unnamed
    foreach pin [get_fanin -to [get_ports $o] -startpoints_only -flat] {
      if { ![$pin is_top_level_port] } { continue }
      set name [get_full_name $pin]
      if { [dict exists $is_in $name] } { lappend got $name }
    }
    dict set ::ledger_fanin $o $got
  }
  return [dict get $::ledger_fanin $o]
}

# The first pass, the k worst paths into each output from each path group
# (none for k 0): a dict "<in> <out>" -> ps, the slowest path of the pair
# it lists. A search to pins needs no arrival but the ones found already,
# and a feed-through is asked for less than any register path, so it
# comes first wherever both are in one group.
proc ledger_listed { is_in outs k } {
  set listed [dict create]
  if { !$k || ![llength $outs] } {
    return $listed
  }
  set to [get_ports $outs]
  foreach group [sta::path_group_names] {
    foreach end [find_timing_paths -to $to -path_delay max -endpoint_path_count $k \
      -unique_paths_to_endpoint -group_path_count [expr { $k * [llength $outs] }] \
      -path_group [list $group]] {
      set i [get_full_name [get_property $end startpoint]]
      if { ![dict exists $is_in $i] } { continue }
      set pair "$i [get_full_name [get_property $end endpoint]]"
      set d [ledger_ps [$end data_arrival_time]]
      if { ![dict exists $listed $pair] || $d > [dict get $listed $pair] } {
        dict set listed $pair $d
      }
    }
  }
  return $listed
}

# The pairs asked for by themselves, a dict input -> its outputs: the
# slowest path of each, a search from the input to those outputs, the
# worst path into each from every path group. A dict "<in> <out>" -> ps,
# no entry where no path is timed.
proc ledger_asked { asks } {
  set asked [dict create]
  dict for {i outs} $asks {
    foreach end [find_timing_paths -from [get_ports $i] -to [get_ports $outs] \
      -path_delay max -endpoint_path_count 1 -group_path_count [llength $outs]] {
      set pair "$i [get_full_name [get_property $end endpoint]]"
      set d [ledger_ps [$end data_arrival_time]]
      if { ![dict exists $asked $pair] || $d > [dict get $asked $pair] } {
        dict set asked $pair $d
      }
    }
  }
  return $asked
}

# The feed-throughs, every pair in the fan-in of an output one passes
# (out_feeds), each its slowest path: a dict "<in> <out>" -> ps. A pair
# the first pass lists is kept when it is within half the fuzz of the
# slowest its output's slack read, which no path into the output passes
# by more than the other half; every other pair is asked for. A fan-in
# pair no path is timed for (a false path) is no feed-through, and is
# said.
proc ledger_arcs { what ins out_feeds k } {
  set is_in [dict create]
  foreach port $ins {
    dict set is_in $port 1
  }
  set listed [ledger_listed $is_in [dict keys $out_feeds] $k]
  ledger_phase "$what: first pass, [dict size $listed] pairs"
  set arcs [dict create]
  set asks [dict create]
  set pairs 0
  dict for {o ft} $out_feeds {
    set fanin [ledger_fanin $o $is_in]
    incr pairs [llength $fanin]
    foreach i $fanin {
      if { [dict exists $listed "$i $o"] && [dict get $listed "$i $o"] >= $ft - $::ledger_fuzz / 2 } {
        dict set arcs "$i $o" [dict get $listed "$i $o"]
      } else {
        dict lappend asks $i $o
      }
    }
  }
  # the first pass found a path the fan-in does not have
  dict for {pair d} $listed {
    lassign $pair i o
    if { $i ni [ledger_fanin $o $is_in] } {
      lappend ::ledger_errors [list 54 "$what: a feed-through from $i to $o is timed, and\
        $i is not in the fan-in of $o"]
    }
  }
  ledger_phase "$what: fan-in, $pairs pairs, [dict size $arcs] kept"
  set asked [ledger_asked $asks]
  set none {}
  dict for {i outs} $asks {
    foreach o $outs {
      if { [dict exists $asked "$i $o"] } {
        dict set arcs "$i $o" [dict get $asked "$i $o"]
      } else {
        lappend none "$i to $o"
      }
    }
  }
  ledger_phase "$what: asked, [dict size $asks] inputs"
  if { [llength $none] } {
    puts "crossing_ledger: $what: [llength $none] pairs in an output's fan-in have no timed\
      path, no feed-through: [join [lrange $none 0 9] ", "][expr { [llength $none] > 10 ? ", ..." : "" }]"
  }
  return $arcs
}

# Each port's slowest listed feed-through is the one its slack read, an
# output's (45) and an input's (53): otherwise something but an input
# starts an unclocked path, or a feed-through is not listed. An input's
# slack comes through required times carried back over its fan-out, a
# fuzzy comparison at every merge this far from zero, so it may read
# under the input's slowest path, never over: an arc slower than it is
# no arc missing, and is not checked.
proc ledger_arcs_check { what out_feeds in_feeds arcs } {
  foreach {side at feeds code} [list output 1 $out_feeds 45 input 0 $in_feeds 53] {
    set worst [dict create]
    dict for {pair d} $arcs {
      set port [lindex $pair $at]
      if { ![dict exists $worst $port] || $d > [dict get $worst $port] } {
        dict set worst $port $d
      }
    }
    foreach port [lsort -unique [concat [dict keys $feeds] [dict keys $worst]]] {
      set feed [expr { [dict exists $feeds $port] ? [dict get $feeds $port] : "" }]
      set arc [expr { [dict exists $worst $port] ? [dict get $worst $port] : "" }]
      if { $feed eq "" || $arc eq "" || $arc < $feed - $::ledger_fuzz
        || ($side eq "output" && $arc > $feed + $::ledger_fuzz) } {
        lappend ::ledger_errors [list $code "$what: $side $port: its slack reads a\
          feed-through of [expr { $feed eq "" ? "none" : [format %.2f $feed] }] ps, the\
          slowest one listed is [expr { $arc eq "" ? "none" : [format %.2f $arc] }] ps"]
      }
    }
  }
}

# One reading while the feed-throughs are timed: {out_feeds out_others
# in_feeds in_others arcs}, the outputs' and the inputs' slowest
# feed-throughs, the halves of the ports none passes, and the list.
proc ledger_reading { what ins outs k } {
  lassign [ledger_split "$what, outputs" [ledger_slacks $outs]] out_feeds out_others
  lassign [ledger_split "$what, inputs" [ledger_slacks $ins]] in_feeds in_others
  ledger_phase "$what: slacks"
  set arcs [ledger_arcs $what $ins $out_feeds $k]
  ledger_arcs_check $what $out_feeds $in_feeds $arcs
  return [list $out_feeds $out_others $in_feeds $in_others $arcs]
}

# A port no feed-through passes held its half while they were timed, and
# holds it again once they are false paths: the two are one number.
# Returns the ports compared.
proc ledger_same { what was is } {
  dict for {port t} $was {
    set now [dict get $is $port]
    if { ($t eq "") != ($now eq "") || ($t ne "" && abs($t - $now) > 0.1) } {
      lappend ::ledger_errors [list 46 "$port read [ledger_field $t] ps before and\
        [ledger_field $now] ps after: $what"]
    }
  }
  return [dict size $was]
}

proc ledger_field { value } {
  # not an expr: it would read the formatted number back, and drop a zero
  if { $value eq "" } {
    return -
  }
  return [format %.2f $value]
}

# The launches and the feed-throughs are timed from here on, by path
# delays of the ledger's own: zero from every register, and from every
# clock for what is no register, to every output; the feed-throughs set
# apart. The part's own budgets are no tighter, so these win.
if { [llength $outs] } {
  set regs [all_registers]
  if { [llength $regs] } {
    set_max_delay 0 -from $regs -to [get_ports $outs]
  }
  set_max_delay 0 -from $clocks -to [get_ports $outs]
  if { [llength $ins] } {
    set_max_delay [expr { -$::ledger_apart }] -from [get_ports $ins] -to [get_ports $outs]
  }
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
set built [lindex [ledger_split "as built" [ledger_slacks $outs]] 1]
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

set rc_file [expr {
  [env_var_exists_and_non_empty LAYER_PARASITICS_FILE]
  ? $::env(LAYER_PARASITICS_FILE) : "$::env(PLATFORM_DIR)/setRC.tcl"
}]
lassign [ledger_reading routed $ins $outs $arcs_k] \
  routed_ft routed_was_outs routed_feeds routed_was_ins routed_arcs
hr_wires_zero global_routing
lassign [ledger_reading "zero wire" $ins $outs $arcs_k] \
  zero_ft zero_was_outs zero_feeds zero_was_ins zero_arcs
# the halves: the inputs' paths to the outputs out of every slack
if { [llength $ins] && [llength $outs] } {
  set_false_path -from [get_ports $ins] -to [get_ports $outs]
}
set zero_ins [ledger_slacks $ins]
set zero_launches [ledger_slacks $outs]
ledger_phase "zero wire: launches, captures"
hr_wires_back $rc_file global_routing
set routed_ins [ledger_slacks $ins]
set launches [ledger_slacks $outs]
ledger_phase "routed: launches, captures"
foreach {what halves} [list "routed, inputs" $routed_ins "routed, outputs" $launches \
  "zero wire, inputs" $zero_ins "zero wire, outputs" $zero_launches] {
  ledger_short $what $halves
}
# the wires are back: every half read before they went reads the same
set same [expr {
  [ledger_same "the wires did not come back" $routed_was_outs $launches]
  + [ledger_same "the wires did not come back" $routed_was_ins $routed_ins]
}]
ledger_same "the zero-wire reading moved" $zero_was_outs $zero_launches
ledger_same "the zero-wire reading moved" $zero_was_ins $zero_ins
if { !$same } {
  puts "crossing_ledger: WARNING: a feed-through passes every port: that the wires\
    came back after the zero-wire reading is not checked"
}

# Each reading lists every feed-through, and the wires change no path
set arcs {}
foreach pair [lsort -unique [concat [dict keys $routed_arcs] [dict keys $zero_arcs]]] {
  lassign $pair i o
  if { ![dict exists $routed_arcs $pair] || ![dict exists $zero_arcs $pair] } {
    lappend ::ledger_errors [list 47 "feed-through $i to $o is in one reading only"]
    continue
  }
  lappend arcs [list $i $o [dict get $routed_arcs $pair] [dict get $zero_arcs $pair]]
}

# the boundary's budgets: the pins over them, counted and named
set misses {}
set over_total 0
foreach {kind var halves} [list \
  in2reg LEDGER_IN2REG_PS $routed_ins \
  reg2out LEDGER_REG2OUT_PS $launches \
  in2out LEDGER_IN2OUT_PS $routed_ft] {
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

# The ledger's lines: its header and comments, and its pins.
set head {}
lappend head "# part $part clock [get_name $clock] period\
  [format %.2f [ledger_ps [$clock period]]] clk_slew\
  [format %.2f [ledger_ps [sta::time_ui_sta $clk_slew]]] skew $skew arcs_k $arcs_k\
  feeds [dict size $routed_feeds]"
lappend head "# ps, routed and zero-wire: out <pin> <L> <L zero> <ft> <ft zero> <lat> <flags>;\
  in <pin> <C> <C zero> <flags>; feed <in> <F> <F zero>; arc <in> <out> <d> <d zero>"
if { [env_var_exists_and_non_empty LEDGER_NOTE] } {
  lappend head "# note $::env(LEDGER_NOTE)"
}
if { [llength $clocks] > 1 } {
  lappend head "# note [llength $clocks] clocks: a launch is the slowest of any of them"
}
if { $::ledger_mcp } {
  lappend head "# note the SDC has a set_multicycle_path: every output is `mcp`"
}
set head [concat $head $misses]
set body {}
foreach o $outs {
  set launch [dict get $launches $o]
  set lat ""
  if { $launch ne "" && [dict exists $built $o] && [dict get $built $o] ne "" } {
    set lat [expr { [dict get $built $o] - $launch }]
  }
  set feed [expr { [dict exists $routed_ft $o] ? [dict get $routed_ft $o] : "" }]
  set feed_zero [expr { [dict exists $zero_ft $o] ? [dict get $zero_ft $o] : "" }]
  lappend body "out $o [ledger_field $launch] [ledger_field [dict get $zero_launches $o]]\
    [ledger_field $feed] [ledger_field $feed_zero] [ledger_field $lat]\
    [expr { $::ledger_mcp ? "mcp" : "-" }]"
}
foreach i $ins {
  lappend body "in $i [ledger_field [dict get $routed_ins $i]] [ledger_field [dict get $zero_ins $i]] -"
}
foreach i $ins {
  if { ![dict exists $routed_feeds $i] } { continue }
  if { ![dict exists $zero_feeds $i] } {
    lappend ::ledger_errors [list 47 "input $i has a feed-through as routed and\
      none at zero wire"]
    continue
  }
  lappend body "feed $i [ledger_field [dict get $routed_feeds $i]] [ledger_field [dict get $zero_feeds $i]]"
}
foreach arc $arcs {
  lassign $arc i o d z
  lappend body "arc $i $o [ledger_field $d] [ledger_field $z]"
}

proc ledger_write { file lines } {
  set f [open $file w]
  foreach line $lines {
    puts $f $line
  }
  close $f
}
# on disk before anything that can stop the run: a ledger its checks have
# not passed, beside the one they will
set unchecked $::env(LEDGER_OUT).unchecked
ledger_write $unchecked [concat $head $body]
if { [llength $::ledger_errors] } {
  foreach e [lrange $::ledger_errors 0 9] {
    puts "crossing_ledger: [lindex $e 1]"
  }
  lassign [lindex $::ledger_errors 0] code message
  utl::error FLW $code "crossing_ledger: $message ([llength $::ledger_errors] such; the\
    readings are in $unchecked)"
}
ledger_phase "checked and on disk"

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
# an output: its 16 slowest paths from registers, and the registers they
# start at
if { [llength $spot_outs] } {
  set by_out [dict create]
  set n 16
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
if { [llength $spots] } {
  ledger_phase "spot checks"
}

ledger_write $::env(LEDGER_OUT) [concat $head $spot_lines $body]
file delete $unchecked

puts "crossing_ledger: $part: [llength $outs] outputs, [llength $ins] inputs,\
  [llength $arcs] feed-throughs from [dict size $routed_feeds] inputs to\
  [dict size $routed_ft] outputs"
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
