# check_clock_tree_paths (ORFS's generate_abstract, carried patch 0231)
# passes a timing model whose clock tree paths are in order, refuses one
# whose max_clock_tree_path is below its min (FLW-0030), and refuses one
# it cannot read rather than pass it (FLW-0031). The fixtures are
# VecRegionModule's clock pin as two builds wrote it: main.lib, max
# 216.3/227.4 below min 501.1/525.9 (a VfRegFile clock pin chosen as the
# latest sink, written without its own tree, 0230), and r31.lib in order
# (min 170.9/179.4, max 546.9/573.7); table.lib is r31.lib with its
# values in a table the check does not read.
# Env: CHECK_CLOCK_TREE_PATHS_TCL, FIXTURES.
source $::env(CHECK_CLOCK_TREE_PATHS_TCL)

proc expect_pass { lib } {
  if { [catch { check_clock_tree_paths $lib } msg] } {
    error "FAIL: [file tail $lib] refused: $msg"
  }
  puts "ok: [file tail $lib] passes"
}

proc expect_refused { lib id } {
  if { ![catch { check_clock_tree_paths $lib } msg] } {
    error "FAIL: [file tail $lib] was not refused"
  }
  # OpenROAD's utl::error logs the message and returns its id.
  if { ![string match "*FLW*$id*" $msg] } {
    error "FAIL: [file tail $lib] refused for another reason: $msg"
  }
  puts "ok: [file tail $lib] refused: $msg"
}

expect_pass $::env(FIXTURES)/r31.lib
expect_refused $::env(FIXTURES)/main.lib 30
expect_refused $::env(FIXTURES)/table.lib 31
puts "pass"
