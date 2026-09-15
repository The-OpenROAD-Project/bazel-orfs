# Where the two tightly-coupled memories go, by hand and identically on
# every core.
#
# RTL-MP cannot place them. With two macros and a standard-cell half
# this small -- SERV's is about a thousand square microns against the
# memories' twenty thousand -- the hierarchical placer reports MPL-0045,
# "cannot find a balanced partitioning for the clusters", and the
# floorplan stage fails outright. Dropping to one clustering level
# (RTLMP_MAX_LEVEL) does not help: there is genuinely nothing to
# partition.
#
# Placing them by hand is the better answer here regardless. This is a
# measurement study, and an automatic placer is a source of run-to-run
# variation in exactly the quantity being reported: wirelength moves
# switching power. Fixing the coordinates makes the memory's
# contribution identical across the three cores, so what differs between
# their energy numbers is the core and not where its SRAM landed.
#
#   cmj_imem  88.54 x 177.08 um   at (8, 8)
#   cmj_dmem  44.27 x  88.54 um   at (101, 8)
#
# Both in the lower left, side by side, with the standard cells filling
# the L-shaped region above and to the right. The die comes from
# CORE_UTILIZATION and is at least 200 um on a side for every core in
# the study, so these coordinates sit inside the core area with room to
# spare on all three.
#
# SPDX-License-Identifier: Apache-2.0

place_macro -macro_name u_imem -location {8 8} -orientation R0
place_macro -macro_name u_dmem -location {101 8} -orientation R0
