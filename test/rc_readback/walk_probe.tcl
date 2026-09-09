# Where the unit-RC calibration's memory goes.
#
# `make write_rc` (docs/tutorials/SetRC.md) extracts per-segment parasitics and
# then reads them back through the ODB Tcl API to write the CSV the fit
# consumes. This probe separates the three costs -- loading the design,
# extracting, and reading back -- and reports RSS as the read-back proceeds, so
# growth that is proportional to segments visited is visible as it happens
# rather than inferred from a final number.
#
# WALK_MODE selects how much of the read-back loop runs, so the growth can be
# attributed to one accessor by difference:
#
#   full     what write_segments_rc_csv does
#   nocap    drops getTotalCapacitance
#   noshape  drops getShape / getTechLayer
#   rsegs    getRSegs only, no accessors
#
# Rows go to /dev/null: this measures the read-back, not the file write.
#
# It deliberately does not run estimate_parasitics or read_spef. Neither feeds
# the segment walk; write_rc.tcl performs them for its net-level comparison
# CSV, and skipping them takes both time and memory off every iteration here.

proc rss { label } {
  set f [open /proc/self/status r]
  set d [read $f]
  close $f
  regexp {VmRSS:\s+(\d+) kB} $d -> cur
  regexp {VmHWM:\s+(\d+) kB} $d -> hwm
  puts [format "RCPROBE %-34s rss=%7.2f GB  hwm=%7.2f GB" \
    $label [expr { $cur / 1048576.0 }] [expr { $hwm / 1048576.0 }]]
  flush stdout
}

set mode [expr { [info exists ::env(WALK_MODE)] ? $::env(WALK_MODE) : "full" }]
set report_every [expr { [info exists ::env(WALK_REPORT_NETS)]
                         ? $::env(WALK_REPORT_NETS) : 10000 }]

rss "start"

source $::env(SCRIPTS_DIR)/load.tcl
load_design 6_final.odb 6_final.sdc
rss "after load_design"

extract_parasitics -ext_model_file $::env(RCX_RULES) -max_res 0 -no_merge_via_res
rss "after extract_parasitics"

puts "RCPROBE walk mode=$mode report_every=$report_every"

set stream [open /dev/null "w"]
set net_i 0
set seg_i 0

foreach db_net [[ord::get_db_block] getNets] {
  set type [$db_net getSigType]

  if { !([string equal $type "CLOCK"] || [string equal $type "SIGNAL"]) } {
    continue
  }

  set wire [$db_net getWire]

  if { $wire eq "NULL" } {
    continue
  }

  set net_name [$db_net getName]
  set net_type [expr { $type eq "CLOCK" ? "clock" : "signal" }]

  foreach rseg [$db_net getRSegs] {
    incr seg_i

    if { $mode eq "rsegs" } {
      continue
    }

    if { $mode ne "noshape" } {
      set shape [$wire getShape [$rseg getShapeId]]

      if { ![$shape isSegment] } {
        continue
      }

      set layer [[$shape getTechLayer] getName]
      set width [$shape getDX]
      set height [$shape getDY]
      set length_um [ord::dbu_to_microns [expr { max($width, $height) }]]
    } else {
      set layer "-"
      set length_um 1.0
    }

    set resistance [$rseg getResistance 0]

    if { $mode ne "nocap" } {
      set capacitance [$rseg getTotalCapacitance 0]
    } else {
      set capacitance 0.0
    }

    puts $stream [format "%s,%s,%s,%.3e,%.3e,%.3e" \
      $net_name $net_type $layer $length_um $resistance $capacitance]
  }

  incr net_i

  if { $net_i % $report_every == 0 } {
    rss "walked nets=$net_i segs=$seg_i"
  }
}

close $stream
rss "walk done nets=$net_i segs=$seg_i"
