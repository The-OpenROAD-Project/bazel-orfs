# A 32-word, 32-bit register file with four read and two write ports:
# small enough for CI, wide enough in ports to have the read wordlines,
# the write mux and the down-column OR trees the tool exists for.
module      rf32x32
words       32
bits        32
clock       clock
read        io_readPorts_0_addr  io_readPorts_0_data
read        io_readPorts_1_addr  io_readPorts_1_data
read        io_readPorts_2_addr  io_readPorts_2_data
read        io_readPorts_3_addr  io_readPorts_3_data
write       io_writePorts_0_addr io_writePorts_0_data io_writePorts_0_wen
write       io_writePorts_1_addr io_writePorts_1_data io_writePorts_1_wen
cell flop   DFFHQNx1_ASAP7_75t_R
cell and2   AND2x2_ASAP7_75t_R
cell or2    OR2x2_ASAP7_75t_R
cell ao22   AO22x2_ASAP7_75t_R
cell inv    INVx1_ASAP7_75t_R
cell tap    TAPCELL_ASAP7_75t_R
pin_layer   M4
tap_columns 8
