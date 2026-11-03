# The platform files the kit's flow reads, as the flow resolved them: one
# line per file, "<kind> <path relative to PLATFORM_DIR>". kit.py copies
# exactly these from the platform, so the kit ships what the flow used and
# nothing is listed by hand. Macros' own views (register files, memories)
# are not the platform's and are left out here.
#
# Run by orfs_run in the kit flow's synthesis environment; OUTPUT names
# the manifest.

set platform [file normalize $::env(PLATFORM_DIR)]
set f [open $::env(OUTPUT) w]
proc emit { f platform kind paths } {
  foreach path $paths {
    set path [file normalize $path]
    if { [string first "$platform/" $path] != 0 } { continue }
    puts $f "$kind [string range $path [expr { [string length $platform] + 1 }] end]"
  }
}
emit $f $platform tech_lef $::env(TECH_LEF)
emit $f $platform cell_lef $::env(SC_LEF)
if { [info exists ::env(ADDITIONAL_LEFS)] } { emit $f $platform cell_lef $::env(ADDITIONAL_LEFS) }
emit $f $platform cell_lib $::env(LIB_FILES)
# not in a stage's environment by name: the platform's own files
foreach {kind name} {setrc setRC.tcl platform_sdc constraints.sdc} {
  set path [file join $::env(PLATFORM_DIR) $name]
  if { ![file exists $path] } { error "kit_manifest: the platform has no $name" }
  emit $f $platform $kind $path
}
close $f
