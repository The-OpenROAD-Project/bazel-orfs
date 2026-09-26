# The .sdc reading is an implementation detail of read_sdc: OpenSTA
# installs sta_sdc_unknown, under which a bus subscript like R0_addr[0]
# is a name, for the extent of the .sdc file, and puts the session's own
# handler back on the way out. This probes both sides of that line on a
# real design, that the line is put back after read_sdc returns or
# fails, also when nested, and that the tcl write_pin_placement writes
# braces its bus names and sources outside read_sdc. One JSON of results
# in $RUN_OUTPUT_DIR; the run fails on any failed probe.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_floorplan.odb 2_floorplan.sdc

set dir $::env(RUN_OUTPUT_DIR)
set results {}
set failed {}

proc probe { name ok detail } {
  global results failed
  lappend results [list $name $ok $detail]
  if { !$ok } {
    lappend failed $name
  }
  puts "[expr {$ok ? "PASS" : "FAIL"}] $name: $detail"
}

proc unknown_handler {} {
  return [namespace eval :: { namespace unknown }]
}

proc write_file { path text } {
  set f [open $path w]
  puts $f $text
  close $f
}

proc is_sdc_handler { handler } {
  return [string match *sta_sdc_unknown $handler]
}

# Outside read_sdc: the session's handler, not the .sdc one.
set session [unknown_handler]
probe "session handler before read_sdc is not the .sdc one" \
  [expr {![is_sdc_handler $session]}] $session
set braced [get_ports {R0_addr[0]}]
probe "braced bus name outside read_sdc resolves" \
  [expr {[llength $braced] == 1}] [get_full_name $braced]

# Inside read_sdc: the .sdc reading.
write_file $dir/probe.sdc {
  set ::probe_ports [get_ports R0_addr[0]]
  set ::probe_handler [namespace eval :: { namespace unknown }]
}
read_sdc $dir/probe.sdc
probe "bare bus name inside read_sdc resolves" \
  [expr {[llength $::probe_ports] == 1}] [get_full_name $::probe_ports]
probe "handler inside read_sdc is sta_sdc_unknown" \
  [is_sdc_handler $::probe_handler] $::probe_handler
probe "session handler after read_sdc" \
  [expr {[unknown_handler] eq $session}] [unknown_handler]

# An .sdc that fails puts it back too.
write_file $dir/bad.sdc {error "deliberate failure"}
set code [catch { read_sdc $dir/bad.sdc } msg]
probe "failing read_sdc raises" [expr {$code == 1}] $msg
probe "session handler after failing read_sdc" \
  [expr {[unknown_handler] eq $session}] [unknown_handler]

# Nested: an .sdc that reads an .sdc.
write_file $dir/outer.sdc "
  read_sdc $dir/probe.sdc
  set ::outer_handler \[namespace eval :: { namespace unknown }\]
  set ::outer_ports \[get_ports R0_addr\[1\]\]
"
read_sdc $dir/outer.sdc
probe "outer .sdc keeps the reading after the inner read_sdc returns" \
  [expr {[is_sdc_handler $::outer_handler] && [llength $::outer_ports] == 1}] \
  $::outer_handler
probe "session handler after nested read_sdc" \
  [expr {[unknown_handler] eq $session}] [unknown_handler]

# write_pin_placement writes tcl that reads outside read_sdc.
place_pins -hor_layers $::env(IO_PLACER_H) -ver_layers $::env(IO_PLACER_V)
write_pin_placement $dir/pins.tcl
set f [open $dir/pins.tcl]
set pins [read $f]
close $f
probe "write_pin_placement braces bus names" \
  [regexp {place_pin -pin_name \{R0_addr\[0\]\} } $pins] \
  [lindex [regexp -inline -line {^place_pin -pin_name [^ ]+} $pins] 0]
set code [catch { source $dir/pins.tcl } msg]
probe "write_pin_placement output sources outside read_sdc" [expr {$code == 0}] $msg

set f [open $dir/results.json w]
puts $f "\["
set sep ""
foreach r $results {
  lassign $r name ok detail
  set detail [string map {\\ \\\\ \" \\\"} $detail]
  puts $f "  $sep{\"probe\": \"$name\", \"ok\": [expr {$ok ? "true" : "false"}], \"detail\": \"$detail\"}"
  set sep ","
}
puts $f "\]"
close $f

if { [llength $failed] } {
  error "[llength $failed] probe(s) failed: [join $failed {; }]"
}
puts "all [llength $results] probes passed"
