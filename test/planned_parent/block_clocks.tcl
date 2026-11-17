# Each hard block's clock against the parent's registers after CTS, in
# CTS's own model (placement parasitics), as JSON for
# cts_latency_offset_test: the block's clock pin arrival plus its
# insertion delay (its lib's max_clock_tree_path, rise and fall averaged,
# what CTS's latency balancer adds) less the parent registers' median
# clock arrival, in ps.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 4_cts.odb
estimate_parasitics -placement
set_propagated_clock [all_clocks]

proc insertion_delay { master } {
  foreach lib $::env(ADDITIONAL_LIBS) {
    set f [open $lib r]
    set text [read $f]
    close $f
    if { ![regexp "cell\\s*\\(\\s*\"?$master\"?\\s*\\)" $text] } {
      continue
    }
    # the brace around each table is matched as any character, so that the
    # pattern carries no brace of its own
    set num {[-0-9.eE]+}
    set table {\s*.\s*values\("(NUM)"\);\s*.\s*}
    set table [string map [list NUM $num] $table]
    set pattern "max_clock_tree_path;\\s*cell_rise\\(scalar\\)${table}cell_fall\\(scalar\\)$table"
    if { [regexp $pattern $text - rise fall] } {
      return [expr { ($rise + $fall) / 2.0 }]
    }
  }
  error "no max_clock_tree_path for $master in ADDITIONAL_LIBS"
}

set block [ord::get_db_block]
set regs {}
foreach pin [all_registers -clock_pins] {
  set inst [$block findInst [get_full_name [get_cells -of_objects $pin]]]
  if { $inst ne "NULL" && [[$inst getMaster] isBlock] } {
    continue
  }
  set a [get_property $pin arrival_max_rise]
  if { $a ne "" } {
    lappend regs $a
  }
}
set regs [lsort -real $regs]
set median [lindex $regs [expr { [llength $regs] / 2 }]]

set entries {}
foreach inst [$block getInsts] {
  set master [$inst getMaster]
  if { ![$master isBlock] } {
    continue
  }
  foreach it [$inst getITerms] {
    if { [[$it getMTerm] getSigType] ne "CLOCK" } {
      continue
    }
    set pin [get_pins "[$inst getName]/[[$it getMTerm] getName]"]
    set arrival [get_property $pin arrival_max_rise]
    set error [expr { $arrival + [insertion_delay [$master getName]] - $median }]
    lappend entries [format "    \"%s\": %.2f" [$inst getName] $error]
  }
}
set out [open $::env(OUTPUT_JSON) w]
puts $out "{"
puts $out "  \"register_median\": [format %.2f $median],"
puts $out "  \"block_error\": {"
puts $out [join $entries ",\n"]
puts $out "  }"
puts $out "}"
close $out
