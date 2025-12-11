[gold]
read_verilog -sv ${GOLD}

[gate]
read_verilog -sv ${GATE}

[script]
prep -top ${TOP}
memory_map
rename -hide w:\_*_ c:\_*_
flatten
hierarchy -purge_lib

[collect *]

[strategy sby]
use sby
depth ${DEPTH}
engine smtbmc bitwuzla

# Lifted from https://github.com/The-OpenROAD-Project/OpenROAD/blob/8987223146c788a48d7ff4bde299a07a9429c8c1/test/helpers.tcl#L78-L90
# Recommendation from eqy team on how to speed up a design
[match *]
gate-nomatch _*_.*
# See issue OpenROAD#6545 "Equivalence check failure due to non-unique resizer nets"
gate-nomatch net*
# Forbid matching on buffer instances or cloned instances to make it less
# likely EQY will fail to prove equivalence because of its assuming structural
# similarity between gold and gate netlists. This doesn't remove coverage.
gate-nomatch clone*
gate-nomatch place*
gate-nomatch rebuffer*
gate-nomatch wire*
gate-nomatch place*
