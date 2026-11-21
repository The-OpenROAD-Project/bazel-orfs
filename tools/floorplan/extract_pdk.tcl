# A platform's wire model for the global floorplan planner, as a
# tab-separated dump pdk_json.py turns into pdk.json:
#
#   platform <name>
#   site  <w_um> <h_um>
#   io    <IO_PLACER_H> <IO_PLACER_V>
#   range <MIN_ROUTING_LAYER> <MAX_ROUTING_LAYER>
#   layer <name> <dir> <pitch_um> <width_um> <r_ohm_per_um> <c_ff_per_um>
#   wire  <layer> <buffer> <length_um> <delay_ps>   a buffer driving the
#         layer's wire into a copy of itself (the resizer's bufferWireDelay)
#   via   <cut layer> <r_ohm>
#
# The layer RC is what the platform's setRC.tcl installs, the same the
# flow's parasitics estimates use. Any synthesised design of the platform
# serves: only its libraries and technology are read.
#
#   EXTRACT_OUT      the dump
source $::env(SCRIPTS_DIR)/load.tcl
load_design 1_synth.odb

set out [open $::env(EXTRACT_OUT) w]
set tech [ord::get_db_tech]
set dbu [$tech getDbUnitsPerMicron]
proc um { v } { return [format %.4f [expr { double($v) / $::dbu }]] }

puts $out "platform\t$::env(PLATFORM)"
foreach lib [[ord::get_db] getLibs] {
  set s [$lib findSite $::env(PLACE_SITE)]
  if { $s ne "NULL" } { puts $out "site\t[um [$s getWidth]]\t[um [$s getHeight]]" }
}
puts $out "io\t$::env(IO_PLACER_H)\t$::env(IO_PLACER_V)"
puts $out "range\t$::env(MIN_ROUTING_LAYER)\t$::env(MAX_ROUTING_LAYER)"

set scene [sta::cmd_scene]
set routing {}
foreach layer [$tech getLayers] {
  set type [$layer getType]
  if { $type eq "ROUTING" } {
    set dir [expr { [$layer getDirection] eq "HORIZONTAL" ? "H" : "V" }]
    set r [expr { [est::layer_resistance $layer $scene] * 1e-6 }]
    set c [expr { [est::layer_capacitance $layer $scene] * 1e-6 * 1e15 }]
    puts $out "layer\t[$layer getName]\t$dir\t[um [$layer getPitch]]\t[um [$layer getWidth]]\t[format %.6g $r]\t[format %.6g $c]"
    lappend routing $layer
  } elseif { $type eq "CUT" } {
    set r [est::layer_resistance $layer $scene]
    puts $out "via\t[$layer getName]\t[format %.6g $r]"
  }
}

# every buffer the libraries have
set buffers {}
foreach cell [get_lib_cells *] {
  if { [get_property $cell is_buffer] } {
    lappend buffers $cell
  }
}
# buffer_wire_delay needs the resizer's block, which this initialises
rsz::find_max_wire_length
set lengths {}
for { set l 5.0 } { $l <= 3000.0 } { set l [expr { $l * 1.25 }] } { lappend lengths $l }
foreach layer $routing {
  set r [est::layer_resistance $layer $scene]
  set c [est::layer_capacitance $layer $scene]
  if { $r <= 0 || $c <= 0 } { continue }
  set_wire_rc -signal -layer [$layer getName]
  foreach cell $buffers {
    foreach l $lengths {
      set d [rsz::buffer_wire_delay $cell [expr { $l * 1e-6 }]]
      puts $out "wire\t[$layer getName]\t[get_name $cell]\t[format %.3f $l]\t[format %.3f [expr { $d * 1e12 }]]"
    }
  }
}
close $out
puts "extract_pdk: written to $::env(EXTRACT_OUT)"
