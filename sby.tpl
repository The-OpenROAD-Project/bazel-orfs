[tasks]
${TASKS}

[options]
${OPTIONS}

[engines]
${ENGINES}

[script]
read -formal ${VERILOG_BASE_NAMES}
prep -top ${TOP}

[files]
${VERILOG}
${INCLUDES}
