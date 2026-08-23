proc parse_json {json_str} {
    set clean_json [string trim $json_str]
    set paths_start [string first "\[" $clean_json]
    set paths_end [string last "\]" $clean_json]
    
    set paths_str [string range $clean_json [expr $paths_start + 1] [expr $paths_end - 1]]
    set paths_list []
    
    set path_objs [split $paths_str "\}"]
    foreach path_obj $path_objs {
        if {[string length [string trim $path_obj]] > 0} {
            set start ""
            set end ""
            if {[regexp {"start":\s*"([^"]+)"} $path_obj match s]} { set start $s }
            if {[regexp {"end":\s*"([^"]+)"} $path_obj match e]} { set end $e }
            if {$start != "" && $end != ""} {
                lappend paths_list [list $start $end]
            }
        }
    }
    return $paths_list
}
