# isolate_loop_sinks sweep

Each ORFS design runs four arms from its floorplan to global route: the flow
as is (`base`) and with `isolate_loop_sinks.tcl` before CTS (`iso`), each at
placement seeds 1 and 2. The two `base` seeds are the noise band; a difference
inside it is noise. Everything measured is reg2reg: the SDCs' IO budgets are
not maintained as requirements.

    for arm in "base 1" "iso 1" "base 2" "iso 2"; do
      tools/headroom/sweep/arm.sh @orfs//flow/designs/asap7/jpeg:jpeg_encoder jpeg $arm
    done
    cat tmp/sweep/results.txt

Run the arms one after another, in a worktree nothing else builds in: a
dirty lane reads the runfile manifests of the workspace's Bazel server, and
another build running there meanwhile replaces files the lane is installing
("... is not built").

Each result line: the reg2reg period (clock period minus the worst reg2reg
slack), the reg2reg violating endpoints and their total slack, the buffer
count, the cell area (um^2), and `report_floor_cycles.tcl`'s line: the
one-flop-loop floor, its register, its stages and the buffers on it. An `iso`
line ends with how many loop sinks were moved.
