# The liberty files a synthesised design is timed with, as one tar for
# the timing steps (sta.sh). Run by orfs_run on the synthesis stage, alone
# (orfs_timing_models) or from base.tcl.
#
#   PSTA_LIBS_TAR  out: the liberty files
#
# The platform's, the macros', and the memories AUTO_MEMORIES wrote, the post-layout view of a
# memory taken over its pre-layout one when both are there, as the stages
# after synthesis read it
set libs {}
foreach var {LIB_FILES ADDITIONAL_LIBS} {
  if { [info exists ::env($var)] } {
    foreach l $::env($var) {
      if { [lsearch -exact $libs $l] < 0 } { lappend libs $l }
    }
  }
}
set memdirs [list $::env(RESULTS_DIR)/memories]
if { [info exists ::env(AUTO_MEMORIES_DIR)] } { lappend memdirs $::env(AUTO_MEMORIES_DIR) }
set mems {}
foreach dir [lsort -unique $memdirs] {
  set mems [concat $mems [glob -nocomplain $dir/*.lib]]
}
foreach f [lsort -unique $mems] {
  if { [string match *_pre_layout.lib $f] } {
    set post [string range $f 0 end-[string length _pre_layout.lib]].lib
    if { [file exists $post] } { continue }
  }
  lappend libs $f
}
if { ![llength $libs] } { error "base.tcl: no liberty files" }
exec -ignorestderr tar -chf $::env(PSTA_LIBS_TAR) --transform {s,.*/,,} {*}$libs
