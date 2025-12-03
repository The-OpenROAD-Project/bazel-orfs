[tasks]
bmc

[options]
bmc:
mode bmc
depth 1000

[engines]
smtbmc z3
#btor btormc

[script]
read -formal VERILOG_BASE_NAMES

# 1. Elaborate
hierarchy -check -top ${TOP}
# 2. Convert processes
proc
# 3. Flatten the hierarchy. 
# This is REQUIRED for Z3 to see signals inside submodules.
flatten
# 4. Clean up weird artifacts from 'proc', but explicitly KEEP dead code/wires.
# The '-keepdc' flag is the magic sauce that stops signals from vanishing.
opt -keepdc -fast
# 5. Memories and Techmap
memory
techmap
# 6. One last check to ensure names are preserved
opt_clean -purge



[files]
${VERILOG}
