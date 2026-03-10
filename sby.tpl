[tasks]
bmc

[options]
bmc:
mode bmc
depth ${DEPTH}

[engines]
smtbmc bitwuzla

[script]
read -formal ${VERILOG_BASE_NAMES}
prep -top ${TOP}

[files]
${VERILOG}
