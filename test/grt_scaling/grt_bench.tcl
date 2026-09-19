# One global-route measurement on a stage ODB, for the grid-scaling study.
#
# Runs through ORFS's `run` target from a deployed _deps tree, so it sees
# the flow's platform, liberty, RC and derates and any OPENROAD_EXE:
#
#   ./make run RUN_SCRIPT=<...>/grt_bench.tcl ODB_FILE=<results>/4_cts.odb \
#       GRT_BENCH_OUT=<abs>/arm.json [GRT_BENCH_ARGS='-congestion_iterations 5'] \
#       [GRT_BENCH_LAYERS='M2 M5'] [GRT_BENCH_PIN_ACCESS=0] [GRT_BENCH_LOAD_ONLY=1]
#       [OPENROAD_EXE=<byo>]
#
# What it records, in one JSON (GRT_BENCH_OUT, required):
#   load_s, pin_access_s, global_route_s      wall time of each step
#   fastroute.*                               FastRoute's own phase timers,
#                                             from the metrics file the
#                                             session writes (utl::metric)
#   wirelength_um                             global_route__wirelength
#   overflow_lines                            the "Final congestion report"
#                                             and any line naming overflow
#   vm_hwm_kb, vm_rss_kb                      peak and final resident memory
#   grid                                      GCell tile size and grid extent
#   args, layers, odb, openroad               what was run, for the report
#
# It never writes the ODB. A timed-out or killed run leaves the JSON of
# the steps that finished (written after each step), so a partial arm is
# still a result.

proc gb_now {} { return [clock milliseconds] }
proc gb_status { key } {
  set f [open /proc/self/status r]
  set v ""
  foreach l [split [read $f] "\n"] {
    if { [regexp "^$key:\\s+(\\d+)" $l -> v] } { break }
  }
  close $f
  return $v
}
proc gb_jstr { s } {
  set s [string map {"\\" "\\\\" "\"" "\\\"" "\n" "\\n" "\r" "" "\t" " "} $s]
  return "\"$s\""
}
proc gb_write {} {
  global gb
  set parts {}
  foreach k [lsort [dict keys $gb]] {
    set v [dict get $gb $k]
    if { [string is double -strict $v] } { lappend parts "[gb_jstr $k]: $v" } \
    elseif { [string index $v 0] eq "\[" || [string index $v 0] eq "\{" } { lappend parts "[gb_jstr $k]: $v" } \
    else { lappend parts "[gb_jstr $k]: [gb_jstr $v]" }
  }
  set f [open $::env(GRT_BENCH_OUT) w]
  puts $f "{[join $parts ,\n]}"
  close $f
}

if { ![info exists ::env(GRT_BENCH_OUT)] } { error "GRT_BENCH_OUT must be set" }
set gb [dict create]
dict set gb odb $::env(ODB_FILE)
dict set gb openroad [expr { [info exists ::env(OPENROAD_EXE)] ? $::env(OPENROAD_EXE) : "" }]
dict set gb args [expr { [info exists ::env(GRT_BENCH_ARGS)] ? $::env(GRT_BENCH_ARGS) : "" }]
dict set gb layers [expr { [info exists ::env(GRT_BENCH_LAYERS)] ? $::env(GRT_BENCH_LAYERS) : "" }]
dict set gb threads [expr { [info exists ::env(NUM_CORES)] ? $::env(NUM_CORES) : "" }]

# FastRoute's phase timers are logger metrics; give them a file.
set metrics_file [file rootname $::env(GRT_BENCH_OUT)].metrics.json
catch { utl::open_metrics $metrics_file }

source $::env(SCRIPTS_DIR)/load.tcl
set t0 [gb_now]
load_design [file tail $::env(ODB_FILE)] [file rootname [file tail $::env(ODB_FILE)]].sdc
dict set gb load_s [expr { ([gb_now] - $t0) / 1000.0 }]
dict set gb insts [llength [[ord::get_db_block] getInsts]]
dict set gb nets [llength [[ord::get_db_block] getNets]]
set die [[ord::get_db_block] getDieArea]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
dict set gb die_um "\[[expr { double([$die dx]) / $dbu }], [expr { double([$die dy]) / $dbu }]\]"
set tile [[ord::get_db_block] getGCellTileSize]
dict set gb grid "\{\"tile_um\": [expr { double($tile) / $dbu }], \"x\": [expr { [$die dx] / $tile }], \"y\": [expr { [$die dy] / $tile }]\}"
dict set gb vm_rss_after_load_kb [gb_status VmRSS]
gb_write

# GRT_BENCH_LOAD_ONLY=1: a smoke test of a deps tree and its ODB, in the
# load time alone -- the JSON has the design, its grid and its memory.
if { [info exists ::env(GRT_BENCH_LOAD_ONLY)] && $::env(GRT_BENCH_LOAD_ONLY) ne "0" } {
  puts "grt_bench: load only, wrote $::env(GRT_BENCH_OUT)"
  return
}

if { [dict get $gb layers] ne "" } {
  lassign [dict get $gb layers] lo hi
  set_routing_layers -signal $lo-$hi -clock $lo-$hi
  dict set gb layers_set "$lo-$hi"
}

# ORFS runs pin_access before global_route; the flow's settings for it
# come from the environment as in global_route.tcl.
if { ![info exists ::env(GRT_BENCH_PIN_ACCESS)] || $::env(GRT_BENCH_PIN_ACCESS) ne "0" } {
  set pa_args {}
  foreach {var flag} {dbProcessNode -db_process_node VIA_IN_PIN_MIN_LAYER -via_in_pin_bottom_layer VIA_IN_PIN_MAX_LAYER -via_in_pin_top_layer} {
    if { [info exists ::env($var)] && $::env($var) ne "" } { lappend pa_args $flag $::env($var) }
  }
  set t0 [gb_now]
  pin_access {*}$pa_args
  dict set gb pin_access_s [expr { ([gb_now] - $t0) / 1000.0 }]
  dict set gb vm_rss_after_pin_access_kb [gb_status VmRSS]
  gb_write
}

set t0 [gb_now]
# tee, not redirect: the run log keeps the router's progress lines for a
# run that is killed, and the capture is parsed below.
utl::teeStringBegin
set rc [catch { global_route -verbose {*}[dict get $gb args] } msg]
set out [utl::teeStringEnd]
dict set gb global_route_s [expr { ([gb_now] - $t0) / 1000.0 }]
dict set gb global_route_ok [expr { $rc == 0 ? "true" : "false" }]
if { $rc } { dict set gb global_route_error $msg }
set ov {}
foreach l [split $out "\n"] {
  if { [regexp -nocase {overflow|Final congestion|Total wirelength|Total number of vias|extra iteration} $l] } { lappend ov [gb_jstr [string trim $l]] }
}
dict set gb overflow_lines "\[[join [lrange $ov 0 199] ,]\]"
dict set gb vm_hwm_kb [gb_status VmHWM]
dict set gb vm_rss_kb [gb_status VmRSS]
gb_write

# Fold the session's metrics (FastRoute phase timers, wirelength) into the JSON.
catch { utl::close_metrics $metrics_file }
if { [file exists $metrics_file] } {
  set f [open $metrics_file r]
  set m [read $f]
  close $f
  foreach {k v} [regexp -all -inline {"([^"]+)":\s*([-0-9.eE+]+)} $m] {
    if { [string match "global_route__*" $k] } {
      dict set gb [string map {"global_route__" ""} $k] $v
    }
  }
  gb_write
}
puts "grt_bench: wrote $::env(GRT_BENCH_OUT)"
