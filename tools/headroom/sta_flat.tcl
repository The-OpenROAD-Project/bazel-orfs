# A parent timed with every block's interface logic in place of the block's
# abstract (orfs_flow's <parent>_ilm_sta, private/ilm.bzl): the parent's
# netlist and parasitics, and each block's interface logic model
# (sta_part.tcl with STA_ILM=1) with its own parasitics, linked in OpenSTA,
# so a path starts and ends at a real flop wherever it is. Run by OpenSTA:
#   STA_DIR=<dir with each part's .v (blocks prefixed by sta_prefix.py),
#   .spef, .sdc, _libs.tar> STA_PARENT=<module> STA_PARTS="<parent> <block>..."
#   STA_WIRES=1|0 STA_CLASSIFY=<classify.tcl> STA_OUT=<report>
#   STA_PATHS=<paths> sta -exit sta_flat.tcl
# STA_OUT: the worst reg2reg path, every reg2reg endpoint's period by the
# class of its worst path (classify.tcl), the min period; STA_PATHS: each
# class's worst path, cell by cell. A block instantiated more than once gets
# its parasitics at every instance. STA_WIRES=0 reads no SPEF: each path's
# logic alone.
set dir $::env(STA_DIR)
set parent $::env(STA_PARENT)
set parts $::env(STA_PARTS)
set blocks [lsearch -all -inline -not -exact $parts $parent]

# every part's liberty once, except a block's own abstract: its cells are
# the block's netlist now
set libdir [file join $dir libs]
file mkdir $libdir
foreach part $parts { exec tar -xf [file join $dir ${part}_libs.tar] -C $libdir }
set abstracts [lmap b $blocks { string cat $b _typ.lib }]
foreach lib [lsort [glob -directory $libdir *]] {
  if { [lsearch -exact $abstracts [file tail $lib]] >= 0 } { continue }
  read_liberty $lib
}
foreach part $parts { read_verilog [file join $dir $part.v] }
link_design $parent
read_sdc [file join $dir $parent.sdc]
set wires $::env(STA_WIRES)
# reduced as read: a full RC network per net of a large design does not
# fit; the reduced model is what estimate_parasitics gives the flow's timing
if { $wires } { read_spef -reduce [file join $dir $parent.spef] }
set where {}
foreach b $blocks {
  set insts [get_cells -hierarchical -filter "ref_name == $b"]
  if { ![llength $insts] } { error "sta_flat: $b has no instance in $parent" }
  foreach inst $insts {
    set path [get_full_name $inst]
    lappend where $path $b
    if { $wires } { read_spef -reduce -path $path [file join $dir $b.spef] }
  }
}
set_propagated_clock [all_clocks]

set p [get_property [lindex [all_clocks] 0] period]
# register to register over the whole linked design: the parent's SDC
# lists the parent's own registers in its groups, so a flop inside a block
# is no group's start or end; these are every flop's clock and data pins
set r2r [list -from [all_registers -clock_pins] -to [all_registers -data_pins]]
set out {}
# the worst path as values: the next find_timing_paths frees its path ends
set w [lindex [find_timing_paths {*}$r2r -sort_by_slack -group_path_count 1] 0]
if { $w eq "" } { error "sta_flat: no reg2reg path in $parent" }
set worst_slack [get_property $w slack]
lappend out [format "reg2reg %8.0f ps  %s -> %s" $worst_slack \
  [get_full_name [get_property $w startpoint]] [get_full_name [get_property $w endpoint]]]
unset w
set kpi [format "reg2reg min period %.0f ps" [expr { $p - $worst_slack }]]
# the min period first, so a histogram that does not finish still leaves it
set f [open $::env(STA_OUT) w]
puts $f [join [concat $out [list $kpi]] "\n"]
close $f

# every reg2reg endpoint's period (a block's own endpoints are those its
# interface logic model keeps: the flops at its boundary), by the class of
# its worst path, 10 ps bins
source $::env(STA_CLASSIFY)
set out [concat $out [hr_classes $where $parent 10 worst]]
lappend out $kpi
set f [open $::env(STA_OUT) w]
puts $f [join $out "\n"]
close $f
# each class's worst path, cell by cell
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
