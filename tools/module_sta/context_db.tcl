# Module M's timing context, cut in OpenROAD from the whole design's
# hierarchical database, for an AI loop iterating on M in a dirty lane:
# load the context with read_db -hier, read the new M with read_verilog,
# link_hier_module and replace_hier_module it in (iterate.tcl), and time.
#
#   PSTA_BASE_DB    the whole design, linked with link_design -hier
#   PSTA_M          M's instance path, e.g. inner_bpu/tage
#   PSTA_CONTEXT_DB out: the database with only M and its context left
#   PSTA_EXACT      out: the endpoints outside M whose slack the context
#                   times completely, one pin per line
#   PSTA_STATS      out: cell counts, JSON
#   plus PSTA_LIBS and PSTA_CLOCKS (common.tcl)
#
# The context, all of it real cells, no annotation of any kind:
#   - the fanin of every input of M back to its launching registers;
#   - the fanout of every output of M to its capturing registers, and the
#     whole fanin of every cell on it;
#   - the clock trees, through buffers and clock gates, of every register
#     kept and of M;
#   - every other load of a net a kept cell drives (a side load: its
#     output pins disconnected), so each kept cell's load is its load in
#     the whole design.
# Every other leaf instance outside M is deleted. M's endpoints and those
# of the capturing registers (PSTA_EXACT) are then timed exactly as in the
# whole design; after synthesis the clocks are ideal and there are no
# wires. The walks cross constant-disabled arcs (-trace_arcs all), so what
# holds a constant in the whole design holds it in the context.

source [file join [file dirname [info script]] common.tcl]

psta_read_libs
read_db -hier $::env(PSTA_BASE_DB)
if { ![psta_clocks] } { error "context_db.tcl: no clock port of PSTA_CLOCKS" }
set block [ord::get_db_block]
set mp "$::env(PSTA_M)/"

# every leaf cell by its database id, for the walks between database and
# timer: the timer escapes [ ] in hierarchical names, the database does not
set cells [dict create]
foreach c [get_cells -hierarchical -quiet -filter "is_hierarchical == 0" *] {
  dict set cells [[sta::sta_to_db_inst $c] getId] $c
}
# inside M, by the database's name
proc inside { name } { string equal -length [string length $::mp] $::mp $name }
proc sta_pin { iterm } {
  set c [dict get $::cells [[$iterm getInst] getId]]
  foreach p [get_pins -quiet -of_objects $c] {
    if { [get_property $p lib_pin_name] eq [[$iterm getMTerm] getName] } { return $p }
  }
  return ""
}
# cell sets: database id -> timer cell, never a cell inside M
proc add { var objs } {
  upvar 1 $var d
  foreach o $objs {
    set i [sta::sta_to_db_inst $o]
    if { $i ne "NULL" && ![inside [$i getName]] } { dict set d [$i getId] $o }
  }
}

# M's boundary: the flat nets with pins both inside M and outside it
set m_insts {}
foreach inst [$block getInsts] {
  if { [inside [$inst getName]] } { lappend m_insts $inst }
}
if { ![llength $m_insts] } { error "context_db.tcl: no cell under $::env(PSTA_M)" }
set seen [dict create]
set in_drivers {}
set out_loads {}
foreach inst $m_insts {
  foreach it [$inst getITerms] {
    set net [$it getNet]
    if { $net eq "NULL" || [$net getSigType] in {POWER GROUND} } { continue }
    set id [$net getId]
    if { [dict exists $seen $id] } { continue }
    dict set seen $id 1
    set drv_in 0
    set outs {}
    set loads {}
    foreach o [$net getITerms] {
      set oin [inside [[$o getInst] getName]]
      if { [$o isOutputSignal] } {
        set drv_in $oin
        if { !$oin } { lappend outs $o }
      } elseif { !$oin } {
        lappend loads $o
      }
    }
    if { [llength $outs] } { set in_drivers [concat $in_drivers $outs] }
    if { $drv_in } { set out_loads [concat $out_loads $loads] }
  }
}
set in_pins [lmap it $in_drivers { sta_pin $it }]
set out_pins [lmap it $out_loads { sta_pin $it }]

set core [dict create]
if { [llength $in_pins] } {
  add core [get_cells -of_objects $in_pins]
  add core [get_fanin -to $in_pins -flat -only_cells -trace_arcs all]
}
set fo [dict create]
if { [llength $out_pins] } {
  add fo [get_cells -of_objects $out_pins]
  add fo [get_fanout -from $out_pins -flat -only_cells -trace_arcs all]
}
set core [dict merge $core $fo]
set fo_inputs [get_pins -quiet -of_objects [dict values $fo] -filter "direction == input"]
if { [llength $fo_inputs] } {
  add core [get_fanin -to $fo_inputs -flat -only_cells -trace_arcs all]
}

# the clock trees: get_fanin stops at a register's clock pin, so they are
# walked on the database's flat nets, from each clock pin to its driver and
# on through the driver's clock inputs (a buffer's, a clock gate's CLK),
# never its enable. A register's clock pin by all_registers as well as
# is_clock: a memory macro's need not be is_clock.
set regck [dict create]
foreach p [all_registers -clock_pins] { dict set regck [get_full_name $p] 1 }
set todo {}
foreach c [concat [dict values $core] [lmap i $m_insts { dict get $cells [$i getId] }]] {
  foreach p [get_pins -quiet -of_objects $c -filter "direction == input"] {
    if { [get_property $p is_clock] || [dict exists $regck [get_full_name $p]] } {
      lappend todo [[sta::sta_to_db_pin $p] getNet]
    }
  }
}
set seen [dict create]
while { [llength $todo] } {
  set net [lindex $todo end]
  set todo [lrange $todo 0 end-1]
  if { $net eq "NULL" || [dict exists $seen [$net getId]] } { continue }
  dict set seen [$net getId] 1
  foreach o [$net getITerms] {
    if { ![$o isOutputSignal] } { continue }
    set c [dict get $cells [[$o getInst] getId]]
    add core [list $c]
    foreach p [get_pins -quiet -of_objects $c -filter "direction == input"] {
      if { [get_property $p is_clock] } { lappend todo [[sta::sta_to_db_pin $p] getNet] }
    }
  }
}

# side loads: every other load of a net a kept cell drives
set side [dict create]
foreach id [dict keys $core] {
  foreach it [[sta::sta_to_db_inst [dict get $core $id]] getITerms] {
    if { ![$it isOutputSignal] } { continue }
    set net [$it getNet]
    if { $net eq "NULL" } { continue }
    foreach o [$net getITerms] {
      set oi [$o getInst]
      if { ![$o isOutputSignal] && ![inside [$oi getName]] && ![dict exists $core [$oi getId]] } {
        dict set side [$oi getId] 1
      }
    }
  }
}

# the exactly timed endpoints outside M: the capturing registers in M's fanout
set exact {}
foreach pin [all_registers -data_pins] {
  set i [sta::sta_to_db_inst [get_cells -of_objects $pin]]
  if { $i ne "NULL" && [dict exists $fo [$i getId]] } { lappend exact [get_full_name $pin] }
}
set f [open $::env(PSTA_EXACT) w]
foreach e [lsort $exact] { puts $f $e }
close $f

# cut: side loads keep their inputs only, the rest outside M goes
set removed 0
foreach inst [$block getInsts] {
  set id [$inst getId]
  if { [inside [$inst getName]] || [dict exists $core $id] } { continue }
  if { [dict exists $side $id] } {
    foreach it [$inst getITerms] {
      if { [$it isOutputSignal] } { $it disconnect }
    }
    continue
  }
  odb::dbInst_destroy $inst
  incr removed
}
write_db $::env(PSTA_CONTEXT_DB)

set f [open $::env(PSTA_STATS) w]
puts $f [psta_json [dict create m $::env(PSTA_M) m_cells [llength $m_insts] \
  context_cells [dict size $core] side_loads [dict size $side] removed $removed \
  exact_endpoints [llength $exact] seconds [psta_seconds] peak_mib [psta_peak_mib]]]
close $f
