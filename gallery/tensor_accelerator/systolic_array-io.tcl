# Systolic array pin constraints — 16x16 PE grid.
# Activations enter left, weights from top, results drain bottom.

set_io_pin_constraint -region left:* -pin_names [concat \
    {act_data[*]} act_valid act_ready]
set_io_pin_constraint -region top:* -pin_names [concat \
    {weight_load_data[*]} weight_load_en {weight_load_col[*]} \
    {cfg_k_tiles[*]} start clear_acc]
set_io_pin_constraint -region bottom:* -pin_names [concat \
    {result_data[*]} result_valid result_ready busy done]
