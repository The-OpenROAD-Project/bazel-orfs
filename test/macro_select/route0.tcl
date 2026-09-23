# Route-0 on a CTS checkpoint: a zero-iteration global route with congestion
# allowed, and what it reports, as JSON. The wall shows here as GRT-0228
# (FastRoute's usage guard on one gcell edge) or as the Total row's
# congestion; either way the route is not attempted, only measured.
# declared beside the flow it probes, so its RESULTS_DIR is the flow's
source $::env(SCRIPTS_DIR)/load.tcl
load_design 4_cts.odb 4_cts.sdc
set_routing_layers -signal $::env(MIN_ROUTING_LAYER)-$::env(MAX_ROUTING_LAYER)
if { [info exists ::env(ROUTING_LAYER_ADJUSTMENT)] } {
  set_global_routing_layer_adjustment $::env(MIN_ROUTING_LAYER)-$::env(MAX_ROUTING_LAYER) $::env(ROUTING_LAYER_ADJUSTMENT)
}
utl::redirectStringBegin
set route_args {-congestion_iterations 0 -allow_congestion -verbose}
if { [info exists ::env(CONGESTION_REPORT)] && $::env(CONGESTION_REPORT) ne "" } {
  lappend route_args -congestion_report_file $::env(CONGESTION_REPORT)
}
set ok [expr { ![catch { global_route {*}$route_args } err] }]
if { [info exists ::env(CONGESTION_REPORT)] && $::env(CONGESTION_REPORT) ne "" && ![file exists $::env(CONGESTION_REPORT)] } {
  set f [open $::env(CONGESTION_REPORT) w]; puts $f "no congestion regions reported"; close $f
}
set text [utl::redirectStringEnd]
puts $text
set total_h 0; set total_v 0; set total_c 0; set usage 0
if { [regexp -line {^Total\s+\d+\s+\d+\s+([\d.]+)%\s+(\d+)\s*/\s*(\d+)\s*/\s*(\d+)} $text - usage total_h total_v total_c] } {}
set wl 0
regexp {Total wirelength: (\d+) um} $text - wl
set guard ""
regexp -line {GRT-0228\] (.*)$} $text - guard
if { !$ok } { regexp -line {GRT-0228\] (.*)$} $err - guard; if { $guard eq "" } { set guard $err } }
set fp [open $::env(OUTPUT_JSON) w]
puts $fp "{"
puts $fp "  \"ok\": $ok,"
puts $fp "  \"usage_percent\": $usage,"
puts $fp "  \"max_h_overflow\": $total_h,"
puts $fp "  \"max_v_overflow\": $total_v,"
puts $fp "  \"total_congestion\": $total_c,"
puts $fp "  \"wirelength_um\": $wl,"
puts $fp "  \"guard\": \"[string map {\\ \\\\ \" \\\"} $guard]\""
puts $fp "}"
close $fp
