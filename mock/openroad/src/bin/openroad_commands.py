"""Lint OpenROAD command implementations.

Each function is registered as a TCL command in the lint OpenROAD
interpreter. Commands create the output files that bazel-orfs expects
and collect estimation data.
"""

import json
import os
import re
import sys


class MockDesignState:
    """Tracks design state across lint OpenROAD commands."""

    def __init__(self):
        self.design_name = ""
        self.platform = ""
        self.cell_count = 0
        self.die_area = None  # (x1, y1, x2, y2) in microns
        self.core_area = None
        self.utilization = 0.0
        self.modules_loaded = []
        self.lefs_loaded = []
        self.libs_loaded = []
        self.sdc_loaded = None
        self.current_stage = ""
        self.ports = set()  # known design ports
        self.clocks = {}  # clock_name -> port_name

    @property
    def results_dir(self):
        return os.environ.get("RESULTS_DIR", ".")

    @property
    def log_dir(self):
        return os.environ.get("LOG_DIR", ".")

    @property
    def reports_dir(self):
        return os.environ.get("REPORTS_DIR", ".")

    @property
    def objects_dir(self):
        return os.environ.get("OBJECTS_DIR", ".")


# Global design state
_state = MockDesignState()


def get_state():
    return _state


def reset_state():
    global _state
    _state = MockDesignState()


def _ensure_dir(path):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def _touch(path, content=""):
    _ensure_dir(path)
    with open(path, "w") as f:
        f.write(content)


# --- Database I/O ---

def cmd_read_db(interp, args):
    """read_db <path>"""
    if args:
        path = args[0]
        print(f"lint: read_db {path}", file=sys.stderr)
    return ""


def cmd_write_db(interp, args):
    """write_db <path>"""
    if args:
        path = args[0]
        _touch(path, "lint-odb-v1\n")
        print(f"lint: write_db {path}", file=sys.stderr)
    return ""


def cmd_orfs_write_db(interp, args):
    """orfs_write_db <path> — ORFS wrapper that also writes metrics."""
    if args:
        path = args[0]
        _touch(path, "lint-odb-v1\n")
        # Also create the metrics JSON alongside
        json_path = path.replace(".odb", ".json")
        metrics = {
            "run__flow__generate_date": "mock",
            "design__instance__count": _state.cell_count,
            "design__instance__area": _state.cell_count * 0.5,
        }
        _touch(json_path, json.dumps(metrics, indent=2) + "\n")
        print(f"lint: orfs_write_db {path}", file=sys.stderr)
    return ""


# --- SDC I/O ---

def cmd_read_sdc(interp, args):
    """read_sdc <path>"""
    remaining = list(args)
    while remaining and remaining[0].startswith("-"):
        remaining.pop(0)
    if remaining:
        path = remaining[0]
        _state.sdc_loaded = path
        if not os.path.isfile(path):
            print(
                f"lint: WARNING: SDC not found:"
                f" {path}",
                file=sys.stderr,
            )
        else:
            print(
                f"lint: read_sdc {path}",
                file=sys.stderr,
            )
    return ""


def cmd_write_sdc(interp, args):
    """write_sdc <path>"""
    if args:
        path = args[0]
        # Copy source SDC if available, else create minimal
        content = "# Mock SDC\n"
        if _state.sdc_loaded and os.path.isfile(_state.sdc_loaded):
            with open(_state.sdc_loaded) as f:
                content = f.read()
        _touch(path, content)
        print(f"lint: write_sdc {path}", file=sys.stderr)
    return ""


def cmd_orfs_write_sdc(interp, args):
    """orfs_write_sdc <path>"""
    return cmd_write_sdc(interp, args)


# --- LEF/Liberty I/O ---

def cmd_read_lef(interp, args):
    """read_lef <path>"""
    remaining = list(args)
    while remaining and remaining[0].startswith("-"):
        remaining.pop(0)
    if remaining:
        path = remaining[0]
        _state.lefs_loaded.append(path)
        if not os.path.isfile(path):
            print(
                f"lint: WARNING: LEF not found:"
                f" {path}",
                file=sys.stderr,
            )
    return ""


def cmd_read_liberty(interp, args):
    """read_liberty <path>"""
    remaining = list(args)
    while remaining and remaining[0].startswith("-"):
        remaining.pop(0)
    if remaining:
        _state.libs_loaded.append(remaining[0])
    return ""


# --- Verilog I/O ---

def cmd_read_verilog(interp, args):
    """read_verilog <path> — also extract port names."""
    if args:
        path = args[-1]
        print(f"lint: read_verilog {path}", file=sys.stderr)
        if os.path.isfile(path):
            _extract_ports_from_verilog(path)
    return ""


def _extract_ports_from_verilog(path):
    """Parse Verilog for port declarations and add to state."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                m = re.match(
                    r"(?:input|output|inout)\s+"
                    r"(?:wire|reg|logic)?\s*"
                    r"(?:\[.*?\])?\s*(\w+)",
                    line,
                )
                if m:
                    _state.ports.add(m.group(1))
    except OSError:
        pass


def cmd_write_verilog(interp, args):
    """write_verilog <path>"""
    remaining = list(args)
    while remaining and remaining[0].startswith("-"):
        remaining.pop(0)
    if remaining:
        path = remaining[0]
        name = _state.design_name or "mock_design"
        _touch(path, f"// Mock netlist\nmodule {name}();\nendmodule\n")
        print(f"lint: write_verilog {path}", file=sys.stderr)
    return ""


def cmd_write_spef(interp, args):
    """write_spef <path>"""
    if args:
        path = args[0]
        _touch(path, "*SPEF mock\n")
        print(f"lint: write_spef {path}", file=sys.stderr)
    return ""


# --- Design commands ---

def cmd_link_design(interp, args):
    """link_design <name>"""
    if args:
        _state.design_name = args[0]
    else:
        print(
            "lint: WARNING: link_design called"
            " with no design name",
            file=sys.stderr,
        )
    return ""


# --- Flow linter: ORFS variable validation ---
# Derived from upstream variables.yaml semantics.
# Thresholds are PDK-dependent: ASAP7 (7nm) vs sky130 (130nm).

# Maximum sane die dimension in microns
_PDK_MAX_DIE_UM = {
    "asap7": 500.0,
    "sky130": 10000.0,
    "gf180": 10000.0,
}
_MAX_DIE_UM = 500.0  # default, overridden by _get_max_die()


def _get_max_die():
    platform = os.environ.get("PLATFORM", "asap7").lower()
    return _PDK_MAX_DIE_UM.get(platform, 500.0)


def _lint(name, msg):
    """Print a flow-lint warning."""
    print(
        f"lint: LINT {name}: {msg}",
        file=sys.stderr,
    )


def validate_env_vars():
    """Validate ORFS environment variables.

    Called once per stage from initialize_floorplan.
    Checks types, ranges, and cross-variable consistency
    based on variables.yaml semantics.
    """
    max_die = _get_max_die()
    platform = os.environ.get(
        "PLATFORM", "asap7"
    ).lower()

    # --- Required variables ---
    for var in (
        "PLATFORM", "DESIGN_NAME",
    ):
        if not os.environ.get(var, ""):
            _lint(var, "required but not set")

    # --- CORE_UTILIZATION: float (0, 100] ---
    val = os.environ.get("CORE_UTILIZATION", "")
    if val:
        try:
            u = float(val)
            if u <= 0 or u > 100:
                _lint(
                    "CORE_UTILIZATION",
                    f"{u} out of range (0, 100]",
                )
        except ValueError:
            _lint(
                "CORE_UTILIZATION",
                f"'{val}' is not a number",
            )

    # --- CORE_ASPECT_RATIO: float, default 1.0 ---
    val = os.environ.get("CORE_ASPECT_RATIO", "")
    if val:
        try:
            ar = float(val)
            if ar <= 0:
                _lint(
                    "CORE_ASPECT_RATIO",
                    f"{ar} must be positive",
                )
            elif ar < 0.1 or ar > 10.0:
                _lint(
                    "CORE_ASPECT_RATIO",
                    f"{ar} is extreme"
                    f" (typical: 0.5–2.0)",
                )
        except ValueError:
            _lint(
                "CORE_ASPECT_RATIO",
                f"'{val}' is not a number",
            )

    # --- CORE_MARGIN: float, default 1.0 ---
    val = os.environ.get("CORE_MARGIN", "")
    if val:
        parts = val.split()
        for p in parts:
            try:
                m = float(p)
                if m < 0:
                    _lint(
                        "CORE_MARGIN",
                        f"{m} must be non-negative",
                    )
                elif m > max_die / 4:
                    _lint(
                        "CORE_MARGIN",
                        f"{m}um is >25% of max die"
                        f" ({max_die}um)",
                    )
            except ValueError:
                _lint(
                    "CORE_MARGIN",
                    f"'{p}' is not a number",
                )

    # --- PLACE_DENSITY: float (0, 1] ---
    val = os.environ.get("PLACE_DENSITY", "")
    if val:
        try:
            d = float(val)
            if d <= 0 or d > 1.0:
                _lint(
                    "PLACE_DENSITY",
                    f"{d} out of range (0, 1.0]",
                )
        except ValueError:
            _lint(
                "PLACE_DENSITY",
                f"'{val}' is not a number",
            )

    # --- ROUTING_LAYER_ADJUSTMENT: float [0, 1] ---
    val = os.environ.get(
        "ROUTING_LAYER_ADJUSTMENT", ""
    )
    if val:
        try:
            a = float(val)
            if a < 0 or a > 1.0:
                _lint(
                    "ROUTING_LAYER_ADJUSTMENT",
                    f"{a} out of range [0, 1.0]",
                )
        except ValueError:
            _lint(
                "ROUTING_LAYER_ADJUSTMENT",
                f"'{val}' is not a number",
            )

    # --- TNS_END_PERCENT: [0, 100] ---
    val = os.environ.get("TNS_END_PERCENT", "")
    if val:
        try:
            t = float(val)
            if t < 0 or t > 100:
                _lint(
                    "TNS_END_PERCENT",
                    f"{t} out of range [0, 100]",
                )
        except ValueError:
            _lint(
                "TNS_END_PERCENT",
                f"'{val}' is not a number",
            )

    # --- RECOVER_POWER: [0, 100] ---
    val = os.environ.get("RECOVER_POWER", "")
    if val:
        try:
            r = float(val)
            if r < 0 or r > 100:
                _lint(
                    "RECOVER_POWER",
                    f"{r} out of range [0, 100]",
                )
        except ValueError:
            _lint(
                "RECOVER_POWER",
                f"'{val}' is not a number",
            )

    # --- DIE_AREA: 4 floats, sane size ---
    val = os.environ.get("DIE_AREA", "")
    if val:
        parts = val.split()
        if len(parts) != 4:
            _lint(
                "DIE_AREA",
                f"expected 4 values (X1 Y1 X2 Y2),"
                f" got {len(parts)}",
            )
        else:
            try:
                coords = [float(x) for x in parts]
                w = coords[2] - coords[0]
                h = coords[3] - coords[1]
                if w <= 0 or h <= 0:
                    _lint(
                        "DIE_AREA",
                        f"non-positive size"
                        f" {w:.1f}x{h:.1f}um",
                    )
                elif w > max_die or h > max_die:
                    _lint(
                        "DIE_AREA",
                        f"{w:.0f}x{h:.0f}um exceeds"
                        f" {max_die}um for"
                        f" {platform}",
                    )
            except ValueError:
                _lint(
                    "DIE_AREA",
                    f"non-numeric values: '{val}'",
                )

    # --- MOCK_AREA: scale factor ---
    val = os.environ.get("MOCK_AREA", "")
    if val:
        try:
            s = float(val)
            if s <= 0:
                _lint(
                    "MOCK_AREA",
                    f"{s} must be positive",
                )
            elif s > 10.0:
                _lint(
                    "MOCK_AREA",
                    f"{s} — this is a scale factor,"
                    f" not absolute area"
                    f" (try 1.0 for 1:1)",
                )
        except ValueError:
            _lint(
                "MOCK_AREA",
                f"'{val}' is not a number",
            )

    # --- MACRO_PLACE_HALO: 2 floats (H V) ---
    val = os.environ.get("MACRO_PLACE_HALO", "")
    if val:
        parts = val.split()
        if len(parts) != 2:
            _lint(
                "MACRO_PLACE_HALO",
                f"expected 2 values (H V),"
                f" got {len(parts)}",
            )
        else:
            for p in parts:
                try:
                    h = float(p)
                    if h < 0:
                        _lint(
                            "MACRO_PLACE_HALO",
                            f"{h} must be"
                            f" non-negative",
                        )
                except ValueError:
                    _lint(
                        "MACRO_PLACE_HALO",
                        f"'{p}' is not a number",
                    )

    # --- CELL_PAD_IN_SITES_*: int >= 0 ---
    for var in (
        "CELL_PAD_IN_SITES_GLOBAL_PLACEMENT",
        "CELL_PAD_IN_SITES_DETAIL_PLACEMENT",
    ):
        val = os.environ.get(var, "")
        if val:
            try:
                n = int(val)
                if n < 0:
                    _lint(var, f"{n} must be >= 0")
            except ValueError:
                _lint(var, f"'{val}' is not an int")

    # --- DETAILED_ROUTE_END_ITERATION: int > 0 ---
    val = os.environ.get(
        "DETAILED_ROUTE_END_ITERATION", ""
    )
    if val:
        try:
            n = int(val)
            if n <= 0:
                _lint(
                    "DETAILED_ROUTE_END_ITERATION",
                    f"{n} must be positive",
                )
        except ValueError:
            _lint(
                "DETAILED_ROUTE_END_ITERATION",
                f"'{val}' is not an int",
            )

    # --- MIN/MAX_PLACE_STEP_COEF: float ---
    for var, lo, hi in (
        ("MIN_PLACE_STEP_COEF", 0.90, 1.10),
        ("MAX_PLACE_STEP_COEF", 0.95, 1.25),
    ):
        val = os.environ.get(var, "")
        if val:
            try:
                c = float(val)
                if c < lo or c > hi:
                    _lint(
                        var,
                        f"{c} outside typical"
                        f" range [{lo}, {hi}]",
                    )
            except ValueError:
                _lint(var, f"'{val}' is not a number")

    # --- Boolean flags: should be 0 or 1 ---
    bool_vars = [
        "SKIP_INCREMENTAL_REPAIR",
        "SKIP_CTS_REPAIR_TIMING",
        "SKIP_LAST_GASP",
        "SKIP_GATE_CLONING",
        "SKIP_PIN_SWAP",
        "SKIP_VT_SWAP",
        "SKIP_ANTENNA_REPAIR",
        "SKIP_DETAILED_ROUTE",
        "SKIP_REPORT_METRICS",
        "SYNTH_HIERARCHICAL",
        "SYNTH_GUT",
        "SYNTH_REPEATABLE_BUILD",
        "SYNTH_MOCK_LARGE_MEMORIES",
        "GPL_TIMING_DRIVEN",
        "GPL_ROUTABILITY_DRIVEN",
        "EQUIVALENCE_CHECK",
        "DONT_BUFFER_PORTS",
        "GENERATE_ARTIFACTS_ON_FAILURE",
    ]
    for var in bool_vars:
        val = os.environ.get(var, "")
        if val and val not in ("0", "1"):
            _lint(var, f"'{val}' should be 0 or 1")

    # --- Cross-variable: CORE_UTILIZATION vs DIE_AREA ---
    has_util = bool(
        os.environ.get("CORE_UTILIZATION", "")
    )
    has_die = bool(os.environ.get("DIE_AREA", ""))
    has_core = bool(os.environ.get("CORE_AREA", ""))
    if has_util and has_die:
        _lint(
            "CORE_UTILIZATION+DIE_AREA",
            "both set — DIE_AREA takes precedence,"
            " CORE_UTILIZATION is ignored",
        )
    if has_core and not has_die:
        _lint(
            "CORE_AREA",
            "set without DIE_AREA —"
            " CORE_AREA requires DIE_AREA",
        )


def cmd_initialize_floorplan(interp, args):
    """initialize_floorplan — reads DIE_AREA/CORE_UTILIZATION."""
    # Run flow linter on all ORFS variables
    validate_env_vars()

    die_area = os.environ.get("DIE_AREA", "")
    core_util = os.environ.get("CORE_UTILIZATION", "50")
    if die_area:
        coords = [float(x) for x in die_area.split()]
        if len(coords) == 4:
            _state.die_area = tuple(coords)
    util = float(core_util) if core_util else 50.0
    _state.utilization = util
    print(
        f"lint: initialize_floorplan"
        f" (util={util}%)",
        file=sys.stderr,
    )
    return ""


def cmd_make_tracks(interp, args):
    return ""


def cmd_global_connect(interp, args):
    return ""


def cmd_add_global_connection(interp, args):
    return ""


def cmd_set_global_routing_layer_adjustment(interp, args):
    return ""


# --- Placement ---

def cmd_global_placement(interp, args):
    print("lint: global_placement (skipped)", file=sys.stderr)
    return ""


def cmd_detailed_placement(interp, args):
    print("lint: detailed_placement (skipped)", file=sys.stderr)
    return ""


def cmd_improve_placement(interp, args):
    return ""


def cmd_optimize_mirroring(interp, args):
    return ""


# --- CTS ---

def cmd_clock_tree_synthesis(interp, args):
    print("lint: clock_tree_synthesis (skipped)", file=sys.stderr)
    return ""


def cmd_set_propagated_clock(interp, args):
    return ""


# --- Routing ---

def cmd_global_route(interp, args):
    print("lint: global_route (skipped)", file=sys.stderr)
    return ""


def cmd_detailed_route(interp, args):
    print("lint: detailed_route (skipped)", file=sys.stderr)
    return ""


def cmd_estimate_parasitics(interp, args):
    return ""


# --- Repair / Optimization ---

def cmd_repair_timing(interp, args):
    return ""


def cmd_repair_design(interp, args):
    return ""


def cmd_repair_tie_fanout(interp, args):
    return ""


def cmd_remove_buffers(interp, args):
    return ""


def cmd_buffer_ports(interp, args):
    return ""


def cmd_set_dont_use(interp, args):
    return ""


# --- Reports ---

def cmd_report_design_area(interp, args):
    return "Design area 0.000 u^2 0% utilization."


def cmd_report_worst_slack(interp, args):
    return ""


def cmd_report_tns(interp, args):
    return ""


def cmd_report_wns(interp, args):
    return ""


def cmd_report_power(interp, args):
    return ""


def cmd_report_checks(interp, args):
    return ""


def cmd_report_clock_skew(interp, args):
    return ""


def cmd_report_floating_nets(interp, args):
    return ""


def cmd_report_cell_usage(interp, args):
    return ""


# --- Database query ---

def cmd_get_db(interp, args):
    """ord::get_db — return a mock database handle."""
    # Register mock ODB object methods
    _register_mock_odb_methods(interp)
    return "mock_db"


def cmd_get_db_block(interp, args):
    """get the current block from db."""
    return "mock_block"


def _register_mock_odb_methods(interp):
    """Register mock ODB object method commands.

    In TCL, [$db getTech] calls "mock_db getTech". We register
    command handlers for these mock object method patterns.
    """
    dbu = 1000  # database units per micron

    # Die/core area from env or defaults
    die = os.environ.get("DIE_AREA", "0 0 100 100").split()
    core = os.environ.get("CORE_AREA", "")
    if not core:
        margin = float(os.environ.get("CORE_MARGIN", "2"))
        core = [
            str(float(die[0]) + margin),
            str(float(die[1]) + margin),
            str(float(die[2]) - margin),
            str(float(die[3]) - margin),
        ]
    else:
        core = core.split()

    def _mock_method(interp, args):
        """Handle any mock object method call."""
        if not args:
            return "mock_obj"
        method = args[0]
        # Database methods
        if method == "getTech":
            return "mock_tech"
        if method == "getDbUnitsPerMicron":
            return str(dbu)
        if method == "getChip":
            return "mock_chip"
        if method == "getBlock":
            return "mock_block"
        # Block methods
        if method == "getDieArea":
            return "mock_die_bbox"
        if method == "getCoreArea":
            return "mock_core_bbox"
        if method == "getNets":
            return ""  # empty list
        if method == "getName":
            return _state.design_name or "mock"
        if method == "getSigType":
            return "SIGNAL"
        # Bbox methods (return in DBU)
        if method == "xMin":
            return str(int(float(die[0]) * dbu))
        if method == "yMin":
            return str(int(float(die[1]) * dbu))
        if method == "xMax":
            return str(int(float(die[2]) * dbu))
        if method == "yMax":
            return str(int(float(die[3]) * dbu))
        return "mock_obj"

    def _mock_core_method(interp, args):
        if not args:
            return "mock_obj"
        method = args[0]
        if method == "xMin":
            return str(int(float(core[0]) * dbu))
        if method == "yMin":
            return str(int(float(core[1]) * dbu))
        if method == "xMax":
            return str(int(float(core[2]) * dbu))
        if method == "yMax":
            return str(int(float(core[3]) * dbu))
        return "mock_obj"

    for name in [
        "mock_db", "mock_tech", "mock_chip",
        "mock_block", "mock_die_bbox", "mock_obj",
    ]:
        interp.register_command(name, _mock_method)
    interp.register_command("mock_core_bbox", _mock_core_method)


def cmd_get_cells(interp, args):
    """get_cells — return empty list."""
    return ""


def cmd_get_ports(interp, args):
    """get_ports — validate port names against design."""
    remaining = list(args)
    quiet = False
    while remaining and remaining[0].startswith("-"):
        if remaining[0] == "-quiet":
            quiet = True
        remaining.pop(0)
    if len(remaining) > 1 and not quiet:
        print(
            "lint: WARNING: get_ports with multiple"
            " positional args (STA-0566 in real"
            " OpenSTA)",
            file=sys.stderr,
        )
    for port_name in remaining:
        # Wildcards: skip validation for glob patterns
        if "*" in port_name or "?" in port_name:
            continue
        if (_state.ports
                and port_name not in _state.ports):
            print(
                f"lint: WARNING: get_ports"
                f" '{port_name}' — port not found"
                f" in design"
                f" (known: {sorted(_state.ports)[:10]})",
                file=sys.stderr,
            )
    return " ".join(remaining)


def cmd_get_nets(interp, args):
    return ""


def cmd_get_pins(interp, args):
    return ""


def cmd_get_clocks(interp, args):
    return ""


def cmd_all_registers(interp, args):
    """all_registers — return empty list (mock has no real cells)."""
    return ""


def cmd_all_inputs(interp, args):
    """all_inputs — return known input ports.

    Supports -no_clocks flag to exclude clock ports.
    """
    remaining = list(args)
    no_clocks = False
    while remaining and remaining[0].startswith("-"):
        if remaining[0] == "-no_clocks":
            no_clocks = True
        remaining.pop(0)
    # Return known ports (from Verilog parse) as space-separated list
    ports = set(_state.ports)
    if no_clocks and _state.clocks:
        clock_ports = {
            v for v in _state.clocks.values() if v
        }
        ports -= clock_ports
    return " ".join(sorted(ports))


def cmd_all_outputs(interp, args):
    """all_outputs — return empty list (mock doesn't track direction)."""
    return ""


def cmd_create_clock(interp, args):
    """create_clock — validate clock port exists."""
    remaining = list(args)
    period = None
    name = None
    port_arg = None
    while remaining:
        if remaining[0] == "-period":
            remaining.pop(0)
            period = remaining.pop(0) if remaining else None
        elif remaining[0] == "-name":
            remaining.pop(0)
            name = remaining.pop(0) if remaining else None
        elif remaining[0].startswith("-"):
            remaining.pop(0)
        else:
            port_arg = remaining.pop(0)
    if port_arg and _state.ports:
        # port_arg might be [get_ports clk] result
        port_name = port_arg.strip()
        if (port_name
                and port_name not in _state.ports
                and not port_name.startswith("{")):
            print(
                f"lint: WARNING: create_clock on"
                f" '{port_name}' — port not in design",
                file=sys.stderr,
            )
    clock_name = name or port_arg or "clk"
    _state.clocks[clock_name] = port_arg
    return ""


def cmd_set_clock_uncertainty(interp, args):
    return ""


def cmd_set_input_delay(interp, args):
    """set_input_delay — validate port exists."""
    remaining = list(args)
    while remaining and remaining[0].startswith("-"):
        remaining.pop(0)
        if remaining:
            remaining.pop(0)  # skip flag value
    # Last arg is the port list
    if remaining and _state.ports:
        port = remaining[-1].strip()
        if (port and port not in _state.ports
                and not port.startswith("{")):
            print(
                f"lint: WARNING: set_input_delay on"
                f" '{port}' — port not in design",
                file=sys.stderr,
            )
    return ""


def cmd_set_output_delay(interp, args):
    """set_output_delay — validate port exists."""
    remaining = list(args)
    while remaining and remaining[0].startswith("-"):
        remaining.pop(0)
        if remaining:
            remaining.pop(0)
    if remaining and _state.ports:
        port = remaining[-1].strip()
        if (port and port not in _state.ports
                and not port.startswith("{")):
            print(
                f"lint: WARNING: set_output_delay on"
                f" '{port}' — port not in design",
                file=sys.stderr,
            )
    return ""


def cmd_group_path(interp, args):
    """group_path — accept all args gracefully.

    In real OpenSTA, group_path with empty object lists is a
    no-op. Mock mirrors this: no warnings for empty -from/-to
    since [all_registers] etc. legitimately return empty lists.
    """
    return ""


def cmd_set_max_fanout(interp, args):
    return ""


def cmd_set_driving_cell(interp, args):
    return ""


def cmd_set_load(interp, args):
    return ""


def cmd_set_input_transition(interp, args):
    return ""


def cmd_set_false_path(interp, args):
    return ""


def cmd_set_multicycle_path(interp, args):
    return ""


# --- Abstract generation ---

def cmd_write_abstract_lef(interp, args):
    """Generate mock LEF abstract."""
    remaining = list(args)
    while remaining and remaining[0].startswith("-"):
        remaining.pop(0)
    if remaining:
        path = remaining[0]
    else:
        name = _state.design_name or "mock"
        path = os.path.join(_state.results_dir, f"{name}.lef")

    name = _state.design_name or "mock"
    # Estimate size from cell count and utilization
    # Rough estimate: ~0.5 um^2 per cell for ASAP7 standard cells.
    # Calibrate from real synth_stat.txt via mock-train skill.
    cell_area = _state.cell_count * 0.5
    util = max(_state.utilization, 30.0) / 100.0
    total_area = cell_area / util if util > 0 else cell_area
    side = max(total_area ** 0.5, 1.0)
    # Snap to grid (ASAP7: 0.054um placement grid)
    grid = 0.054
    w = round(side / grid) * grid
    h = round(side / grid) * grid

    max_die = _get_max_die()
    if w > max_die or h > max_die:
        _lint(
            "LEF_SIZE",
            f"{w:.1f}x{h:.1f}um exceeds"
            f" {max_die}um — cell_count="
            f"{_state.cell_count},"
            f" util={_state.utilization}%",
        )

    lef_content = f"""VERSION 5.8 ;
BUSBITCHARS "[]" ;
DIVIDERCHAR "/" ;

MACRO {name}
  CLASS BLOCK ;
  ORIGIN 0 0 ;
  FOREIGN {name} 0 0 ;
  SIZE {w:.3f} BY {h:.3f} ;
END {name}

END LIBRARY
"""
    _touch(path, lef_content)
    print(f"lint: write_abstract_lef {path} (SIZE {w:.3f} x {h:.3f})", file=sys.stderr)
    return ""


def cmd_write_timing_model(interp, args):
    """Generate mock Liberty timing model."""
    remaining = list(args)
    while remaining and remaining[0].startswith("-"):
        remaining.pop(0)
    if remaining:
        path = remaining[0]
    else:
        name = _state.design_name or "mock"
        path = os.path.join(_state.results_dir, f"{name}_typ.lib")

    name = _state.design_name or "mock"
    lib_content = f"""library ({name}_typ) {{
  technology (cmos) ;
  delay_model : table_lookup ;
  time_unit : "1ps" ;
  cell ({name}) {{
    area : {_state.cell_count * 0.5:.1f} ;
  }}
}}
"""
    _touch(path, lib_content)
    print(f"lint: write_timing_model {path}", file=sys.stderr)
    return ""


# --- Misc ORFS helpers ---

def cmd_log_cmd(interp, args):
    """log_cmd <command> <args...> — ORFS wrapper that logs and times commands."""
    if args:
        # Execute the wrapped command
        return interp.invoke(args)
    return ""


def cmd_load_design(interp, args):
    """load_design <odb_or_verilog> ?sdc?"""
    if args:
        print(f"lint: load_design {args[0]}", file=sys.stderr)
        if len(args) > 1:
            _state.sdc_loaded = args[1]
            # Find the actual SDC file in RESULTS_DIR
            sdc_path = os.path.join(_state.results_dir, args[1])
            if os.path.isfile(sdc_path):
                _state.sdc_loaded = sdc_path
    return ""


def cmd_erase_non_stage_variables(interp, args):
    return ""


def cmd_report_metrics(interp, args):
    """report_metrics — produce JSON metrics file."""
    return ""


def cmd_find_macros(interp, args):
    """find_macros — return empty list."""
    return ""


def cmd_source_env_var_if_exists(interp, args):
    """source_env_var_if_exists VAR — source file at $VAR if it exists."""
    if args:
        var = args[0]
        path = os.environ.get(var, "")
        if path and os.path.isfile(path):
            interp.eval_file(path)
    return ""


def cmd_env_var_exists_and_non_empty(interp, args):
    """env_var_exists_and_non_empty VAR — return 1 if env var is set and non-empty."""
    if args:
        val = os.environ.get(args[0], "")
        return "1" if val else "0"
    return "0"


def cmd_append_env_var(interp, args):
    """append_env_var listVar envVar ?flag? ?defaultVal?"""
    if len(args) < 2:
        return ""
    list_var = args[0]
    env_var = args[1]
    flag = args[2] if len(args) > 2 else None
    default = args[3] if len(args) > 3 else None
    val = os.environ.get(env_var, "")
    if not val and default:
        val = default
    if val:
        current = interp.variables.get(list_var, "")
        items = interp._parse_list(current)
        if flag:
            items.append(flag)
        items.append(val)
        interp.variables[list_var] = interp._to_list(items)
    return ""


def cmd_source_step_tcl(interp, args):
    """source_step_tcl PRE|POST STAGE — source pre/post hooks."""
    return ""


def cmd_set_thread_count(interp, args):
    return ""


def cmd_place_pins(interp, args):
    return ""


def cmd_place_pin(interp, args):
    return ""


def cmd_macro_placement(interp, args):
    return ""


def cmd_tapcell(interp, args):
    return ""


def cmd_pdngen(interp, args):
    return ""


def cmd_filler_placement(interp, args):
    return ""


def cmd_check_placement(interp, args):
    return ""


def cmd_check_antennas(interp, args):
    return ""


def cmd_density_fill(interp, args):
    return ""


def cmd_write_def(interp, args):
    if args:
        _touch(args[-1], "# mock DEF\n")
    return ""


# --- utl namespace ---

def cmd_utl_set_metrics_stage(interp, args):
    if args:
        _state.current_stage = args[0]
    return ""


def cmd_utl_info(interp, args):
    return ""


def cmd_utl_warn(interp, args):
    return ""


def cmd_utl_error(interp, args):
    return ""


def cmd_utl_report(interp, args):
    return ""


def register_all(interp):
    """Register all lint OpenROAD commands on a TclInterpreter."""
    commands = {
        # Database I/O
        "read_db": cmd_read_db,
        "write_db": cmd_write_db,
        "orfs_write_db": cmd_orfs_write_db,
        # SDC
        "read_sdc": cmd_read_sdc,
        "write_sdc": cmd_write_sdc,
        "orfs_write_sdc": cmd_orfs_write_sdc,
        # LEF/Liberty
        "read_lef": cmd_read_lef,
        "read_liberty": cmd_read_liberty,
        # Verilog
        "read_verilog": cmd_read_verilog,
        "write_verilog": cmd_write_verilog,
        "write_spef": cmd_write_spef,
        # Design
        "link_design": cmd_link_design,
        "initialize_floorplan": cmd_initialize_floorplan,
        "make_tracks": cmd_make_tracks,
        "global_connect": cmd_global_connect,
        "add_global_connection": cmd_add_global_connection,
        "set_global_routing_layer_adjustment": cmd_set_global_routing_layer_adjustment,
        # Placement
        "global_placement": cmd_global_placement,
        "detailed_placement": cmd_detailed_placement,
        "improve_placement": cmd_improve_placement,
        "optimize_mirroring": cmd_optimize_mirroring,
        # CTS
        "clock_tree_synthesis": cmd_clock_tree_synthesis,
        "set_propagated_clock": cmd_set_propagated_clock,
        # Routing
        "global_route": cmd_global_route,
        "detailed_route": cmd_detailed_route,
        "estimate_parasitics": cmd_estimate_parasitics,
        # Repair
        "repair_timing": cmd_repair_timing,
        "repair_design": cmd_repair_design,
        "repair_tie_fanout": cmd_repair_tie_fanout,
        "remove_buffers": cmd_remove_buffers,
        "buffer_ports": cmd_buffer_ports,
        "set_dont_use": cmd_set_dont_use,
        # Reports
        "report_design_area": cmd_report_design_area,
        "report_worst_slack": cmd_report_worst_slack,
        "report_tns": cmd_report_tns,
        "report_wns": cmd_report_wns,
        "report_power": cmd_report_power,
        "report_checks": cmd_report_checks,
        "report_clock_skew": cmd_report_clock_skew,
        "report_floating_nets": cmd_report_floating_nets,
        "report_cell_usage": cmd_report_cell_usage,
        # Database query
        "get_db": cmd_get_db,
        "get_db_block": cmd_get_db_block,
        "get_cells": cmd_get_cells,
        "get_ports": cmd_get_ports,
        "get_nets": cmd_get_nets,
        "get_pins": cmd_get_pins,
        "get_clocks": cmd_get_clocks,
        "all_registers": cmd_all_registers,
        "all_inputs": cmd_all_inputs,
        "all_outputs": cmd_all_outputs,
        # SDC commands
        "create_clock": cmd_create_clock,
        "set_clock_uncertainty": cmd_set_clock_uncertainty,
        "set_input_delay": cmd_set_input_delay,
        "set_output_delay": cmd_set_output_delay,
        "group_path": cmd_group_path,
        "set_max_fanout": cmd_set_max_fanout,
        "set_driving_cell": cmd_set_driving_cell,
        "set_load": cmd_set_load,
        "set_input_transition": cmd_set_input_transition,
        "set_false_path": cmd_set_false_path,
        "set_multicycle_path": cmd_set_multicycle_path,
        # Abstract
        "write_abstract_lef": cmd_write_abstract_lef,
        "write_timing_model": cmd_write_timing_model,
        # ORFS helpers
        "log_cmd": cmd_log_cmd,
        "load_design": cmd_load_design,
        "erase_non_stage_variables": cmd_erase_non_stage_variables,
        "report_metrics": cmd_report_metrics,
        "find_macros": cmd_find_macros,
        "source_env_var_if_exists": cmd_source_env_var_if_exists,
        "env_var_exists_and_non_empty": cmd_env_var_exists_and_non_empty,
        "append_env_var": cmd_append_env_var,
        "source_step_tcl": cmd_source_step_tcl,
        "set_thread_count": cmd_set_thread_count,
        # Physical
        "place_pins": cmd_place_pins,
        "place_pin": cmd_place_pin,
        "macro_placement": cmd_macro_placement,
        "tapcell": cmd_tapcell,
        "pdngen": cmd_pdngen,
        "filler_placement": cmd_filler_placement,
        "check_placement": cmd_check_placement,
        "check_antennas": cmd_check_antennas,
        "density_fill": cmd_density_fill,
        "write_def": cmd_write_def,
        # utl namespace
        "set_metrics_stage": cmd_utl_set_metrics_stage,
    }
    for name, func in commands.items():
        interp.register_command(name, func)

    # Register utl:: namespace commands
    interp.register_command("utl::set_metrics_stage", cmd_utl_set_metrics_stage)
    interp.register_command("utl::info", cmd_utl_info)
    interp.register_command("utl::warn", cmd_utl_warn)
    interp.register_command("utl::error", cmd_utl_error)
    interp.register_command("utl::report", cmd_utl_report)
    interp.register_command("ord::get_db", cmd_get_db)
    interp.register_command("ord::get_db_block", cmd_get_db_block)
