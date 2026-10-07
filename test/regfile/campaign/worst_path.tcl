set t [lindex [find_timing_paths -path_delay max -group_path_count 1 -sort_by_slack] 0]; set o "slack [get_property $t slack] ep [get_full_name [get_property $t endpoint]]\n"
foreach pt [get_property $t points] { set p [get_property $pt pin]; set n [get_full_name $p]; if {[regexp {/(Y|QN|Q|SN|CON)$} $n] || [get_property $p is_port]} { set c [expr {[get_property $p is_port] ? "port" : [get_property [get_cells -of_objects $p] ref_name]}]; append o [format "%7.1f %-50s %s\n" [get_property $pt arrival] [string range $n end-49 end] $c] } }
set o
