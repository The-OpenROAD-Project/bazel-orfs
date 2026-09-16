# The platform's wire constant, scaled, to find what the critical path
# behaves as if it were routed on.
#
# The demand-weighted calibration (rc_calibrate.py) moves the signal
# constant by 4-7% and recovers 15% of the pre-route magnitude error,
# because it is an average over the bulk and the bulk is already about
# right. The error lives on the critical path, which a resistance-aware
# router deliberately puts on metal faster than average.
#
# So this sweeps the constant instead of fitting it, and the scale at
# which placement's min_period meets the routed period says what
# resistance the critical path is effectively seeing. That number is a
# property of the router's policy, not of the wire model, which is why
# no averaging fit can find it.
#
# Resistance only. Capacitance is nearly flat across asap7's stack
# (0.09-0.19 against resistance's 8x range), so layer choice is a
# resistance story, and scaling C too would confound the wire's own RC
# with the load the driving cell sees.
source $::env(PLATFORM_DIR)/setRC.tcl

set scale $::env(RI_RC_SCALE)
set base_r 2.65684E-02
set base_c 1.65790E-01
set scaled_r [expr { $base_r * $scale }]

set_wire_rc -signal -resistance $scaled_r -capacitance $base_c

puts "RC_SCAN scale=$scale signal R=$scaled_r C=$base_c"
