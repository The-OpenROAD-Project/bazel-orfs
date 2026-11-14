# The whole synthesised design as a hierarchical database, the baseline
# every module's timing context is cut from (context_db.tcl), and the
# liberty it is timed with. Run by orfs_run on the synthesis stage.
#
#   PSTA_BASE_DB   out: the hierarchical database
#   PSTA_LIBS_TAR  out: the liberty files, for the timing steps
#
# The reading is ORFS's load_design's (load.tcl), the LEFs and liberty the
# stage reads, the netlist linked with -hier, but for its read_sdc: the
# timing steps apply a clock and nothing else, and the stage's 1_2_yosys.sdc
# is not among orfs_run's inputs. Unlike synth_odb.tcl's 1_synth.odb, no
# dead logic is eliminated: the baseline is the netlist synthesis wrote,
# the one timed flat.
source $::env(SCRIPTS_DIR)/load.tcl
source_env_var_if_exists PLATFORM_TCL
source $::env(SCRIPTS_DIR)/read_liberty.tcl
read_lef $::env(TECH_LEF)
read_lef $::env(SC_LEF)
if { [env_var_exists_and_non_empty ADDITIONAL_LEFS] } {
  foreach lef $::env(ADDITIONAL_LEFS) {
    read_lef $lef
  }
}
foreach lef [auto_memories_views .lef] {
  read_lef $lef
}
read_verilog $::env(RESULTS_DIR)/1_2_yosys.v
link_design -hier $::env(DESIGN_NAME)
write_db $::env(PSTA_BASE_DB)

# the liberty files, as one tar for the timing steps: the platform's, the
# macros', and the memories AUTO_MEMORIES wrote, the post-layout view of a
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
