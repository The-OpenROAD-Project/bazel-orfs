# The .sdc reading is an implementation detail of read_sdc: a bus
# subscript like R0_addr[0] is a name inside an .sdc, and stock tcl -- a
# command substitution -- everywhere else. This probes both sides of that
# line on a real design, that the line is put back after read_sdc returns
# or fails, also when nested, and that the tcl write_pin_placement writes
# reads on the stock interpreter. One JSON of results in $RUN_OUTPUT_DIR;
# the run fails on any failed probe.
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

# Outside read_sdc: stock tcl.
probe "stock handler before read_sdc" \
  [expr {[unknown_handler] eq "::unknown"}] [unknown_handler]
set code [catch { get_ports R0_addr[0] } msg]
probe "bare bus name outside read_sdc is a tcl error" \
  [expr {$code == 1 && $msg eq {invalid command name "0"}}] $msg
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
probe "handler inside read_sdc is sta_unknown" \
  [expr {$::probe_handler eq "::sta_unknown"}] $::probe_handler
probe "stock handler after read_sdc" \
  [expr {[unknown_handler] eq "::unknown"}] [unknown_handler]

# An .sdc that fails puts it back too.
write_file $dir/bad.sdc {error "deliberate failure"}
set code [catch { read_sdc $dir/bad.sdc } msg]
probe "failing read_sdc raises" [expr {$code == 1}] $msg
probe "stock handler after failing read_sdc" \
  [expr {[unknown_handler] eq "::unknown"}] [unknown_handler]

# Nested: an .sdc that reads an .sdc.
write_file $dir/outer.sdc "
  read_sdc $dir/probe.sdc
  set ::outer_handler \[namespace eval :: { namespace unknown }\]
  set ::outer_ports \[get_ports R0_addr\[1\]\]
"
read_sdc $dir/outer.sdc
probe "outer .sdc keeps the reading after the inner read_sdc returns" \
  [expr {$::outer_handler eq "::sta_unknown" && [llength $::outer_ports] == 1}] \
  $::outer_handler
probe "stock handler after nested read_sdc" \
  [expr {[unknown_handler] eq "::unknown"}] [unknown_handler]

# write_pin_placement writes tcl that reads on the stock interpreter.
place_pins -hor_layers $::env(IO_PLACER_H) -ver_layers $::env(IO_PLACER_V)
write_pin_placement $dir/pins.tcl
set f [open $dir/pins.tcl]
set pins [read $f]
close $f
probe "write_pin_placement braces bus names" \
  [regexp {place_pin -pin_name \{R0_addr\[0\]\} } $pins] \
  [lindex [regexp -inline -line {^place_pin -pin_name [^ ]+} $pins] 0]
set code [catch { source $dir/pins.tcl } msg]
probe "write_pin_placement output sources on stock tcl" [expr {$code == 0}] $msg

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
