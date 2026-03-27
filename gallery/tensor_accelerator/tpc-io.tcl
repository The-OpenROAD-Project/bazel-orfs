# TPC pin constraints — NoC on left/right, AXI + control on top/bottom.

set_io_pin_constraint -region left:* -pin_names [concat \
    {noc_rx_data[*]} {noc_rx_addr[*]} noc_rx_valid noc_rx_ready noc_rx_is_instr]
set_io_pin_constraint -region right:* -pin_names [concat \
    {noc_tx_data[*]} {noc_tx_addr[*]} noc_tx_valid noc_tx_ready]
set_io_pin_constraint -region top:* -pin_names [concat \
    tpc_start {tpc_start_pc[*]} tpc_busy tpc_done tpc_error \
    global_sync_in sync_request sync_grant]
set_io_pin_constraint -region bottom:* -pin_names [concat \
    {axi_*}]
