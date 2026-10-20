# Repair headroom across a parent and its blocks: the parent's netlist with
# every block's real cells and wires in place of its abstract, as each part
# was at its own stage (sta_part.tcl), timed in OpenSTA, then the
# measurements of tools/odb_debug/headroom.tcl on the whole. A block
# instantiated more than once gets its parasitics at every instance.
#
#   STA_DIR=<dir with each part's .v (blocks prefixed by sta_prefix.py),
#   .spef, .sdc, _libs.tar> STA_PARENT=<module> STA_PARTS="<parent> <block>..."
#   STA_WIRES=1|0 HR_TCL=<headroom.tcl> HR_ENDS=0 HR_TARGET=0 HR_OUT=<file>
#   [HR_CLASSES=<classify.tcl>] sta -exit headroom_flat.tcl
#
# STA_WIRES=0 reads no SPEF: the period then is the zero-wire floor, and
# that is all it reports. The output is one JSON object; what it means:
# .claude/skills/repair-headroom/SKILL.md.
source $::env(HR_TCL)
set dir $::env(STA_DIR)
set parent $::env(STA_PARENT)
set parts $::env(STA_PARTS)
set blocks [lsearch -all -inline -not -exact $parts $parent]
set ends [expr { [info exists ::env(HR_ENDS)] ? $::env(HR_ENDS) : 0 }]
set wires [expr { ![info exists ::env(STA_WIRES)] || $::env(STA_WIRES) }]
if { [info exists ::env(HR_TARGET)] } { set ::hr_target $::env(HR_TARGET) }

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

# each block instance's path, for the parasitics and for the split of
# every gain into the parent's and the blocks'
set paths {}
foreach b $blocks {
  set insts [get_cells -hierarchical -filter "ref_name == $b"]
  if { ![llength $insts] } { error "headroom_flat: $b has no instance in $parent" }
  foreach inst $insts { lappend paths [get_full_name $inst] }
}
# reduced as read: a full RC network per net of a whole core does not fit.
# A cell swap deletes the reduced models of the nets driving it, so the VT
# measurement reads the SPEF again after its swaps and after its undo.
proc hr_read_spefs {} {
  global dir parent blocks
  read_spef -reduce [file join $dir $parent.spef]
  foreach b $blocks {
    foreach inst [get_cells -hierarchical -filter "ref_name == $b"] {
      read_spef -reduce -path [get_full_name $inst] [file join $dir $b.spef]
    }
  }
}
if { $wires } {
  hr_read_spefs
  set ::hr_parasitics hr_read_spefs
}
set_propagated_clock [all_clocks]

# HR_CLASSES names classify.tcl: classify every reg2reg endpoint's worst
# path by where it runs (orfs_headroom's <name>_classes) and stop
if { [info exists ::env(HR_CLASSES)] && $::env(HR_CLASSES) ne "" } {
  source $::env(HR_CLASSES)
  set where {}
  foreach b $blocks {
    foreach inst [get_cells -hierarchical -filter "ref_name == $b"] {
      lappend where [get_full_name $inst] $b
    }
  }
  set f [open $::env(HR_OUT) w]
  puts $f [join [hr_classes $where $parent] "\n"]
  close $f
  exit
}

proc jstr { x } {
  return "\"[string map {\\ \\\\ \" \\\"} $x]\""
}

proc json { d } {
  set parts {}
  dict for {k v} $d {
    if { [string match "vts_*" $k] || [string match "top_*" $k] } {
      lappend parts "\"$k\":\[[join [lmap x $v { jstr $x }] ,]\]"
    } elseif { [string is double -strict $v] } {
      lappend parts "\"$k\":$v"
    } else {
      lappend parts "\"$k\":[jstr $v]"
    }
  }
  return "{[join $parts ,]}"
}

set t0 [clock seconds]
set out [list "\"wires\":$wires" "\"blocks\":[llength $paths]" "\"period\":[json [hr_period]]"]
# written as each measurement finishes, so a run stopped early keeps them
proc emit { out } {
  set f [open $::env(HR_OUT) w]
  puts $f "{[join $out ,]}"
  close $f
}
emit $out
if { $wires } {
  lappend out "\"floor_cycles\":[json [hr_floor_cycles $ends]]"
  emit $out
  lappend out "\"skew\":[json [hr_skew $ends 1 60 $paths]]"
  emit $out
  lappend out "\"floor_retime\":[json [hr_floor_retime $ends 60 $paths]]"
  emit $out
  lappend out "\"vt\":[json [hr_vt $ends $paths 0]]"
  emit $out
  lappend out "\"vt_parent_only\":[json [hr_vt $ends $paths 1]]"
}
lappend out "\"seconds\":[expr { [clock seconds] - $t0 }]"
emit $out
