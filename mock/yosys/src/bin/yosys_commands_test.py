"""Unit tests for mock Yosys command implementations."""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(__file__))
# tcl_interpreter lives in mock-openroad
sys.path.insert(0, os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "..", "openroad", "src", "bin",
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


@pytest.fixture
def tmpdir():
    d = tempfile.mkdtemp()
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


# --- Verilog parsing ---

class TestParseVerilog:
    def test_simple_module(self):
        content = (
            "module top(\n"
            "  input wire clk,\n"
            "  input wire [7:0] data_in,\n"
            "  output wire [7:0] data_out\n"
            ");\n"
            "  assign data_out = data_in;\n"
            "endmodule\n"
        )
        modules = yosys_commands.parse_verilog(content)
        assert "top" in modules
        assert "clk" in modules["top"]["ports"]
        assert "data_in" in modules["top"]["ports"]
        assert "data_out" in modules["top"]["ports"]
        assert modules["top"]["assigns"] == 1

    def test_register_count(self):
        content = (
            "module counter(\n"
            "  input wire clk\n"
            ");\n"
            "  reg [7:0] count;\n"
            "  reg single_bit;\n"
            "endmodule\n"
        )
        modules = yosys_commands.parse_verilog(content)
        assert "counter" in modules
        # 8-bit reg + 1-bit reg = 9
        assert modules["counter"]["regs"] == 9

    def test_module_instantiation(self):
        content = (
            "module top();\n"
            "  submod u0 (.clk(clk));\n"
            "endmodule\n"
        )
        modules = yosys_commands.parse_verilog(content)
        assert "submod" in modules["top"]["instances"]

    def test_empty_input(self):
        modules = yosys_commands.parse_verilog("")
        assert modules == {}

    def test_multiple_modules(self):
        content = (
            "module a();\nendmodule\n"
            "module b();\nendmodule\n"
        )
        modules = yosys_commands.parse_verilog(content)
        assert "a" in modules
        assert "b" in modules


# --- Cell estimation ---

class TestEstimateCells:
    def test_empty_modules(self):
        assert yosys_commands.estimate_cells({}) == 100

    def test_simple_module(self):
        modules = {
            "top": {
                "ports": ["clk", "out"],
                "regs": 8,
                "assigns": 3,
                "instances": [],
                "lines": 10,
            }
        }
        cells = yosys_commands.estimate_cells(modules, "top")
        # 8 regs + 3*4 assigns + 10*2 lines = 40
        assert cells == 40

    def test_with_submodule(self):
        modules = {
            "top": {
                "ports": [],
                "regs": 0,
                "assigns": 0,
                "instances": ["sub"],
                "lines": 5,
            },
            "sub": {
                "ports": [],
                "regs": 16,
                "assigns": 2,
                "instances": [],
                "lines": 10,
            },
        }
        cells = yosys_commands.estimate_cells(modules, "top")
        # top: 0 + 0 + 5*2 = 10
        # sub: 16 + 2*4 + 10*2 = 44
        # total = 54
        assert cells == 54


# --- Read commands ---

class TestReadVerilog:
    def test_reads_file(self, interp, state, tmpdir):
        path = os.path.join(tmpdir, "test.v")
        with open(path, "w") as f:
            f.write(
                "module chip(\n"
                "  input wire clk,\n"
                "  output wire q\n"
                ");\nendmodule\n"
            )
        interp.eval(f"read_verilog {path}")
        assert "chip" in state.modules
        assert len(state.verilog_files) == 1

    def test_sv_flag_ignored(self, interp, state, tmpdir):
        path = os.path.join(tmpdir, "test.sv")
        with open(path, "w") as f:
            f.write("module sv_mod();\nendmodule\n")
        interp.eval(f"read_verilog -sv {path}")
        assert "sv_mod" in state.modules

    def test_missing_file(self, interp, state, capsys):
        interp.eval("read_verilog /nonexistent.v")
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
        assert len(state.verilog_files) == 0


class TestReadLiberty:
    def test_noop(self, interp):
        """read_liberty is a no-op in mock."""
        interp.eval("read_liberty -lib /some/file.lib")


# --- Hierarchy ---

class TestHierarchy:
    def test_sets_top_module(self, interp, state):
        interp.eval("hierarchy -top my_top")
        assert state.top_module == "my_top"

    def test_check_flag(self, interp, state):
        interp.eval("hierarchy -check -top my_top")
        assert state.top_module == "my_top"

    def test_missing_top_warns(
        self, interp, state, tmpdir, capsys
    ):
        path = os.path.join(tmpdir, "test.v")
        with open(path, "w") as f:
            f.write("module real_top();\nendmodule\n")
        interp.eval(f"read_verilog {path}")
        interp.eval("hierarchy -top wrong_name")
        captured = capsys.readouterr()
        assert "not found" in captured.err


# --- Write commands ---

class TestWriteVerilog:
    def test_creates_netlist(self, interp, state, tmpdir):
        state.top_module = "chip"
        state.design_name = "chip"
        state.modules = {
            "chip": {
                "ports": ["clk", "d", "q"],
                "regs": 1,
                "assigns": 0,
                "instances": [],
                "lines": 5,
            }
        }
        path = os.path.join(tmpdir, "netlist.v")
        interp.eval(f"write_verilog {path}")
        with open(path) as f:
            content = f.read()
        assert "module chip" in content
        assert "clk" in content


class TestWriteRtlil:
    def test_creates_rtlil(self, interp, state, tmpdir):
        state.modules = {
            "top": {
                "ports": ["clk", "data"],
                "regs": 0,
                "assigns": 0,
                "instances": [],
                "lines": 3,
            }
        }
        path = os.path.join(tmpdir, "out.rtlil")
        interp.eval(f"write_rtlil {path}")
        with open(path) as f:
            content = f.read()
        assert "module \\top" in content
        assert "wire \\clk" in content
        assert "wire \\data" in content


class TestWriteJson:
    def test_creates_json(self, interp, tmpdir):
        path = os.path.join(tmpdir, "mem.json")
        interp.eval(f"write_json {path}")
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, dict)


# --- Synthesis ---

class TestSynth:
    def test_estimates_cells(self, interp, state):
        state.modules = {
            "top": {
                "ports": [],
                "regs": 32,
                "assigns": 10,
                "instances": [],
                "lines": 20,
            }
        }
        state.top_module = "top"
        interp.eval("synth")
        # 32 + 10*4 + 20*2 = 112
        assert state.cell_count_estimate == 112


class TestStat:
    def test_produces_report(self, interp, state, capsys):
        state.cell_count_estimate = 500
        state.top_module = "chip"
        result = interp.eval("stat")
        assert "500" in result
        assert "chip" in result


class TestTee:
    def test_captures_to_file(self, interp, state, tmpdir):
        state.cell_count_estimate = 42
        state.top_module = "t"
        path = os.path.join(tmpdir, "stats.txt")
        interp.eval(f"tee -o {path} stat")
        assert os.path.isfile(path)
        with open(path) as f:
            content = f.read()
        assert "42" in content


# --- No-op passes ---

class TestNoOpPasses:
    """All synthesis passes should be no-ops that don't crash."""

    PASSES = [
        "opt_clean", "opt", "flatten", "abc",
        "techmap", "dfflibmap", "memory",
        "memory_libmap", "proc", "clean",
        "rename", "check", "select", "delete",
        "setattr", "scratchpad", "design",
        "autoname", "chformal", "async2sync",
        "dff2dffe", "opt_merge", "opt_muxtree",
        "opt_reduce", "opt_expr", "peepopt",
        "wreduce", "share", "alumacc",
        "pmuxtree", "muxcover",
    ]

    @pytest.mark.parametrize("cmd", PASSES)
    def test_pass_noop(self, interp, cmd):
        result = interp.eval(cmd)
        assert result == ""


class TestLog:
    def test_prints_to_stderr(self, interp, capsys):
        interp.eval("log hello world")
        captured = capsys.readouterr()
        assert "hello world" in captured.err


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
