# MAC PE pin constraints — weight-stationary systolic dataflow.
# Activations flow left→right, partial sums flow top→bottom.

set_io_pin_constraint -region left:*   -pin_names {act_in[*]}
set_io_pin_constraint -region right:*  -pin_names {act_out[*]}
set_io_pin_constraint -region top:*    -pin_names [concat \
    {psum_in[*]} {weight_in[*]} load_weight enable clear_acc]
set_io_pin_constraint -region bottom:* -pin_names {psum_out[*]}
