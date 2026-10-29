# Fold slang's per-instance copies of each module in XS_FOLD_MODULES back
# onto one module of the bare name, so synthesis maps it once.
#
# Run from fold_entries.ys through SYNTH_POST_HIERARCHY_SCRIPTS, as
# xs_icg.ys is. The slang frontend elaborates one module per instance and
# names it after the instance path (RobEntry$<path>): the Rob's 352 entry
# cells would be 352 modules and 352 ABC runs. The modules listed are the
# arrays front end's entry cells (arrays/extract.py), which take no
# parameters, so every copy is the same module: one copy is renamed to
# the bare name, every instance retyped onto it, and the hierarchy check
# after the hook prunes the rest.
#
# SPDX-License-Identifier: Apache-2.0
foreach base $::env(XS_FOLD_MODULES) {
  set copies {}
  foreach line [split [yosys tee -q -s result.string select -list-mod "$base\\\$*"] "\n"] {
    set line [regsub {^\\} [string trim $line] {}]
    if { $line ne "" } {
      lappend copies $line
    }
  }
  if { [llength $copies] == 0 } {
    error "fold_entries: no copies of $base in the design"
  }
  set copies [lsort $copies]
  yosys rename [lindex $copies 0] $base
  yosys chtype -set $base "t:$base\\\$*"
  puts "fold_entries: $base, [llength $copies] copies folded onto one"
}
