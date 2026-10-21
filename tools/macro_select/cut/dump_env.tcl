# The environment ORFS's make gives a stage's openroad, and the directory
# it runs in, as JSON: the census worker loads a design with the same.
#
#   make run RUN_SCRIPT=dump_env.tcl DUMP_ENV_OUT=env.json
proc dump_env_quote { s } {
  return "\"[string map {\\ \\\\ \" \\\" \n \\n \t \\t \r \\r} $s]\""
}
set f [open $::env(DUMP_ENV_OUT) w]
puts $f "\{\"cwd\": [dump_env_quote [pwd]], \"env\": \{"
set sep ""
foreach k [lsort [array names ::env]] {
  puts -nonewline $f "$sep[dump_env_quote $k]: [dump_env_quote $::env($k)]"
  set sep ",\n"
}
puts $f "\}\}"
close $f
