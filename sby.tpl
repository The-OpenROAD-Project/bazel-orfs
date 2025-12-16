[tasks]
bmc

[options]
bmc:
mode bmc

[engines]
smtbmc bitwuzla

[script]
read -formal ${VERILOG_BASE_NAMES}
prep -top ${TOP}

[files]
${VERILOG}
