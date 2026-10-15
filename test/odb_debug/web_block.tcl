# A 10 x 10 um asap7 BLOCK with three M3 pins on its top edge, 18, 36 and
# 90 nm wide, M4 obstructed over the block, served by the odb-debug daemon
# through the web viewer. The 36 nm pin has no access point (DRT-0073):
# OpenROAD issue 11766.
set here [file dirname [file normalize [info script]]]
read_lef $::env(TECH_LEF)
read_lef $here/block.lef
read_def $here/design.def
# flow/platforms/asap7/openRoad/make_tracks.tcl, M1-M7
make_tracks M7 -x_offset 0.016 -x_pitch 0.064 -y_offset 0.016 -y_pitch 0.064
make_tracks M6 -x_offset 0.012 -x_pitch 0.048 -y_offset 0.016 -y_pitch 0.064
make_tracks M5 -x_offset 0.012 -x_pitch 0.048 -y_offset 0.012 -y_pitch 0.048
make_tracks M4 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.012 -y_pitch 0.048
make_tracks M3 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.009 -y_pitch 0.036
make_tracks M2 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.009 -y_pitch 0.036
make_tracks M1 -x_offset 0.009 -x_pitch 0.036 -y_offset 0.009 -y_pitch 0.036
set_routing_layers -signal M2-M7
source $::env(ODB_DEBUG_DAEMON)
