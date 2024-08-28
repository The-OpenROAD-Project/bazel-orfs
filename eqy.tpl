[gold]
read_verilog -sv ${GOLD}
prep -top ${TOP}
memory_map

[gate]
read_verilog -sv ${GATE}
prep -top ${TOP}
memory_map

[collect *]

[strategy sby]
use sby
depth ${DEPTH}
engine smtbmc bitwuzla

