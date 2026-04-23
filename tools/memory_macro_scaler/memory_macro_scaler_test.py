"""Unit tests for memory_macro_scaler.

All fixtures are inline strings — no filesystem access, no subprocess.
"""

import io
import re
import tempfile
import textwrap
import unittest
from pathlib import Path

import memory_macro_scaler as mms


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _lib_header(name, time_unit='"1ns"'):
    return textwrap.dedent(
        f"""\
        library({name}) {{
          technology (cmos);
          delay_model : table_lookup;
          time_unit : {time_unit};
          voltage_unit : "1V";
          current_unit : "1uA";
          leakage_power_unit : "1nW";
        """
    )


def _firtool_sram_lib(
    name="tiny_8x8", nR=1, nW=1, nRW=0, rows=8, bits=8, ck_path_value=0.3
):
    """Build a minimal Liberty file with firtool-style pins and a ck-path arc."""
    import math

    addr_bits = int(math.log2(rows))
    types = f"""
      type ({name}_DATA) {{
        base_type : array; data_type : bit;
        bit_width : {bits}; bit_from : {bits-1}; bit_to : 0; downto : true;
      }}
      type ({name}_ADDR) {{
        base_type : array; data_type : bit;
        bit_width : {addr_bits}; bit_from : {addr_bits-1}; bit_to : 0; downto : true;
      }}
    """
    pins = []
    pins.append("    pin(clk) { direction : input; clock : true; capacitance : 2.0; }")
    for i in range(nR):
        pins.append(
            f"    bus(R{i}_addr) {{ bus_type : {name}_ADDR; direction : input; }}"
        )
        pins.append(
            f"    bus(R{i}_data) {{ bus_type : {name}_DATA; direction : output; }}"
        )
        pins.append(f"    pin(R{i}_en)   {{ direction : input; }}")
    for i in range(nW):
        pins.append(
            f"    bus(W{i}_addr) {{ bus_type : {name}_ADDR; direction : input; }}"
        )
        pins.append(
            f"    bus(W{i}_data) {{ bus_type : {name}_DATA; direction : input; }}"
        )
        pins.append(f"    pin(W{i}_en)   {{ direction : input; }}")
        pins.append(
            f"    bus(W{i}_mask) {{ bus_type : {name}_DATA; direction : input; }}"
        )
    for i in range(nRW):
        pins.append(
            f"    bus(RW{i}_addr)  {{ bus_type : {name}_ADDR; direction : input; }}"
        )
        pins.append(
            f"    bus(RW{i}_wdata) {{ bus_type : {name}_DATA; direction : input; }}"
        )
        pins.append(
            f"    bus(RW{i}_rdata) {{ bus_type : {name}_DATA; direction : output; }}"
        )
        pins.append(f"    pin(RW{i}_wmode) {{ direction : input; }}")

    ck_arc = f"""
    pin(clk_tree_sink) {{
      direction : input;
      timing() {{
        timing_type : max_clock_tree_path;
        cell_rise(scalar) {{ values ("{ck_path_value}") }}
        cell_fall(scalar) {{ values ("{ck_path_value}") }}
      }}
      timing() {{
        timing_type : min_clock_tree_path;
        cell_rise(scalar) {{ values ("{ck_path_value}") }}
        cell_fall(scalar) {{ values ("{ck_path_value}") }}
      }}
    }}
    """
    data_arc = """
    pin(R0_sample_delay) {
      direction : output;
      timing() {
        related_pin : "clk";
        timing_type : rising_edge;
        cell_rise(scalar) { values ("0.5") }
        cell_fall(scalar) { values ("0.45") }
        rise_transition(scalar) { values ("0.08") }
        fall_transition(scalar) { values ("0.07") }
      }
      timing() {
        related_pin : "clk";
        timing_type : setup_rising;
        rise_constraint(scalar) { values ("0.12") }
        fall_constraint(scalar) { values ("0.10") }
      }
    }
    """
    return (
        _lib_header(name)
        + types
        + f"  cell({name}) {{\n"
        + "    area : 300.0;\n"
        + "\n".join(pins)
        + "\n"
        + ck_arc
        + data_arc
        + "  }\n"
        "}\n"
    )


def _memory_group_sram_lib(name="bram_64x32", addr_width=6, word_width=32):
    return (
        _lib_header(name) + f"  cell({name}) {{\n"
        "    area : 1200.0;\n"
        "    memory() {\n"
        "      type : ram;\n"
        f"      address_width : {addr_width};\n"
        f"      word_width : {word_width};\n"
        "    }\n"
        "    pin(clk) { direction : input; clock : true; }\n"
        "  }\n"
        "}\n"
    )


def _flop_memory_lib(name="regs_16x8"):
    return (
        _lib_header(name) + f"  cell({name}) {{\n"
        "    area : 800.0;\n"
        "    ff(IQ,IQN) {\n"
        '      clocked_on : "clk";\n'
        '      next_state : "D";\n'
        "    }\n"
        "    pin(clk) { direction : input; clock : true; }\n"
        "    pin(D)   { direction : input; }\n"
        "    pin(Q)   { direction : output; }\n"
        "  }\n"
        "}\n"
    )


def _non_memory_lib(name="INVx1"):
    return (
        _lib_header(name) + f"  cell({name}) {{\n"
        "    area : 0.5;\n"
        "    pin(A) { direction : input; capacitance : 1.0; }\n"
        "    pin(Y) {\n"
        "      direction : output;\n"
        "      timing() {\n"
        '        related_pin : "A";\n'
        "        timing_type : combinational;\n"
        '        cell_rise(scalar) { values ("0.03") }\n'
        '        cell_fall(scalar) { values ("0.025") }\n'
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )


def _tiny_lef(name, pins, width=10.0, height=10.0):
    body = [
        f"MACRO {name}",
        "  CLASS BLOCK ;",
        "  ORIGIN 0 0 ;",
        f"  SIZE {width} BY {height} ;",
    ]
    for p in pins:
        body.append(f"  PIN {p}")
        body.append("    DIRECTION INPUT ;")
        body.append("    PORT")
        body.append("      LAYER M4 ; RECT 0 0 0.1 0.1 ;")
        body.append("    END")
        body.append(f"  END {p}")
    body.append(f"END {name}")
    return "\n".join(body) + "\n"


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class TestClassify(unittest.TestCase):
    def test_memory_group_is_sram(self):
        role = mms.classify(_memory_group_sram_lib(addr_width=7, word_width=32))
        self.assertEqual(role.kind, "sram")
        self.assertEqual(role.rows, 128)
        self.assertEqual(role.bits, 32)

    def test_memory_group_without_firtool_pins_defaults_to_1RW(self):
        role = mms.classify(_memory_group_sram_lib())
        self.assertEqual(role.nRW, 1)
        self.assertEqual(role.nR, 0)
        self.assertEqual(role.nW, 0)
        self.assertEqual(role.ports_key, "1RW")

    def test_firtool_1r1w_sram(self):
        role = mms.classify(_firtool_sram_lib(nR=1, nW=1, rows=8, bits=8))
        self.assertEqual(role.kind, "sram")
        self.assertEqual(role.nR, 1)
        self.assertEqual(role.nW, 1)
        self.assertEqual(role.nRW, 0)
        self.assertEqual(role.rows, 8)
        self.assertEqual(role.bits, 8)
        self.assertEqual(role.ports_key, "1R1W")

    def test_firtool_1rw_sram(self):
        role = mms.classify(_firtool_sram_lib(nR=0, nW=0, nRW=1))
        self.assertEqual(role.kind, "sram")
        self.assertEqual(role.ports_key, "1RW")

    def test_firtool_2r1w_sram(self):
        role = mms.classify(_firtool_sram_lib(nR=2, nW=1, rows=64, bits=32))
        self.assertEqual(role.nR, 2)
        self.assertEqual(role.nW, 1)
        self.assertEqual(role.ports_key, "2R1W")
        self.assertEqual(role.rows, 64)
        self.assertEqual(role.bits, 32)

    def test_flop_memory_by_name_and_ff_group(self):
        role = mms.classify(_flop_memory_lib("regs_16x8"))
        self.assertEqual(role.kind, "flop_memory")
        self.assertEqual(role.rows, 16)
        self.assertEqual(role.bits, 8)

    def test_non_memory(self):
        role = mms.classify(_non_memory_lib())
        self.assertEqual(role.kind, "non_memory")
        self.assertEqual(role.ports_key, None)


# ---------------------------------------------------------------------------
# Idiomatic ASAP7 table
# ---------------------------------------------------------------------------


class TestIdiomaticTable(unittest.TestCase):
    def test_any_predicted_sram_has_aspect_in_1_to_4(self):
        """Every predicted outline over a reasonable shape sweep stays inside 1:1..1:4."""
        shapes = [
            (64, 32),
            (128, 32),
            (128, 64),
            (256, 32),
            (256, 64),
            (1024, 32),
            (512, 128),
        ]
        for rows, bits in shapes:
            for ports in ("1RW", "1R1W", "2R1W"):
                role = mms.MemoryRole(kind="sram", rows=rows, bits=bits, nRW=1)
                role.nR = 2 if ports == "2R1W" else (1 if ports == "1R1W" else 0)
                role.nW = 1 if ports in ("1R1W", "2R1W") else 0
                role.nRW = 0 if ports in ("1R1W", "2R1W") else 1
                bucket, _ = mms.lookup_idiomatic(role)
                w = bucket["width_um"]
                h = bucket["height_um"]
                aspect = max(w, h) / min(w, h)
                self.assertTrue(
                    1.0 <= aspect <= 4.0,
                    f"shape {(rows, bits, ports)} outline {w:.1f}x{h:.1f} "
                    f"aspect {aspect:.2f} is outside 1:1..1:4",
                )

    def test_fit_reproduces_openram_freepdk45_anchor(self):
        """The FreePDK45 128x32 1RW anchor (6967.66 um²) is in the training set —
        the fit should predict close to it when asked for the same shape + PDK."""
        area = mms.predict_area_um2(
            rows=128, bits=32, ports_key="1RW", kind="sram", tech_nm=45
        )
        # Allow 30% — the fit is coarse (pools FreePDK45 + sky130 points)
        # and pays for cross-PDK generalization with in-sample residuals.
        self.assertAlmostEqual(area / 6967.66, 1.0, delta=0.30)

    def test_fit_reproduces_openram_freepdk45_access_time(self):
        """FreePDK45 128x32 1RW → 322 ps is the calibration point — exact match."""
        d = mms.predict_access_time_ps(
            rows=128, bits=32, ports_key="1RW", kind="sram", tech_nm=45
        )
        self.assertAlmostEqual(d, 322.0, delta=1.0)

    def test_asap7_sram_area_is_much_smaller_than_sky130(self):
        """Scaling from 130 nm sky130 to 7 nm ASAP7 squeezes area by (7/130)^2 ~ 0.003x."""
        sram_sky130 = mms.predict_area_um2(
            rows=256, bits=32, ports_key="1RW", kind="sram", tech_nm=130
        )
        sram_asap7 = mms.predict_area_um2(
            rows=256, bits=32, ports_key="1RW", kind="sram", tech_nm=7
        )
        ratio = sram_asap7 / sram_sky130
        self.assertTrue(
            0.001 < ratio < 0.01,
            f"7nm/130nm area ratio {ratio:.4f} outside expected range",
        )

    def test_port_factor_monotonic(self):
        """More ports -> more area, same rows/bits/tech."""
        a1 = mms.predict_area_um2(
            rows=128, bits=32, ports_key="1RW", kind="sram", tech_nm=7
        )
        a2 = mms.predict_area_um2(
            rows=128, bits=32, ports_key="1R1W", kind="sram", tech_nm=7
        )
        a3 = mms.predict_area_um2(
            rows=128, bits=32, ports_key="2R1W", kind="sram", tech_nm=7
        )
        self.assertLess(a1, a2)
        self.assertLess(a2, a3)

    def test_flop_memory_access_time_is_zero(self):
        role = mms.MemoryRole(kind="flop_memory", rows=16, bits=8)
        bucket, _ = mms.lookup_idiomatic(role)
        self.assertEqual(bucket["access_time_ps"], 0.0)
        # And no outline — flops don't have a physical macro shell.
        self.assertNotIn("width_um", bucket)

    def test_non_memory_has_no_bucket(self):
        role = mms.MemoryRole(kind="non_memory")
        bucket, _ = mms.lookup_idiomatic(role)
        self.assertIsNone(bucket)

    def test_training_residuals_inside_dse_budget(self):
        """The fit must stay within the ±25% / ±5% budget documented in the README.

        The budget is the DSE-usefulness threshold: a lower number would
        mean we're underfit (a more-complex model could help); a higher
        number would mean DSE rankings near that size are unreliable.
        Regressions outside this band must either adjust the budget
        in the README or investigate (new data? model change?).
        """
        ff_budget = 0.05  # ±5% per README
        sram_budget = 0.25  # ±25% per README
        for tech, rows, bits, ports, kind, area, _ in mms.MEMORY_DATA_POINTS:
            pred = mms.predict_area_um2(
                rows=rows, bits=bits, ports_key=ports, kind=kind, tech_nm=tech
            )
            rel_err = abs(pred - area) / area
            budget = ff_budget if kind == "ff" else sram_budget
            self.assertLess(
                rel_err,
                budget,
                f"{kind} {tech}nm {rows}x{bits} {ports}: residual "
                f"{rel_err*100:.1f}% exceeds DSE budget {budget*100:.0f}%",
            )


# ---------------------------------------------------------------------------
# .lib scaling
# ---------------------------------------------------------------------------


def _extract_values(text):
    return [
        float(m.group(1)) for m in re.finditer(r'values\s*\(\s*"(-?[\d.]+)"\s*\)', text)
    ]


def _extract_ck_values(text):
    """Pull values from timing() groups whose timing_type is min/max_clock_tree_path.

    Walks with brace depth — the narrow regex approach can't span nested
    cell_rise() / cell_fall() groups.
    """
    vals = []
    lines = text.splitlines()
    depth = 0
    in_timing = False
    timing_depth = 0
    is_ck_timing = False
    for line in lines:
        opens = line.count("{")
        closes = line.count("}")
        if re.search(r"\btiming\s*\(\s*\)\s*\{", line):
            in_timing = True
            timing_depth = depth + opens
            is_ck_timing = False
        if in_timing:
            m = re.search(r"\btiming_type\s*:\s*(\w+)", line)
            if m and m.group(1) in ("min_clock_tree_path", "max_clock_tree_path"):
                is_ck_timing = True
            if is_ck_timing:
                for v in re.finditer(r'values\s*\(\s*"(-?[\d.]+)"\s*\)', line):
                    vals.append(float(v.group(1)))
        depth += opens - closes
        if in_timing and depth < timing_depth:
            in_timing = False
            is_ck_timing = False
    return vals


class TestScaleLibText(unittest.TestCase):
    def test_ck_insertion_override_writes_absolute_value(self):
        text = _firtool_sram_lib(ck_path_value=0.3)
        # bucket 128x64 post-CTS has 220 ps = 0.22 ns at 1ns time_unit
        scaled = mms.scale_lib_text(text, timing_scale=1.0, ck_insertion_ps=220.0)
        ck_vals = _extract_ck_values(scaled)
        self.assertTrue(ck_vals)
        for v in ck_vals:
            self.assertAlmostEqual(v, 0.22, places=5)

    def test_pre_layout_ck_collapsed_to_zero(self):
        text = _firtool_sram_lib(ck_path_value=0.3)
        scaled = mms.scale_lib_text(text, timing_scale=1.0, ck_insertion_ps=0.0)
        for v in _extract_ck_values(scaled):
            self.assertEqual(v, 0.0)

    def test_rise_fall_ratio_preserved(self):
        text = _firtool_sram_lib()
        # Pre-scale the ck-tree arcs to 0 so we can look past them to the data arc.
        scaled = mms.scale_lib_text(text, timing_scale=0.5, ck_insertion_ps=0.0)
        # Data arc in fixture: cell_rise=0.5, cell_fall=0.45 (after scale stays 10:9).
        rises = [
            float(m.group(1))
            for m in re.finditer(
                r'cell_rise\(scalar\)\s*\{\s*values\s*\(\s*"([\d.]+)"', scaled
            )
        ]
        falls = [
            float(m.group(1))
            for m in re.finditer(
                r'cell_fall\(scalar\)\s*\{\s*values\s*\(\s*"([\d.]+)"', scaled
            )
        ]
        # Find a non-zero (= data arc) rise/fall pair.
        data_rise = next(v for v in rises if v > 0)
        data_fall = next(v for v in falls if v > 0)
        self.assertAlmostEqual(data_rise / data_fall, 0.5 / 0.45, places=5)

    def test_no_change_to_area_line(self):
        text = _firtool_sram_lib()
        scaled = mms.scale_lib_text(text, timing_scale=0.1)
        # area : 300.0 should survive.
        self.assertIn("area : 300.0", scaled)

    def test_ck_target_untouched_if_none(self):
        text = _firtool_sram_lib(ck_path_value=0.3)
        scaled = mms.scale_lib_text(text, timing_scale=1.0, ck_insertion_ps=None)
        for v in _extract_ck_values(scaled):
            self.assertAlmostEqual(v, 0.3, places=6)


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


class TestScaleReference(unittest.TestCase):
    def test_library_name_mismatch_raises(self):
        post = _firtool_sram_lib("tiny_128x64", nRW=1, rows=128, bits=64)
        pre = _firtool_sram_lib("OTHER_128x64", nRW=1, rows=128, bits=64)
        lef = _tiny_lef("tiny_128x64", ["clk", "RW0_addr", "RW0_rdata"])
        with self.assertRaises(ValueError):
            mms.scale_reference(
                lib_post_cts_text=post,
                lib_pre_layout_text=pre,
                lef_text=lef,
            )

    def test_sram_dual_scale_produces_different_ck_values(self):
        post = _firtool_sram_lib(
            "tiny_128x64", nRW=1, rows=128, bits=64, ck_path_value=0.5
        )
        pre = _firtool_sram_lib(
            "tiny_128x64", nRW=1, rows=128, bits=64, ck_path_value=0.5
        )
        lef = _tiny_lef(
            "tiny_128x64", ["clk", "RW0_addr", "RW0_rdata", "RW0_wdata", "RW0_wmode"]
        )
        sp, spre, sle, role, bucket, _ = mms.scale_reference(
            lib_post_cts_text=post,
            lib_pre_layout_text=pre,
            lef_text=lef,
        )
        self.assertEqual(role.kind, "sram")
        self.assertIsNotNone(bucket)
        post_ck = _extract_ck_values(sp)
        pre_ck = _extract_ck_values(spre)
        for v in pre_ck:
            self.assertEqual(v, 0.0)
        for v in post_ck:
            self.assertGreater(v, 0.0)

    def test_non_memory_lef_round_trips(self):
        post = _non_memory_lib()
        lef = _tiny_lef("INVx1", ["A", "Y"])
        sp, spre, sle, role, bucket, _ = mms.scale_reference(
            lib_post_cts_text=post,
            lib_pre_layout_text=None,
            lef_text=lef,
        )
        self.assertEqual(role.kind, "non_memory")
        self.assertIsNone(bucket)
        self.assertEqual(sle, lef)

    def test_single_input_emits_both_outputs(self):
        """Place-stage macros supply only one .lib; tool synthesizes both views."""
        post = _firtool_sram_lib(
            "tiny_128x64", nRW=1, rows=128, bits=64, ck_path_value=0.5
        )
        lef = _tiny_lef(
            "tiny_128x64", ["clk", "RW0_addr", "RW0_rdata", "RW0_wdata", "RW0_wmode"]
        )
        sp, spre, sle, role, bucket, _ = mms.scale_reference(
            lib_post_cts_text=post,
            lib_pre_layout_text=None,
            lef_text=lef,
            emit_pre_layout=True,
        )
        self.assertIsNotNone(
            spre,
            "single-input mode with emit_pre_layout=True must produce pre_layout output",
        )
        post_ck = _extract_ck_values(sp)
        pre_ck = _extract_ck_values(spre)
        # Pre-layout ck arcs are clamped to 0.
        for v in pre_ck:
            self.assertEqual(v, 0.0)
        # Post-CTS ck arcs take the idiomatic value (>0).
        for v in post_ck:
            self.assertGreater(v, 0.0)
        # Both outputs should have the same cell area (shape preserved).
        self.assertIn("area : 300.0", sp)
        self.assertIn("area : 300.0", spre)

    def test_single_input_without_emit_pre_layout_gives_none(self):
        post = _firtool_sram_lib()
        lef = _tiny_lef("tiny_8x8", ["clk"])
        _, spre, _, _, _, _ = mms.scale_reference(
            lib_post_cts_text=post,
            lib_pre_layout_text=None,
            lef_text=lef,
            emit_pre_layout=False,
        )
        self.assertIsNone(spre)

    def test_sram_lef_rewrite_places_pins_on_edges(self):
        post = _firtool_sram_lib("tiny_128x64", nRW=1, rows=128, bits=64)
        lef = _tiny_lef(
            "tiny_128x64", ["clk", "RW0_addr", "RW0_rdata", "RW0_wdata", "RW0_wmode"]
        )
        _, _, scaled_lef, role, bucket, _ = mms.scale_reference(
            lib_post_cts_text=post,
            lib_pre_layout_text=None,
            lef_text=lef,
        )
        # Grab every PIN block's first RECT; check x-coordinates.
        pin_rects = re.findall(
            r"PIN\s+(\S+).*?RECT\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
            scaled_lef,
            re.DOTALL,
        )
        by_pin = {
            p: (float(x0), float(y0), float(x1), float(y1))
            for p, x0, y0, x1, y1 in pin_rects
        }
        # Output pin lands on the right edge (x0 near width_um).
        self.assertAlmostEqual(
            by_pin["RW0_rdata"][0], bucket["width_um"] - mms._M4_PITCH_UM, places=3
        )
        # Input pin lands on the left edge (x0 == 0).
        self.assertEqual(by_pin["RW0_addr"][0], 0.0)
        # Clock lands on the top edge (y0 near height_um).
        self.assertAlmostEqual(
            by_pin["clk"][1], bucket["height_um"] - mms._M5_PITCH_UM, places=3
        )


# ---------------------------------------------------------------------------
# CLI shim
# ---------------------------------------------------------------------------


class TestGenerateFromScratch(unittest.TestCase):
    def test_generate_lib_has_memory_group(self):
        role = mms.MemoryRole(
            kind="sram",
            rows=128,
            bits=64,
            nR=1,
            nW=1,
            library_name="mem",
            cell_name="mem",
        )
        lib = mms.generate_lib(role, tech_nm=7)
        self.assertIn("memory()", lib)
        self.assertIn("type : ram", lib)
        self.assertIn("address_width : 7", lib)  # log2(128)=7
        self.assertIn("word_width : 64", lib)

    def test_generate_lib_has_power_arcs(self):
        role = mms.MemoryRole(
            kind="sram", rows=128, bits=64, nRW=1, library_name="mem", cell_name="mem"
        )
        lib = mms.generate_lib(role, tech_nm=7)
        self.assertIn("internal_power()", lib)
        self.assertIn("default_cell_leakage_power", lib)
        # At least one rise_power with a nonzero value.
        rp = re.findall(r'rise_power\([a-z_]+\)\s*\{\s*values\s*\(\s*"([\d.]+)', lib)
        self.assertTrue(
            any(float(v) > 0 for v in rp),
            "expected nonzero rise_power for at least one arc",
        )

    def test_generate_lib_has_setup_hold(self):
        role = mms.MemoryRole(
            kind="sram",
            rows=128,
            bits=64,
            nR=1,
            nW=1,
            library_name="mem",
            cell_name="mem",
        )
        lib = mms.generate_lib(role, tech_nm=7)
        self.assertIn("setup_rising", lib)
        self.assertIn("hold_rising", lib)

    def test_generate_lef_outline_and_pins(self):
        role = mms.MemoryRole(
            kind="sram", rows=128, bits=64, nRW=1, library_name="mem", cell_name="mem"
        )
        lef = mms.generate_lef(role, tech_nm=7)
        self.assertIn("MACRO mem", lef)
        self.assertIn("SIZE ", lef)
        self.assertIn("PIN RW0_addr", lef)
        self.assertIn("PIN RW0_rdata", lef)
        self.assertIn("PIN RW0_clk", lef)


class TestBanking(unittest.TestCase):
    def test_small_memory_is_single_bank(self):
        role = mms.MemoryRole(kind="sram", rows=64, bits=32, nRW=1)
        plan = mms.bank_plan(role)
        self.assertEqual(plan.num_banks, 1)
        self.assertEqual(plan.word_slices, 1)
        self.assertEqual(plan.row_banks, 1)

    def test_oversized_width_gets_word_sliced(self):
        # 1024-bit-wide memory should slice into MAX_BITS_PER_BANK chunks.
        role = mms.MemoryRole(kind="sram", rows=64, bits=1024, nRW=1)
        plan = mms.bank_plan(role)
        self.assertGreater(plan.word_slices, 1)
        self.assertLessEqual(plan.bits_per_bank, mms.MAX_BITS_PER_BANK)

    def test_oversized_depth_gets_row_banked(self):
        # 2048-row memory should row-bank into chunks of MAX_ROWS_PER_BANK.
        role = mms.MemoryRole(kind="sram", rows=2048, bits=32, nRW=1)
        plan = mms.bank_plan(role)
        self.assertGreater(plan.row_banks, 1)
        self.assertLessEqual(plan.rows_per_bank, mms.MAX_ROWS_PER_BANK)

    def test_many_read_ports_replicate(self):
        role = mms.MemoryRole(kind="sram", rows=64, bits=32, nR=5, nW=1)
        plan = mms.bank_plan(role)
        self.assertGreater(plan.read_copies, 1)
        self.assertLessEqual(plan.nR_per_bank, mms.MAX_READ_PORTS_PER_BANK)

    def test_oversized_memory_area_scales_with_bank_count(self):
        """Total area should grow roughly proportionally to the bank count."""
        small = mms.MemoryRole(kind="sram", rows=64, bits=32, nRW=1)
        big = mms.MemoryRole(kind="sram", rows=64, bits=1024, nRW=1)
        small_area, _ = mms.predict_idiomatic(small, tech_nm=7)
        big_area, _ = mms.predict_idiomatic(big, tech_nm=7)
        # 1024 / 32 = 32x more bits → area should be 20–50x larger (banking
        # adds periphery per bank but the fit exponent is close to 1).
        ratio = big_area["area_um2"] / (
            small_area["width_um"] * small_area["height_um"]
        )
        self.assertGreater(ratio, 15)
        self.assertLess(ratio, 80)

    def test_banked_access_time_picks_up_mux_penalty(self):
        """Row-banking adds log2(N) FO4 of select delay on the read path."""
        small = mms.MemoryRole(kind="sram", rows=64, bits=32, nRW=1)
        banked = mms.MemoryRole(kind="sram", rows=4096, bits=32, nRW=1)
        small_b, _ = mms.predict_idiomatic(small, tech_nm=7)
        banked_b, _ = mms.predict_idiomatic(banked, tech_nm=7)
        self.assertGreater(banked_b["access_time_ps"], small_b["access_time_ps"])

    def test_bucket_exposes_bank_plan(self):
        role = mms.MemoryRole(kind="sram", rows=2048, bits=256, nR=2, nW=1)
        bucket, _ = mms.predict_idiomatic(role, tech_nm=7)
        self.assertIn("bank_plan", bucket)
        self.assertGreater(bucket["bank_plan"].num_banks, 1)


class TestVerilogScanner(unittest.TestCase):
    def test_scan_detects_firtool_sram(self):
        sv = textwrap.dedent(
            """\
            module data_128x64(
              input         clk,
              input  [6:0]  R0_addr,
              input         R0_en,
              output [63:0] R0_data,
              input  [6:0]  W0_addr,
              input         W0_en,
              input  [63:0] W0_data,
              input  [63:0] W0_mask
            );
            endmodule
            module unrelated(
              input a,
              output y
            );
            endmodule
        """
        )
        roles = mms.scan_verilog_for_memories(sv)
        self.assertIn("data_128x64", roles)
        r = roles["data_128x64"]
        self.assertEqual(r.kind, "sram")
        self.assertEqual(r.rows, 128)
        self.assertEqual(r.bits, 64)
        self.assertEqual(r.nR, 1)
        self.assertEqual(r.nW, 1)
        self.assertNotIn("unrelated", roles)

    def test_scan_detects_flop_memory_by_name(self):
        sv = textwrap.dedent(
            """\
            module regfile_16x32(
              input clk,
              input [3:0] addr,
              output [31:0] q,
              input we,
              input [31:0] d
            );
              reg [31:0] mem [15:0];
              always @(posedge clk) if (we) mem[addr] <= d;
              assign q = mem[addr];
            endmodule
        """
        )
        roles = mms.scan_verilog_for_memories(sv)
        self.assertIn("regfile_16x32", roles)
        r = roles["regfile_16x32"]
        self.assertEqual(r.kind, "flop_memory")
        self.assertEqual(r.rows, 16)
        self.assertEqual(r.bits, 32)


class TestCli(unittest.TestCase):
    def test_dry_run_on_non_memory(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            lib = d / "in.lib"
            lef = d / "in.lef"
            lib.write_text(_non_memory_lib())
            lef.write_text(_tiny_lef("INVx1", ["A", "Y"]))
            out_lib = d / "out.lib"
            out_lef = d / "out.lef"
            rc = mms.main(
                [
                    "--in-lib-post-cts",
                    str(lib),
                    "--in-lef",
                    str(lef),
                    "--out-lib-post-cts",
                    str(out_lib),
                    "--out-lef",
                    str(out_lef),
                    "--dry-run",
                ]
            )
            self.assertEqual(rc, 0)
            self.assertFalse(out_lib.exists())
            self.assertFalse(out_lef.exists())

    def test_single_input_cli_writes_both_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            post = d / "post.lib"
            post.write_text(_firtool_sram_lib("tiny_128x64", nRW=1, rows=128, bits=64))
            lef = d / "in.lef"
            lef.write_text(_tiny_lef("tiny_128x64", ["clk", "RW0_addr", "RW0_rdata"]))
            out_post = d / "out_post.lib"
            out_pre = d / "out_pre.lib"
            out_lef = d / "out.lef"
            rc = mms.main(
                [
                    "--in-lib-post-cts",
                    str(post),
                    "--in-lef",
                    str(lef),
                    "--out-lib-post-cts",
                    str(out_post),
                    "--out-lib-pre-layout",
                    str(out_pre),
                    "--out-lef",
                    str(out_lef),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(out_post.read_text())
            self.assertTrue(out_pre.read_text())
            self.assertNotEqual(out_post.read_text(), out_pre.read_text())

    def test_dual_input_writes_both(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            post = d / "post.lib"
            post.write_text(_firtool_sram_lib("tiny_128x64", nRW=1, rows=128, bits=64))
            pre = d / "pre.lib"
            pre.write_text(_firtool_sram_lib("tiny_128x64", nRW=1, rows=128, bits=64))
            lef = d / "in.lef"
            lef.write_text(_tiny_lef("tiny_128x64", ["clk", "RW0_addr", "RW0_rdata"]))
            out_post = d / "out_post.lib"
            out_pre = d / "out_pre.lib"
            out_lef = d / "out.lef"
            rc = mms.main(
                [
                    "--in-lib-post-cts",
                    str(post),
                    "--in-lib-pre-layout",
                    str(pre),
                    "--in-lef",
                    str(lef),
                    "--out-lib-post-cts",
                    str(out_post),
                    "--out-lib-pre-layout",
                    str(out_pre),
                    "--out-lef",
                    str(out_lef),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(out_post.read_text())
            self.assertTrue(out_pre.read_text())
            self.assertTrue(out_lef.read_text())
            # Sanity: two .libs differ (post-CTS has nonzero ck arc, pre has 0).
            self.assertNotEqual(out_post.read_text(), out_pre.read_text())


if __name__ == "__main__":
    unittest.main()
