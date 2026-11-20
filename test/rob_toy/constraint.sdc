# 473 ps, 0.8 of XiangShan's published goal in fanouts of four on this
# library, and XiangShan's fanout cap (test/coremark_joule/designs/asap7/
# xiangshan/constraints.sdc): repair works hard here and buffers broadcast
# nets as the Rob macro does
set clk_name clock
set clk_port_name clock
set clk_period 473
source $env(PLATFORM_DIR)/constraints.sdc
set_max_fanout 32 [current_design]
