# Drives the SYNTH_RETIME_MODULES block of ORFS's synth.tcl (SYNTH_TCL) on
# the fixture, with abc replaced by a recorder of what it would retime.
yosys -import

proc env_var_exists_and_non_empty { name } {
  return [expr { [info exists ::env($name)] && $::env($name) ne "" }]
}

proc abc { args } {
  set ::retimed [lsort [split [string trim [tee -q -s result.string select -list-mod]] "\n"]]
}

set fid [open $::env(SYNTH_TCL) r]
set block ""
set found 0
while { [gets $fid line] >= 0 } {
  if { !$found && $line ne "if \{ \[env_var_exists_and_non_empty SYNTH_RETIME_MODULES\] \} \{" } {
    continue
  }
  set found 1
  append block $line "\n"
  if { [info complete $block] } {
    break
  }
}
close $fid
if { !$found } {
  error "no SYNTH_RETIME_MODULES block in $::env(SYNTH_TCL)"
}

read_verilog $::env(TEST_VERILOG)
hierarchy -top Top
set ::env(SCRIPTS_DIR) .

proc retime { patterns checkpoint } {
  set ::env(SYNTH_RETIME_MODULES) $patterns
  set ::env(SYNTH_CHECKPOINT) $checkpoint
  set ::retimed {}
  if { [catch { uplevel #0 $::block } message] } {
    return [list error $message]
  }
  return [list ok $::retimed]
}

proc expect { patterns checkpoint expected } {
  set got [retime $patterns $checkpoint]
  if { [lindex $expected 0] eq "error" } {
    set ok [expr {
      [lindex $got 0] eq "error"
      && [string match [lindex $expected 1] [lindex $got 1]]
    }]
  } else {
    set ok [expr { $got eq $expected }]
  }
  if { !$ok } {
    error "SYNTH_RETIME_MODULES='$patterns' SYNTH_CHECKPOINT='$checkpoint':\
      expected $expected, got $got"
  }
  puts "PASS: '$patterns' checkpoint='$checkpoint' -> $got"
}

# Globs over the slang-style names, and the top by its plain name.
expect "FooKept* BarKept* Top" "" \
  [list ok [list {BarKept$top.bar} {FooKept$top.foo} Top]]
# A bare name matches no Name$<path> module: an error naming it alone.
expect "FooKept Top" "" {error {*matches FooKept; the slang*}}
# A module flattening removed is not retimed either.
expect "Unrelated* Top" "" {error {*matches Unrelated\*; *}}
# In a partition an entry for another partition's module is skipped.
expect "FooKept Top" "partition.rtlil" [list ok [list Top]]
expect "Nothing*" "partition.rtlil" [list ok {}]
