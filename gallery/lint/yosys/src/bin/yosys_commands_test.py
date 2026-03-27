"""Unit tests for lint Yosys command implementations."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "tcl", "src", "bin"
))
from tcl_interpreter import TclInterpreter
import yosys_commands


@pytest.fixture
def interp():
    i = TclInterpreter()
    yosys_commands.register_all(i)
    yosys_commands.reset_state()
    return i


@pytest.fixture
def state():
    yosys_commands.reset_state()
    return yosys_commands.get_state()


# --- Verilog parsing ---

class TestParseVerilog:
    def test_simple_module(self):
        content = """
module counter (
    input wire clk,
    input wire rst,
    output wire [7:0] count
);
  reg [7:0] counter_reg;
  assign count = counter_reg;
endmodule
"""
        modules = yosys_commands.parse_verilog(content)
        assert "counter" in modules
        assert modules["counter"]["regs"] == 8
        assert modules["counter"]["assigns"] == 1

    def test_multiple_modules(self):
        content = """
module a(); endmodule
module b(); endmodule
module c(); endmodule
"""
        modules = yosys_commands.parse_verilog(content)
        assert len(modules) == 3
        assert "a" in modules
        assert "b" in modules
        assert "c" in modules

    def test_empty_content(self):
        modules = yosys_commands.parse_verilog("")
        assert modules == {}

    def test_no_modules(self):
        modules = yosys_commands.parse_verilog(
            "// just a comment\n"
        )
        assert modules == {}

    def test_instantiation_detection(self):
        content = """
module top();
  sub_a u_a (.clk(clk));
  sub_b u_b (.clk(clk));
endmodule
"""
        modules = yosys_commands.parse_verilog(content)
        assert "sub_a" in modules["top"]["instances"]
        assert "sub_b" in modules["top"]["instances"]


# --- Cell estimation ---

class TestEstimateCells:
    def test_empty_modules(self):
        result = yosys_commands.estimate_cells({})
        assert result == 100  # default fallback

    def test_with_top_module(self):
        modules = {
            "top": {
                "ports": ["clk"], "regs": 32,
                "assigns": 4, "instances": [],
                "lines": 10,
            }
        }
        result = yosys_commands.estimate_cells(modules, "top")
        assert result > 32  # at least the flip-flops

    def test_with_instances(self):
        modules = {
            "top": {
                "ports": [], "regs": 0,
                "assigns": 0, "instances": ["sub"],
                "lines": 5,
            },
            "sub": {
                "ports": [], "regs": 16,
                "assigns": 2, "instances": [],
                "lines": 10,
            },
        }
        result = yosys_commands.estimate_cells(modules, "top")
        # Should include sub's contribution
        assert result > 16


# --- read_verilog validation ---

class TestReadVerilog:
    def test_missing_file(self, interp, capsys):
        interp.eval('read_verilog /nonexistent/file.sv')
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_existing_file(self, interp, state, capsys):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sv", delete=False
        ) as f:
            f.write("module test_mod(); endmodule\n")
            f.flush()
            interp.eval(f'read_verilog {f.name}')
            assert "test_mod" in state.modules
            os.unlink(f.name)

    def test_empty_file(self, interp, state, capsys):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sv", delete=False
        ) as f:
            f.write("// empty\n")
            f.flush()
            interp.eval(f'read_verilog {f.name}')
            captured = capsys.readouterr()
            assert "0 modules" in captured.err
            os.unlink(f.name)


# --- hierarchy validation ---

class TestHierarchy:
    def test_unknown_top(self, interp, state, capsys):
        state.modules = {"real_mod": {"ports": []}}
        interp.eval("hierarchy -top nonexistent_mod")
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_valid_top(self, interp, state, capsys):
        state.modules = {"my_mod": {"ports": []}}
        interp.eval("hierarchy -top my_mod")
        assert state.top_module == "my_mod"


# --- write_verilog output ---

class TestWriteVerilog:
    def test_creates_file(self, interp, state):
        state.top_module = "test_mod"
        state.modules = {
            "test_mod": {"ports": ["clk", "rst"]}
        }
        with tempfile.NamedTemporaryFile(
            suffix=".v", delete=False
        ) as f:
            path = f.name
        interp.eval(f"write_verilog {path}")
        with open(path) as f:
            content = f.read()
        assert "module test_mod" in content
        assert "clk" in content
        os.unlink(path)


# --- stat output ---

class TestStat:
    def test_stat_report_format(self, interp, state):
        state.top_module = "counter"
        state.modules = {
            "counter": {
                "ports": ["clk"], "regs": 32,
                "assigns": 4, "instances": [],
                "lines": 10,
            }
        }
        result = interp.eval("stat")
        assert "Number of cells" in result
        assert "counter" in result


# --- write_json (mem.json) ---

class TestWriteJson:
    def test_creates_valid_json(self, interp):
        import json
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False
        ) as f:
            path = f.name
        interp.eval(f"write_json {path}")
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        os.unlink(path)


class TestParseVerilogEdgeCases:
    def test_wide_bus_port(self):
        content = """
module wide(
    input wire [255:0] data
);
endmodule
"""
        modules = yosys_commands.parse_verilog(content)
        assert "wide" in modules
        assert "data" in str(modules["wide"]["ports"])

    def test_multiline_port_list(self):
        content = """
module multi(
    input wire clk,
    input wire rst,
    output reg [3:0] out_a,
    output reg [3:0] out_b
);
  reg [3:0] state;
endmodule
"""
        modules = yosys_commands.parse_verilog(content)
        assert "multi" in modules
        assert modules["multi"]["regs"] >= 4

    def test_parameterized_module(self):
        content = """
module param #(
    parameter WIDTH = 8
) (
    input wire [WIDTH-1:0] data
);
endmodule
"""
        modules = yosys_commands.parse_verilog(content)
        assert "param" in modules

    def test_nested_instances_count(self):
        content = """
module leaf();
  reg [7:0] data;
endmodule
module mid();
  leaf u0();
  leaf u1();
endmodule
module top();
  mid u_mid();
endmodule
"""
        modules = yosys_commands.parse_verilog(content)
        cells = yosys_commands.estimate_cells(
            modules, "top"
        )
        # Should account for 2x leaf via mid
        assert cells > 8


class TestReadVerilogFlags:
    def test_sv_flag_accepted(self, interp, capsys):
        """read_verilog -sv should not crash."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sv", delete=False
        ) as f:
            f.write("module sv_mod(); endmodule\n")
            f.flush()
            interp.eval(f"read_verilog -sv {f.name}")
            os.unlink(f.name)

    def test_defer_flag_accepted(
        self, interp, capsys
    ):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sv", delete=False
        ) as f:
            f.write("module d(); endmodule\n")
            f.flush()
            interp.eval(
                f"read_verilog -defer {f.name}"
            )
            os.unlink(f.name)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
