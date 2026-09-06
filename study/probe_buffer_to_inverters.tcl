# Is a design suitable for studying OpenROAD PR 10662?
#
# The move replaces one buffer with a pair of cascaded inverters placed at
# the thirds of the fanout. BufferToInvertersGenerator::generate rejects a
# target unless ALL of the following hold, so "suitable" is not "big" or
# "slow", it is these conditions being satisfiable at all:
#
#   1. A USABLE INVERTER EXISTS -- not dont_use, a link cell, with buffer
#      ports, and -- when -match_cell_footprint is on -- carrying the same
#      cell_footprint as the buffer being replaced. This is a property of
#      the PLATFORM, not the design, and it is the gate that decides
#      whether anything can happen at all. It costs no flow run to
#      evaluate, so it runs first and can end the study for a platform.
#   2. BUFFERS ON VIOLATING PATHS at path_index >= 2. The move only ever
#      looks at a driver that is a liberty buffer, two or more vertices
#      into a path with negative slack.
#   3. SOMETHING TO REPAIR. Zero violating endpoints means repair_timing
#      has no targets and every arm measures the same nothing. A design
#      that has closed is excluded, not reported as "showed no effect".
#
# Reported per design so the choice of designs is a measurement rather
# than an intuition -- the failure mode of the previous study, where a
# design picked by convenience scored 17.5% and showed nothing.

source $::env(SCRIPTS_DIR)/load.tcl
load_design 3_place.odb 3_place.sdc

set ::probe_paths 200
if { [info exists ::env(PROBE_PATHS)] && $::env(PROBE_PATHS) ne "" } {
  set ::probe_paths $::env(PROBE_PATHS)
}

set block [ord::get_db_block]

# ---------------------------------------------------------------------------
# 1. The platform gate: are there inverters the generator would accept?
#
# match_cell_footprint is a repair_timing argument, not a db property, so
# it is read from the environment the way ORFS passes it -- see
# repair_timing_helper in ORFS's util.tcl, which forwards
# MATCH_CELL_FOOTPRINT as -match_cell_footprint.
# ---------------------------------------------------------------------------
set match_footprint 0
if { [info exists ::env(MATCH_CELL_FOOTPRINT)]
     && $::env(MATCH_CELL_FOOTPRINT) ne "" } {
  set match_footprint 1
}

# Liberty cell -> footprint, via the OpenSTA object. Cells with no
# footprint are exempt from the filter, exactly as the generator's
# !empty() guards make them.
proc cell_footprint { cell } {
  if { [catch { set fp [$cell footprint] }] } {
    return ""
  }
  return $fp
}

proc cell_is { cell what } {
  if { [catch { set v [$cell $what] }] } {
    return 0
  }
  return $v
}

set buffer_footprints [dict create]
set inverter_footprints [dict create]
set n_buffers 0
set n_inverters 0

foreach cell [get_lib_cells -quiet *] {
  if { [cell_is $cell is_buffer] } {
    incr n_buffers
    dict set buffer_footprints [cell_footprint $cell] 1
  }
  if { [cell_is $cell is_inverter] } {
    if { [get_property $cell dont_use] } {
      continue
    }
    incr n_inverters
    dict set inverter_footprints [cell_footprint $cell] 1
  }
}

# The generator picks ONE inverter per buffer, so the gate is: for some
# buffer footprint, does a usable inverter share it (or is either side
# unlabelled)?
set gate_open 0
if { !$match_footprint } {
  set gate_open [expr { $n_inverters > 0 }]
} else {
  foreach bf [dict keys $buffer_footprints] {
    foreach inv_f [dict keys $inverter_footprints] {
      if { $bf eq "" || $inv_f eq "" || $bf eq $inv_f } {
        set gate_open 1
      }
    }
  }
}

# An assertion, not a print. A probe whose liberty walk silently found
# nothing would report "no usable inverters" for every platform and look
# like a finding rather than a broken query.
if { $n_buffers == 0 } {
  error "probe found no liberty buffers: the lib cell walk is broken,\
         not the platform"
}

# ---------------------------------------------------------------------------
# 3. Is there anything to repair?
# ---------------------------------------------------------------------------
set wns [sta::worst_slack -max]
set tns [sta::total_negative_slack]
set unit "[sta::unit_scale_abbreviation time]s"

# ---------------------------------------------------------------------------
# 2. Buffers on violating paths, at depth >= 2.
#
# Walked over the worst N violating paths rather than the whole netlist:
# the move is offered targets from the repair worklist, so a buffer census
# of the design as a whole would over-count by orders of magnitude.
# ---------------------------------------------------------------------------
set paths_walked 0
set path_buffers 0
set path_buffers_deep 0
set path_pins 0

foreach path [find_timing_paths -path_delay max -slack_max 0 \
  -group_count $::probe_paths] {
  incr paths_walked
  set idx 0
  foreach pt [$path points] {
    set pin [$pt pin]
    incr path_pins
    set inst [sta::pin_instance $pin]
    if { $inst ne "NULL" && $inst ne "" } {
      set cell [sta::instance_property $inst liberty_cell]
      if { $cell ne "NULL" && $cell ne "" && [cell_is $cell is_buffer] } {
        incr path_buffers
        if { $idx >= 2 } {
          incr path_buffers_deep
        }
      }
    }
    incr idx
  }
}

# The path walk is the part most likely to break silently against an
# OpenSTA API change: a renamed accessor returns nothing, every count
# stays zero, and the design looks unsuitable rather than unmeasured. If
# the design has negative slack there MUST be violating paths to walk.
if { $wns < 0 && $paths_walked == 0 } {
  error "probe walked 0 violating paths on a design with WNS $wns$unit:\
         find_timing_paths returned nothing, which is a broken query, not\
         a suitable-design verdict"
}
if { $paths_walked > 0 && $path_pins == 0 } {
  error "probe walked $paths_walked paths but saw 0 pins: the path point\
         accessor is not returning points"
}

set report [list \
  design $::env(STUDY_DESIGN) \
  time_unit $unit \
  wns $wns \
  tns $tns \
  match_cell_footprint $match_footprint \
  liberty_buffers $n_buffers \
  usable_inverters $n_inverters \
  buffer_footprints [join [dict keys $buffer_footprints] ","] \
  inverter_footprints [join [dict keys $inverter_footprints] ","] \
  gate_open $gate_open \
  violating_paths_walked $paths_walked \
  path_pins $path_pins \
  path_buffers $path_buffers \
  path_buffers_depth_ge2 $path_buffers_deep]

puts "PROBE: $report"
set fd [open $::env(RESULTS_OUT)/probe.txt w]
puts $fd $report
close $fd
