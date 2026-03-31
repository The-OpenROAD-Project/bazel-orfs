"""Unit tests for lint OpenROAD command implementations."""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "tcl",
        "src",
        "bin",
    ),
)
from tcl_interpreter import TclInterpreter
import openroad_commands


@pytest.fixture
def interp():
    i = TclInterpreter()
    openroad_commands.register_all(i)
    openroad_commands.reset_state()
    return i


@pytest.fixture
def state():
    openroad_commands.reset_state()
    return openroad_commands.get_state()


@pytest.fixture
def tmpdir():
    d = tempfile.mkdtemp()
    yield d
    import shutil

    shutil.rmtree(d, ignore_errors=True)


# --- Database I/O ---


class TestDatabaseIO:
    def test_write_db_creates_file(self, interp, tmpdir):
        path = os.path.join(tmpdir, "test.odb")
        interp.eval(f"write_db {path}")
        assert os.path.isfile(path)
        with open(path) as f:
            assert "lint-odb" in f.read()

    def test_orfs_write_db_creates_json(self, interp, tmpdir):
        path = os.path.join(tmpdir, "test.odb")
        interp.eval(f"orfs_write_db {path}")
        json_path = path.replace(".odb", ".json")
        assert os.path.isfile(json_path)
        with open(json_path) as f:
            data = json.load(f)
        assert "design__instance__count" in data


# --- SDC I/O ---


class TestSDC:
    def test_read_sdc_missing_file(self, interp, capsys):
        interp.eval("read_sdc /nonexistent/constraints.sdc")
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_read_sdc_existing(self, interp, state):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sdc", delete=False) as f:
            f.write("create_clock -period 1000 clk\n")
            f.flush()
            interp.eval(f"read_sdc {f.name}")
            assert state.sdc_loaded == f.name
            os.unlink(f.name)

    def test_write_sdc_creates_file(self, interp, tmpdir):
        path = os.path.join(tmpdir, "out.sdc")
        interp.eval(f"write_sdc {path}")
        assert os.path.isfile(path)


# --- Flow linter: ORFS variable validation ---
# These env vars are cleaned up after each test via the fixture.

# Env vars the linter checks — cleaned between tests
_LINT_VARS = [
    "PLATFORM",
    "DESIGN_NAME",
    "CORE_UTILIZATION",
    "CORE_ASPECT_RATIO",
    "CORE_MARGIN",
    "CORE_AREA",
    "DIE_AREA",
    "MOCK_AREA",
    "PLACE_DENSITY",
    "ROUTING_LAYER_ADJUSTMENT",
    "TNS_END_PERCENT",
    "RECOVER_POWER",
    "MACRO_PLACE_HALO",
    "CELL_PAD_IN_SITES_GLOBAL_PLACEMENT",
    "CELL_PAD_IN_SITES_DETAIL_PLACEMENT",
    "DETAILED_ROUTE_END_ITERATION",
    "MIN_PLACE_STEP_COEF",
    "MAX_PLACE_STEP_COEF",
    "SKIP_INCREMENTAL_REPAIR",
    "SKIP_CTS_REPAIR_TIMING",
    "SKIP_LAST_GASP",
    "GPL_TIMING_DRIVEN",
    "SYNTH_HIERARCHICAL",
    "SYNTH_GUT",
    "GENERATE_ARTIFACTS_ON_FAILURE",
]


@pytest.fixture(autouse=True)
def clean_env():
    """Remove lint-checked env vars before/after."""
    saved = {}
    for v in _LINT_VARS:
        saved[v] = os.environ.pop(v, None)
    os.environ["PLATFORM"] = "asap7"
    os.environ["DESIGN_NAME"] = "test"
    yield
    for v in _LINT_VARS:
        os.environ.pop(v, None)
        if saved[v] is not None:
            os.environ[v] = saved[v]


def _lint_stderr(interp, capsys):
    """Run initialize_floorplan and return stderr."""
    interp.eval("initialize_floorplan")
    return capsys.readouterr().err


class TestFloorplan:
    def test_valid_utilization(self, interp, state):
        os.environ["CORE_UTILIZATION"] = "40"
        interp.eval("initialize_floorplan")
        assert state.utilization == 40.0

    def test_invalid_utilization_zero(self, interp, capsys):
        os.environ["CORE_UTILIZATION"] = "0"
        err = _lint_stderr(interp, capsys)
        assert "LINT CORE_UTILIZATION" in err

    def test_invalid_utilization_over_100(self, interp, capsys):
        os.environ["CORE_UTILIZATION"] = "150"
        err = _lint_stderr(interp, capsys)
        assert "LINT CORE_UTILIZATION" in err

    def test_insane_die_area(self, interp, capsys):
        os.environ["DIE_AREA"] = "0 0 5000 5000"
        err = _lint_stderr(interp, capsys)
        assert "LINT DIE_AREA" in err
        assert "exceeds" in err

    def test_sane_die_area(self, interp, capsys):
        os.environ["DIE_AREA"] = "0 0 50 50"
        err = _lint_stderr(interp, capsys)
        assert "LINT DIE_AREA" not in err

    def test_die_area_sky130_large_ok(self, interp, capsys):
        """sky130 allows larger dies."""
        os.environ["PLATFORM"] = "sky130"
        os.environ["DIE_AREA"] = "0 0 5000 5000"
        err = _lint_stderr(interp, capsys)
        assert "exceeds" not in err

    def test_mock_area_too_large(self, interp, capsys):
        os.environ["MOCK_AREA"] = "200.0"
        err = _lint_stderr(interp, capsys)
        assert "LINT MOCK_AREA" in err
        assert "scale factor" in err

    def test_mock_area_sane(self, interp, capsys):
        os.environ["MOCK_AREA"] = "1.0"
        err = _lint_stderr(interp, capsys)
        assert "scale factor" not in err


class TestLintNumericRanges:
    def test_place_density_valid(self, interp, capsys):
        os.environ["PLACE_DENSITY"] = "0.65"
        err = _lint_stderr(interp, capsys)
        assert "LINT PLACE_DENSITY" not in err

    def test_place_density_over_1(self, interp, capsys):
        os.environ["PLACE_DENSITY"] = "1.5"
        err = _lint_stderr(interp, capsys)
        assert "LINT PLACE_DENSITY" in err

    def test_place_density_zero(self, interp, capsys):
        os.environ["PLACE_DENSITY"] = "0"
        err = _lint_stderr(interp, capsys)
        assert "LINT PLACE_DENSITY" in err

    def test_routing_layer_adj_valid(self, interp, capsys):
        os.environ["ROUTING_LAYER_ADJUSTMENT"] = "0.5"
        err = _lint_stderr(interp, capsys)
        assert "LINT ROUTING_LAYER" not in err

    def test_routing_layer_adj_over_1(self, interp, capsys):
        os.environ["ROUTING_LAYER_ADJUSTMENT"] = "1.5"
        err = _lint_stderr(interp, capsys)
        assert "LINT ROUTING_LAYER" in err

    def test_tns_end_percent_valid(self, interp, capsys):
        os.environ["TNS_END_PERCENT"] = "100"
        err = _lint_stderr(interp, capsys)
        assert "LINT TNS_END_PERCENT" not in err

    def test_tns_end_percent_negative(self, interp, capsys):
        os.environ["TNS_END_PERCENT"] = "-5"
        err = _lint_stderr(interp, capsys)
        assert "LINT TNS_END_PERCENT" in err

    def test_recover_power_valid(self, interp, capsys):
        os.environ["RECOVER_POWER"] = "50"
        err = _lint_stderr(interp, capsys)
        assert "LINT RECOVER_POWER" not in err

    def test_recover_power_over_100(self, interp, capsys):
        os.environ["RECOVER_POWER"] = "150"
        err = _lint_stderr(interp, capsys)
        assert "LINT RECOVER_POWER" in err

    def test_core_aspect_ratio_valid(self, interp, capsys):
        os.environ["CORE_ASPECT_RATIO"] = "1.0"
        err = _lint_stderr(interp, capsys)
        assert "LINT CORE_ASPECT" not in err

    def test_core_aspect_ratio_extreme(self, interp, capsys):
        os.environ["CORE_ASPECT_RATIO"] = "50.0"
        err = _lint_stderr(interp, capsys)
        assert "LINT CORE_ASPECT_RATIO" in err
        assert "extreme" in err

    def test_core_aspect_ratio_zero(self, interp, capsys):
        os.environ["CORE_ASPECT_RATIO"] = "0"
        err = _lint_stderr(interp, capsys)
        assert "LINT CORE_ASPECT_RATIO" in err

    def test_core_margin_valid(self, interp, capsys):
        os.environ["CORE_MARGIN"] = "2.0"
        err = _lint_stderr(interp, capsys)
        assert "LINT CORE_MARGIN" not in err

    def test_core_margin_negative(self, interp, capsys):
        os.environ["CORE_MARGIN"] = "-1.0"
        err = _lint_stderr(interp, capsys)
        assert "LINT CORE_MARGIN" in err

    def test_min_place_step_coef_valid(self, interp, capsys):
        os.environ["MIN_PLACE_STEP_COEF"] = "0.95"
        err = _lint_stderr(interp, capsys)
        assert "LINT MIN_PLACE" not in err

    def test_min_place_step_coef_extreme(self, interp, capsys):
        os.environ["MIN_PLACE_STEP_COEF"] = "2.0"
        err = _lint_stderr(interp, capsys)
        assert "LINT MIN_PLACE_STEP_COEF" in err


class TestLintIntegers:
    def test_cell_pad_valid(self, interp, capsys):
        os.environ["CELL_PAD_IN_SITES_GLOBAL_PLACEMENT"] = "2"
        err = _lint_stderr(interp, capsys)
        assert "LINT CELL_PAD" not in err

    def test_cell_pad_negative(self, interp, capsys):
        os.environ["CELL_PAD_IN_SITES_GLOBAL_PLACEMENT"] = "-1"
        err = _lint_stderr(interp, capsys)
        assert "LINT CELL_PAD" in err

    def test_drt_iterations_valid(self, interp, capsys):
        os.environ["DETAILED_ROUTE_END_ITERATION"] = "64"
        err = _lint_stderr(interp, capsys)
        assert "LINT DETAILED_ROUTE" not in err

    def test_drt_iterations_zero(self, interp, capsys):
        os.environ["DETAILED_ROUTE_END_ITERATION"] = "0"
        err = _lint_stderr(interp, capsys)
        assert "LINT DETAILED_ROUTE" in err


class TestLintBooleans:
    def test_bool_valid_0(self, interp, capsys):
        os.environ["SKIP_LAST_GASP"] = "0"
        err = _lint_stderr(interp, capsys)
        assert "LINT SKIP_LAST_GASP" not in err

    def test_bool_valid_1(self, interp, capsys):
        os.environ["SKIP_LAST_GASP"] = "1"
        err = _lint_stderr(interp, capsys)
        assert "LINT SKIP_LAST_GASP" not in err

    def test_bool_invalid(self, interp, capsys):
        os.environ["SKIP_LAST_GASP"] = "yes"
        err = _lint_stderr(interp, capsys)
        assert "LINT SKIP_LAST_GASP" in err
        assert "should be 0 or 1" in err


class TestLintCrossVariable:
    def test_util_and_die_area_both_set(self, interp, capsys):
        os.environ["CORE_UTILIZATION"] = "40"
        os.environ["DIE_AREA"] = "0 0 50 50"
        err = _lint_stderr(interp, capsys)
        assert "LINT CORE_UTILIZATION+DIE_AREA" in err

    def test_core_area_without_die(self, interp, capsys):
        os.environ["CORE_AREA"] = "5 5 45 45"
        err = _lint_stderr(interp, capsys)
        assert "LINT CORE_AREA" in err
        assert "requires DIE_AREA" in err

    def test_die_area_wrong_count(self, interp, capsys):
        os.environ["DIE_AREA"] = "0 0 50"
        err = _lint_stderr(interp, capsys)
        assert "LINT DIE_AREA" in err
        assert "expected 4" in err

    def test_macro_halo_valid(self, interp, capsys):
        os.environ["MACRO_PLACE_HALO"] = "1 1"
        err = _lint_stderr(interp, capsys)
        assert "LINT MACRO_PLACE_HALO" not in err

    def test_macro_halo_wrong_count(self, interp, capsys):
        os.environ["MACRO_PLACE_HALO"] = "1"
        err = _lint_stderr(interp, capsys)
        assert "LINT MACRO_PLACE_HALO" in err
        assert "expected 2" in err


# --- LEF/Liberty ---


class TestLef:
    def test_read_lef_missing(self, interp, capsys):
        interp.eval("read_lef /nonexistent/tech.lef")
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_write_abstract_lef_insane_size(self, interp, state, tmpdir, capsys):
        """Huge cell count should lint about size."""
        state.design_name = "huge_macro"
        state.cell_count = 100_000_000
        state.utilization = 10.0
        path = os.path.join(tmpdir, "huge.lef")
        interp.eval(f"write_abstract_lef {path}")
        captured = capsys.readouterr()
        assert "LINT LEF_SIZE" in captured.err
        assert "exceeds" in captured.err

    def test_write_abstract_lef(self, interp, state, tmpdir):
        state.design_name = "test_macro"
        state.cell_count = 1000
        state.utilization = 50.0
        path = os.path.join(tmpdir, "test_macro.lef")
        interp.eval(f"write_abstract_lef {path}")
        with open(path) as f:
            content = f.read()
        assert "MACRO test_macro" in content
        assert "SIZE" in content
        assert "END test_macro" in content

    def test_write_timing_model(self, interp, state, tmpdir):
        state.design_name = "test_macro"
        state.cell_count = 500
        path = os.path.join(tmpdir, "test_macro_typ.lib")
        interp.eval(f"write_timing_model {path}")
        with open(path) as f:
            content = f.read()
        assert "library" in content
        assert "test_macro" in content
        assert "cell" in content


# --- Link design ---


class TestLinkDesign:
    def test_empty_name(self, interp, capsys):
        interp.eval("link_design")
        captured = capsys.readouterr()
        assert "WARNING" in captured.err

    def test_valid_name(self, interp, state):
        interp.eval("link_design my_chip")
        assert state.design_name == "my_chip"


# --- Mock ODB object methods ---


class TestMockODB:
    def test_get_db(self, interp):
        result = interp.eval("set db [ord::get_db]")
        assert result == "mock_db"

    def test_method_chain(self, interp):
        os.environ["DIE_AREA"] = "0 0 50 50"
        interp.eval("set db [ord::get_db]")
        result = interp.eval("$db getTech")
        assert result == "mock_tech"
        result = interp.eval("[$db getTech] getDbUnitsPerMicron")
        assert int(result) > 0
        del os.environ["DIE_AREA"]

    def test_die_area_bbox(self, interp):
        os.environ["DIE_AREA"] = "0 0 100 200"
        interp.eval("set db [ord::get_db]")
        interp.eval("set block [[$db getChip] getBlock]")
        interp.eval("set bbox [$block getDieArea]")
        xmax = interp.eval("$bbox xMax")
        ymax = interp.eval("$bbox yMax")
        # 100 * 1000 dbu = 100000
        assert int(xmax) == 100000
        assert int(ymax) == 200000
        del os.environ["DIE_AREA"]

    def test_get_nets_empty(self, interp):
        interp.eval("set db [ord::get_db]")
        interp.eval("set block [[$db getChip] getBlock]")
        result = interp.eval("$block getNets")
        assert result == ""


# --- Verilog output ---


class TestWriteVerilog:
    def test_creates_file(self, interp, state, tmpdir):
        state.design_name = "top"
        path = os.path.join(tmpdir, "out.v")
        interp.eval(f"write_verilog {path}")
        assert os.path.isfile(path)
        with open(path) as f:
            assert "module top" in f.read()


# --- SPEF output ---


class TestWriteSpef:
    def test_creates_file(self, interp, tmpdir):
        path = os.path.join(tmpdir, "out.spef")
        interp.eval(f"write_spef {path}")
        assert os.path.isfile(path)


# --- log_cmd wrapper ---


class TestLogCmd:
    def test_delegates_to_inner(self, interp, state):
        state.design_name = ""
        interp.eval("log_cmd link_design test_chip")
        assert state.design_name == "test_chip"


# --- SDC validation ---


class TestSDCValidation:
    def test_get_ports_known(self, interp, state):
        state.ports = {"clk", "rst", "data_in"}
        result = interp.eval("get_ports clk")
        assert result == "clk"

    def test_get_ports_unknown_warns(self, interp, state, capsys):
        state.ports = {"clk", "rst"}
        interp.eval("get_ports nonexistent")
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_get_ports_multi_arg_warns(self, interp, state, capsys):
        state.ports = {"clk"}
        interp.eval("get_ports clk rst")
        captured = capsys.readouterr()
        assert "STA-0566" in captured.err

    def test_get_ports_quiet_no_multi_warn(self, interp, state, capsys):
        state.ports = {"clk"}
        interp.eval("get_ports -quiet clk rst")
        captured = capsys.readouterr()
        assert "STA-0566" not in captured.err

    def test_get_ports_wildcard_no_warn(self, interp, state, capsys):
        state.ports = {"clk"}
        interp.eval("get_ports *")
        captured = capsys.readouterr()
        assert "not found" not in captured.err

    def test_get_ports_empty_design(self, interp, state):
        """No ports loaded — no validation, no crash."""
        state.ports = set()
        result = interp.eval("get_ports anything")
        assert result == "anything"

    def test_create_clock_valid(self, interp, state):
        state.ports = {"clk"}
        interp.eval("create_clock -period 1000 clk")
        assert "clk" in state.clocks

    def test_create_clock_unknown_warns(self, interp, state, capsys):
        state.ports = {"clk"}
        interp.eval("create_clock -period 1000 bad_port")
        captured = capsys.readouterr()
        assert "not in design" in captured.err

    def test_group_path_empty_from_ok(self, interp, capsys):
        """Empty -from is valid (mirrors real OpenSTA
        no-op for empty object lists)."""
        interp.eval('group_path -name x -from "" -to y')
        captured = capsys.readouterr()
        assert "STA-0391" not in captured.err

    def test_set_input_delay_unknown_warns(self, interp, state, capsys):
        state.ports = {"clk", "data_in"}
        interp.eval("set_input_delay -clock clk 0 bad_port")
        captured = capsys.readouterr()
        assert "not in design" in captured.err

    def test_set_output_delay_unknown_warns(self, interp, state, capsys):
        state.ports = {"clk", "data_out"}
        interp.eval("set_output_delay -clock clk 0 bad_port")
        captured = capsys.readouterr()
        assert "not in design" in captured.err


class TestAllRegistersInputsOutputs:
    def test_all_registers_returns_empty(self, interp):
        result = interp.eval("all_registers")
        assert result == ""

    def test_all_inputs_returns_ports(self, interp, state):
        state.ports = {"clk", "data_in", "reset"}
        result = interp.eval("all_inputs")
        ports = result.split()
        assert "clk" in ports
        assert "data_in" in ports
        assert "reset" in ports

    def test_all_inputs_no_clocks(self, interp, state):
        state.ports = {"clk", "data_in", "reset"}
        state.clocks = {"clk": "clk"}
        result = interp.eval("all_inputs -no_clocks")
        ports = result.split()
        assert "clk" not in ports
        assert "data_in" in ports

    def test_all_outputs_returns_empty(self, interp):
        result = interp.eval("all_outputs")
        assert result == ""

    def test_platform_sdc_pattern(self, interp, state, capsys):
        """The platform SDC pattern with set_max_delay
        and group_path should work without errors."""
        state.ports = {"clk", "data_in", "data_out"}
        state.clocks = {"clk": "clk"}
        interp.eval("set non_clk_inputs [all_inputs -no_clocks]")
        interp.eval(
            "group_path -name in2reg" " -from $non_clk_inputs" " -to [all_registers]"
        )
        interp.eval(
            "group_path -name reg2out" " -from [all_registers]" " -to [all_outputs]"
        )
        captured = capsys.readouterr()
        assert "STA-0391" not in captured.err


class TestORFSHelpers:
    def test_source_env_var_if_exists_missing(self, interp):
        """source_env_var_if_exists with unset var is no-op."""
        os.environ.pop("NONEXISTENT_VAR", None)
        interp.eval("source_env_var_if_exists NONEXISTENT_VAR")

    def test_env_var_exists_and_non_empty(self, interp):
        os.environ["TEST_VAR"] = "hello"
        result = interp.eval("env_var_exists_and_non_empty TEST_VAR")
        assert result == "1"
        del os.environ["TEST_VAR"]

    def test_env_var_exists_empty(self, interp):
        os.environ["TEST_VAR"] = ""
        result = interp.eval("env_var_exists_and_non_empty TEST_VAR")
        assert result == "0"
        del os.environ["TEST_VAR"]

    def test_env_var_not_exists(self, interp):
        os.environ.pop("TEST_VAR", None)
        result = interp.eval("env_var_exists_and_non_empty TEST_VAR")
        assert result == "0"

    def test_find_macros_empty(self, interp):
        result = interp.eval("find_macros")
        assert result == ""

    def test_erase_non_stage_variables(self, interp):
        """Should be a no-op, not crash."""
        interp.eval("erase_non_stage_variables")


class TestReadVerilogPorts:
    def test_extracts_ports(self, interp, state):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sv", delete=False) as f:
            f.write(
                "module top(\n"
                "  input wire clk,\n"
                "  input wire [7:0] data_in,\n"
                "  output wire [7:0] data_out\n"
                ");\nendmodule\n"
            )
            f.flush()
            interp.eval(f"read_verilog {f.name}")
            os.unlink(f.name)
        assert "clk" in state.ports
        assert "data_in" in state.ports
        assert "data_out" in state.ports

    def test_no_ports_from_missing_file(self, interp, state):
        interp.eval("read_verilog /nonexistent.v")
        assert len(state.ports) == 0


class TestWriteTimingModelPins:
    def test_pins_from_state_ports(self, interp, state, tmpdir):
        state.design_name = "fakeram"
        state.cell_count = 100
        state.ports = {"addr_in", "we_in", "rd_out", "clk"}
        path = os.path.join(tmpdir, "fakeram_typ.lib")
        interp.eval(f"write_timing_model {path}")
        with open(path) as f:
            content = f.read()
        assert "pin (addr_in)" in content
        assert "pin (we_in)" in content
        assert "pin (rd_out)" in content
        assert "pin (clk)" in content

    def test_pins_from_rtlil(self, interp, state, tmpdir):
        """Ports loaded from RTLIL when state.ports empty."""
        state.design_name = "blk"
        state.cell_count = 50
        state.ports = set()
        results = os.path.join(tmpdir, "results")
        os.makedirs(results)
        os.environ["RESULTS_DIR"] = results
        # Write mock RTLIL with port wires
        rtlil = os.path.join(results, "1_1_yosys_canonicalize.rtlil")
        with open(rtlil, "w") as f:
            f.write(
                "# Mock RTLIL\n"
                "module \\blk\n"
                "  wire \\din\n"
                "  wire \\dout\n"
                "  wire \\ck\n"
                "end\n"
            )
        path = os.path.join(tmpdir, "blk_typ.lib")
        interp.eval(f"write_timing_model {path}")
        with open(path) as f:
            content = f.read()
        assert "pin (din)" in content
        assert "pin (dout)" in content
        assert "pin (ck)" in content

    def test_no_pins_when_no_ports(self, interp, state, tmpdir):
        state.design_name = "empty"
        state.cell_count = 10
        state.ports = set()
        os.environ["RESULTS_DIR"] = tmpdir
        path = os.path.join(tmpdir, "empty_typ.lib")
        interp.eval(f"write_timing_model {path}")
        with open(path) as f:
            content = f.read()
        assert "pin (" not in content


class TestWriteSdcFlags:
    def test_no_timestamp_flag(self, interp, tmpdir):
        path = os.path.join(tmpdir, "out.sdc")
        interp.eval(f"write_sdc -no_timestamp {path}")
        assert os.path.isfile(path)


class TestWriteDef:
    def test_creates_file(self, interp, tmpdir):
        path = os.path.join(tmpdir, "out.def")
        interp.eval(f"write_def {path}")
        assert os.path.isfile(path)


class TestCoreAreaBbox:
    def test_core_area_with_margin(self, interp):
        os.environ["DIE_AREA"] = "0 0 100 100"
        os.environ.pop("CORE_AREA", None)
        os.environ["CORE_MARGIN"] = "5"
        interp.eval("set db [ord::get_db]")
        interp.eval("set block [[$db getChip] getBlock]")
        interp.eval("set bbox [$block getCoreArea]")
        xmin = int(interp.eval("$bbox xMin"))
        ymin = int(interp.eval("$bbox yMin"))
        xmax = int(interp.eval("$bbox xMax"))
        ymax = int(interp.eval("$bbox yMax"))
        # margin=5um, dbu=1000 → 5000
        assert xmin == 5000
        assert ymin == 5000
        assert xmax == 95000
        assert ymax == 95000
        del os.environ["DIE_AREA"]
        del os.environ["CORE_MARGIN"]

    def test_explicit_core_area(self, interp):
        os.environ["DIE_AREA"] = "0 0 100 100"
        os.environ["CORE_AREA"] = "10 10 90 90"
        interp.eval("set db [ord::get_db]")
        interp.eval("set block [[$db getChip] getBlock]")
        interp.eval("set bbox [$block getCoreArea]")
        xmin = int(interp.eval("$bbox xMin"))
        assert xmin == 10000
        del os.environ["DIE_AREA"]
        del os.environ["CORE_AREA"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
