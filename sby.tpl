[tasks]
bmc

[options]
bmc:
mode bmc

[engines]
smtbmc z3

[script]
read -formal ${VERILOG_BASE_NAMES}
prep -top ${TOP}

[files]
${VERILOG}
