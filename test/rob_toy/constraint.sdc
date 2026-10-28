# XiangShan's period and fanout cap (test/coremark_joule/designs/asap7/
# xiangshan/constraints.sdc): the Rob macro was built against both, so
# repair works as hard here and buffers broadcast nets the same way
set clk_name clock
set clk_port_name clock
set clk_period 473
source $env(PLATFORM_DIR)/constraints.sdc
set_max_fanout 32 [current_design]
