# The whole design timed flat: the parent's netlist with every block's real
# cells and wires (sta_part.tcl's pieces) in place of the block's abstract,
# so a path starts and ends at a real flop wherever it is. Run by OpenSTA:
#   STA_PARENT=XSTile STA_PARTS="XSTile Frontend ..." STA_DIR=<dir with each
#   part's .v, .spef, .sdc, _libs.tar> STA_OUT=<report> sta -exit sta_flat.tcl
# Every reg2reg endpoint is classified by where its worst path runs: its
# start and end, in the parent or inside a block, and any block it passes
# through on the way (STA_CLASSIFY=<classify.tcl>).
set dir $::env(STA_DIR)
set parent $::env(STA_PARENT)
set parts $::env(STA_PARTS)
set blocks [lsearch -all -inline -not -exact $parts $parent]

# every part's liberty once, except a block's own abstract: its cells are
# the block's netlist now
set libdir [file join $dir libs]
file mkdir $libdir
foreach part $parts { exec tar -xf [file join $dir ${part}_libs.tar] -C $libdir }
foreach lib [lsort [glob -directory $libdir *]] {
  set base [file tail $lib]
  if { [lsearch -exact [lmap b $blocks { string cat $b _typ.lib }] $base] >= 0 } { continue }
  read_liberty $lib
}
foreach part $parts { read_verilog [file join $dir $part.v] }
link_design $parent
read_sdc [file join $dir $parent.sdc]
# reduced as read: a full RC network per net of the whole design does not
# fit; the reduced model is what estimate_parasitics gives the flow's timing
# STA_WIRES=0 times the same netlist without wires: each path's logic alone
set wires [expr { ![info exists ::env(STA_WIRES)] || $::env(STA_WIRES) }]
if { $wires } { read_spef -reduce [file join $dir $parent.spef] }
set where {}
foreach b $blocks {
  set insts [get_cells -hierarchical -filter "ref_name == $b"]
  if { [llength $insts] != 1 } { error "sta_flat: $b has [llength $insts] instances in $parent, want 1" }
  set path [get_full_name [lindex $insts 0]]
  lappend where $path $b
  if { $wires } { read_spef -reduce -path $path [file join $dir $b.spef] }
}
set_propagated_clock [all_clocks]

set p [get_property [lindex [all_clocks] 0] period]
# register to register over the whole linked design: the parent's SDC lists
# the parent's own registers in its reg2reg group (write_sdc expands
# all_registers when the parent is written), so a flop inside a block is no
# group's start or end; these are every flop's clock and data pins
set r2r [list -from [all_registers -clock_pins] -to [all_registers -data_pins]]
set out {}
# the worst path as values: the next find_timing_paths frees its path ends
set w [lindex [find_timing_paths {*}$r2r -sort_by_slack -group_path_count 1] 0]
set worst_slack [get_property $w slack]
lappend out [format "reg2reg %8.0f ps  %s -> %s" $worst_slack \
  [get_full_name [get_property $w startpoint]] [get_full_name [get_property $w endpoint]]]
unset w
set kpi [format "reg2reg min period %.0f ps" [expr { $p - $worst_slack }]]
# the KPI first, so a histogram that does not finish still leaves it
set f [open $::env(STA_OUT) w]
puts $f [join [concat $out [list $kpi]] "\n"]
close $f

# every reg2reg endpoint's period (a block's own endpoints are those its
# interface logic model keeps: the flops at its boundary), by the class of
# its worst path, 10 ps bins: within the parent or a block, from one part to
# another, or through a block it neither starts nor ends in
# (//tools/headroom:classify.tcl)
source $::env(STA_CLASSIFY)
set out [concat $out [hr_classes $where $parent 10 worst]]
lappend out $kpi
set f [open $::env(STA_OUT) w]
puts $f [join $out "\n"]
close $f
# each class's worst path, cell by cell
if { [info exists ::env(STA_PATHS)] } {
  set f [open $::env(STA_PATHS) w]
  close $f
  foreach c [lsort [array names worst]] {
    lassign $worst($c) slack from to
    set f [open $::env(STA_PATHS) a]
    puts $f "### class $c worst [format %.0f [expr { $p - $slack }]] ps"
    close $f
    report_checks -from [get_pins $from] -to [get_pins $to] -format full_clock_expanded \
      -fields {fanout cap slew} -digits 0 >> $::env(STA_PATHS)
  }
}

# Every endpoint above STA_CROSSINGS_PS, with each part its worst path
# runs through: the net it enters the part by, the net it leaves by and the
# time spent inside, the stretch a surgery would move (STA_CROSSINGS, one
# line per endpoint: period, class, then part:entry_net:exit_net:ps per
# stretch, then M= the modules its cells sit in, six levels deep). A
# block's nets are named inside the block: the first and last leaf pin of
# its stretch sit on the nets of the ports the path crosses.
proc sta_local_net { pin part where } {
  set nets [get_nets -quiet -of_objects $pin]
  if { [llength $nets] == 0 } { return "-" }
  set name [get_full_name [lindex $nets 0]]
  foreach { path b } $where {
    if { $b eq $part && [string first "$path/" $name] == 0 } {
      return [string range $name [string length "$path/"] end]
    }
  }
  return $name
}
if { [info exists ::env(STA_CROSSINGS)] } {
  set above $::env(STA_CROSSINGS_PS)
  set f [open $::env(STA_CROSSINGS) w]
  foreach t [find_timing_paths {*}$r2r -endpoint_path_count 1 \
               -group_path_count [sta::endpoint_count] -slack_max [expr { $p - $above }]] {
    set stretches {}
    set cur ""
    array unset mods
    array unset logic
    # W= the path's wire delay: the arrival gained from a cell's output pin
    # to the next cell's input, summed (the rest is the cells' own delay)
    set wire 0.0
    set prev_out ""
    foreach point [get_property $t points] {
      set pin [get_property $point pin]
      set at [get_property $point arrival]
      if { $prev_out ne "" && [get_property $pin direction] eq "input" } {
        set wire [expr { $wire + $at - $prev_out }]
      }
      set prev_out [expr { [get_property $pin direction] eq "output" ? $at : "" }]
      # the module the pin's cell sits in, to six levels: the carve study's
      # unit (crossings.py folds it further)
      set comps [lrange [split [get_full_name $pin] /] 0 end-2]
      set mods([join [lrange $comps 0 5] /]) 1
      # L= the modules a logic cell of the path sits in: a repeater (a
      # buffer or an inverter) is wire, and may sit anywhere
      set ref [get_property [get_cells -of_objects $pin] ref_name]
      if { ![info exists is_rep($ref)] } {
        set lc [lindex [get_lib_cells -quiet */$ref] 0]
        set is_rep($ref) [expr { $lc ne "" && ([get_property $lc is_buffer] || [get_property $lc is_inverter]) }]
      }
      if { !$is_rep($ref) } { set logic([join [lrange $comps 0 5] /]) 1 }
      set part [hr_part_of [get_full_name $pin] $where $parent]
      if { $part ne $cur } {
        if { $cur ne "" } { lappend stretches [list $cur $entry $last $entry_at $last_at] }
        set cur $part
        set entry $pin
        set entry_at $at
      }
      set last $pin
      set last_at $at
    }
    lappend stretches [list $cur $entry $last $entry_at $last_at]
    set fields [list [format %.0f [expr { $p - [get_property $t slack] }]] \
      [hr_class [lmap s $stretches { lindex $s 0 }] $parent]]
    foreach s $stretches {
      lassign $s part entry last entry_at last_at
      lappend fields [format "%s:%s:%s:%.0f" $part [sta_local_net $entry $part $where] \
        [sta_local_net $last $part $where] [expr { $last_at - $entry_at }]]
    }
    lappend fields "M=[join [lsort [array names mods]] ,]"
    lappend fields "L=[join [lsort [array names logic]] ,]"
    lappend fields [format "W=%.0f" $wire]
    lappend fields "E=[get_full_name [get_property $t endpoint]]"
    puts $f [join $fields "\t"]
  }
  close $f
}

# Every module's cell area, at each of six levels (STA_MODULE_AREA, one line
# per module: path, cells, um2): what a carve puts in each macro.
if { [info exists ::env(STA_MODULE_AREA)] } {
  array unset area
  array unset count
  array unset cell_area
  foreach c [get_cells -hierarchical *] {
    if { [get_property $c is_hierarchical] } { continue }
    set ref [get_property $c ref_name]
    if { ![info exists cell_area($ref)] } {
      set lc [lindex [get_lib_cells -quiet */$ref] 0]
      set cell_area($ref) [expr { $lc eq "" ? 0.0 : [get_property $lc area] }]
    }
    set comps [lrange [split [get_full_name $c] /] 0 end-1]
    for { set d 1 } { $d <= [expr { min(6, [llength $comps]) }] } { incr d } {
      set m [join [lrange $comps 0 [expr { $d - 1 }]] /]
      if { [info exists area($m)] } {
        set area($m) [expr { $area($m) + $cell_area($ref) }]
        incr count($m)
      } else {
        set area($m) $cell_area($ref)
        set count($m) 1
      }
    }
  }
  set f [open $::env(STA_MODULE_AREA) w]
  foreach m [lsort [array names area]] {
    puts $f [format "%s\t%d\t%.1f" $m $count($m) $area($m)]
  }
  close $f
}

# Each listed hierarchical instance's port bits (STA_PORTS_OF, a list of
# instance paths; STA_PORTS, one line per instance: path, bits): the pins a
# macro carved at that boundary would have.
if { [info exists ::env(STA_PORTS)] } {
  set f [open $::env(STA_PORTS) w]
  foreach inst $::env(STA_PORTS_OF) {
    set pins [get_pins -quiet $inst/*]
    puts $f [format "%s\t%d" $inst [llength $pins]]
  }
  close $f
}
