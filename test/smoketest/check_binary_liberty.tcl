# The OpenROAD stages read the platform's liberty files in binary form
# (orfs_pdk's mirror, PdkInfo.openroad_config): every file in LIB_FILES,
# or in <CORNER>_LIB_FILES with CORNERS, is a binary liberty file.
# liberty_binary_info refuses a text library (STA-1900).
set lib_files {}
if { [info exists ::env(CORNERS)] && $::env(CORNERS) ne "" } {
  foreach corner $::env(CORNERS) {
    lappend lib_files {*}$::env([string toupper $corner]_LIB_FILES)
  }
} else {
  lappend lib_files {*}$::env(LIB_FILES)
}
# Normalized: a platform may spell LIB_FILES with $(abspath ...) (gf180).
set platform_dir [file normalize $::env(PLATFORM_DIR)]
set n 0
foreach lib_file $lib_files {
  # Macro libraries (ADDITIONAL_LIBS) are not the platform's.
  if { ![string match "$platform_dir/*" [file normalize $lib_file]] } { continue }
  if { [catch { liberty_binary_info $lib_file } err] } {
    puts "not a binary liberty file: $lib_file ($err)"
    exit 1
  }
  incr n
}
if { $n == 0 } {
  puts "no platform liberty files in LIB_FILES"
  exit 1
}
puts "all $n platform liberty files are binary"
exec touch $::env(WORK_HOME)/$::env(OUTPUT)
