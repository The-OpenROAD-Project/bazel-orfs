# One routed generate_ram block as a picture: run from an OpenROAD
# checkout's src/ram/test, where routed.tcl and the PDKs' files are, with
# a GUI build of openroad:
#
#   PDK=asap7 ARGS="-w_ports 2 ..." OUT=/abs/x.png QT_QPA_PLATFORM=offscreen \
#     openroad -exit -no_init -no_splash render.tcl
source "helpers.tcl"
source "routed.tcl"

proc read_sky130hd { } {
  read_liberty sky130hd/sky130_fd_sc_hd__tt_025C_1v80.lib
  read_lef sky130hd/sky130hd.tlef
  read_lef sky130hd/sky130_fd_sc_hd_merged.lef
}
set sky130hd {
  -routing_layer {met1 0.48}
  -ver_layer {met2 0.48 40}
  -hor_layer {met3 0.48 20}
  -filler_cells {sky130_fd_sc_hd__fill_1 sky130_fd_sc_hd__fill_2
    sky130_fd_sc_hd__fill_4 sky130_fd_sc_hd__fill_8}
  -tapcell sky130_fd_sc_hd__tap_1
  -max_tap_dist 15
}

switch $::env(PDK) {
  asap7 {
    routed::read_asap7
    set pdk $routed::asap7
  }
  nangate45 {
    routed::read_nangate45
    set pdk $routed::nangate45
  }
  sky130hd {
    read_sky130hd
    set pdk $sky130hd
  }
}
generate_ram {*}$pdk {*}$::env(ARGS)
routed::check
save_image -resolution 0.01 $::env(OUT)
puts "pass"
