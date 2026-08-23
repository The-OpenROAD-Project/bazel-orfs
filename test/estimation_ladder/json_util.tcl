proc escape_json {str} {
    set escaped [string map { \" \\\" \\ \\\\ \/ \\/ \b \\b \f \\f \n \\n \r \\r \t \\t } $str]
    return "\"$escaped\""
}

proc write_json_object {args} {
    set items {}
    foreach {k v} $args {
        lappend items "[escape_json $k]: $v"
    }
    return "\{ [join $items ", "] \}"
}

proc write_json_array {args} {
    return "\[ [join $args ", "] \]"
}
