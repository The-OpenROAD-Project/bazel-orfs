# openroad -exit time_frontend.tcl, with load.tcl's environment and
# XS_TAG, XS_OUT: appends xs_measure's line to XS_OUT, the worst path
# beside it as <XS_OUT without extension>_<XS_TAG>.txt.
set here [file dirname [info script]]
source $here/load.tcl
source $here/measure.tcl
xs_measure $::env(XS_TAG) $::env(XS_OUT) [file rootname $::env(XS_OUT)]_$::env(XS_TAG).txt
