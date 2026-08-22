set fd1 [open $::env(TEST_SOURCE_1) r]
set content1 [read $fd1]
close $fd1
if {![string match "*test_source_content*" $content1]} {
    puts "FAIL: TEST_SOURCE_1 content mismatch: $content1"
    exit 1
}

set found_second 0
foreach src $::env(TEST_SOURCES) {
    set fdn [open $src r]
    set contentn [read $fdn]
    close $fdn
    if {[string match "*second_source_content*" $contentn]} {
        set found_second 1
    }
}
if {!$found_second} {
    puts "FAIL: TEST_SOURCES did not contain second_source_content"
    exit 1
}

puts "PASS: orfs_test sources mapped correctly"
exit 0
