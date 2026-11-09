# The platform's boundary constraints (flow/platforms/asap7/constraints.sdc)
# in the shape a real part's SDC has them, for the crossing ledger to read
# on top of the toy's clock: a part's own budgets change none of its
# halves (mini_top_parent_pm_ledger_budgets_test). The budgets are the
# ones toy.bzl counts the parent's pins over.
set non_clk_inputs [all_inputs -no_clocks]
set_max_delay -ignore_clock_latency 300 -from $non_clk_inputs -to [all_registers]
set_max_delay -ignore_clock_latency 600 -from [all_registers] -to [all_outputs]
set_max_delay 100 -from $non_clk_inputs -to [all_outputs]
group_path -name in2reg -from $non_clk_inputs -to [all_registers]
group_path -name reg2out -from [all_registers] -to [all_outputs]
group_path -name reg2reg -from [all_registers] -to [all_registers]
group_path -name in2out -from $non_clk_inputs -to [all_outputs]
