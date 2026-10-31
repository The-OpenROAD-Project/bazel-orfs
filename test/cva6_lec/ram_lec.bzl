"""kepler-formal SEC of a RAM against the macro AUTO_MEMORIES makes of it.

Gold is the RAM as the RTL has it, gate the model FakeRAM writes for its
macro. Both run under one top at a reduced depth, through their own
parameters (a full-size SEC of an SRAM does not finish), so the check is
of the width, byte lanes, enable, write mode and read the depth does not
change. Each control changes the model and must be caught.
"""

load("//test/lec:lec.bzl", "lec_test")

def _top(name, module, params, ports, depth, rst):
    """A genrule writing `lec_top`, one instance of `module`."""
    aw = {2: 1, 4: 2}[depth]
    decls = ["    input  logic clk", "    input  logic cs", "    input  logic we", "    input  logic [%d:0] addr" % (aw - 1)]
    conns = [".clk", ".cs", ".we", ".addr"]
    for port, width, direction in ports:
        decls.append("    %s logic [%d:0] %s" % ("output" if direction == "out" else "input ", width - 1, port))
        conns.append("." + port)
    if rst:
        conns.append(".rst_n(1'b1)")
    text = "module lec_top (\n%s\n);\n  %s #(%s) ram_i (%s);\nendmodule\n" % (
        ",\n".join(decls),
        module,
        params.format(depth = depth, aw = aw),
        ", ".join(conns),
    )
    native.genrule(
        name = name,
        outs = [name + ".sv"],
        cmd = "cat > $@ <<'EOF'\n" + text + "EOF",
    )

def ram_lec(name, module, gold, gold_params, gold_rst, gate, ports, controls, depths = [2, 4], timeout = "moderate"):
    """Equivalence at depths 2 and 4, and each control caught at depth 2.

    Args:
        name: prefix of the tests.
        module: the RAM's module name, on both sides.
        gold: the file with the RAM as the RTL has it (that module alone).
        gold_params: its parameter overrides, with {depth} and {aw}.
        gold_rst: True when the RTL's RAM has an rst_n the macro drops.
        gate: the model FakeRAM wrote for the macro.
        ports: (name, width, "in" | "out") past clk, cs, we and addr.
        controls: control name -> sed expression applied to the model.
        depths: the reduced depths checked; the controls run at the first.
        timeout: of each test, for a wide word.
    """
    for depth in depths:
        _top(name + "_gold_top_d%d" % depth, module, gold_params, ports, depth, gold_rst)
        _top(name + "_gate_top_d%d" % depth, module, ".WORD_DEPTH({depth}), .ADDR_WIDTH({aw})", ports, depth, False)
        lec_test(
            name = "%s_d%d_test" % (name, depth),
            frontend = "sv",
            gate_verilog_files = [":%s_gate_top_d%d" % (name, depth), gate],
            gold_verilog_files = [":%s_gold_top_d%d" % (name, depth), gold],
            timeout = timeout,
        )
    for control, expr in controls.items():
        # Each control must change the model, or it controls nothing.
        native.genrule(
            name = "%s_control_%s" % (name, control),
            srcs = [gate],
            outs = ["%s_control_%s.v" % (name, control)],
            cmd = "sed %s $< > $@ && ! cmp -s $< $@" % expr,
        )
        lec_test(
            name = "%s_%s_test" % (name, control),
            expect_equivalent = False,
            frontend = "sv",
            gate_verilog_files = [":%s_gate_top_d%d" % (name, depths[0]), ":%s_control_%s" % (name, control)],
            gold_verilog_files = [":%s_gold_top_d%d" % (name, depths[0]), gold],
            timeout = timeout,
        )

def reverse_lanes(bus, lanes):
    """A sed expression: mask bit j writes lane lanes - 1 - j."""
    return " ".join(["-e 's/%s\\[%d\\])/%s[L%d])/'" % (bus, j, bus, lanes - 1 - j) for j in range(lanes)]) + " -e 's/\\[L\\([0-9]*\\)\\]/[\\1]/'"

ENABLE_INVERTED = "-e 's/if (cs) begin/if (!cs) begin/'"
