"""Tests for lib_to_verilog.py — Liberty .lib to behavioral Verilog conversion."""

import textwrap

from lib_to_verilog import (
    Cell,
    FfInfo,
    LatchInfo,
    Pin,
    generate_combinational_verilog,
    generate_dff_v,
    generate_empty_v,
    generate_ff_verilog,
    generate_latch_verilog,
    liberty_expr_to_verilog,
    parse_lef_macros,
    parse_lib_cells,
)


class TestLibertyExprToVerilog:
    def test_negation(self):
        assert liberty_expr_to_verilog("!D") == "~D"

    def test_and(self):
        assert liberty_expr_to_verilog("A*B") == "A & B"

    def test_or(self):
        assert liberty_expr_to_verilog("A+B") == "A | B"

    def test_complex(self):
        assert liberty_expr_to_verilog("!A*B+C") == "~A & B | C"

    def test_passthrough(self):
        assert liberty_expr_to_verilog("CLK") == "CLK"

    def test_double_negation(self):
        assert liberty_expr_to_verilog("!!A") == "~~A"

    def test_postfix_negation(self):
        assert liberty_expr_to_verilog("A'") == "~A"

    def test_postfix_negation_paren(self):
        assert liberty_expr_to_verilog("(A+B)'") == "~(A | B)"

    def test_postfix_double_negation(self):
        assert liberty_expr_to_verilog("A''") == "~~A"

    def test_xor_passthrough(self):
        assert liberty_expr_to_verilog("A^B") == "A^B"


class TestParseLibCells:
    def test_simple_dff(self):
        lib = textwrap.dedent("""\
            library (test) {
              cell (DFFx1) {
                pin (Q) {
                  direction : output;
                  function : "IQ";
                }
                pin (D) {
                  direction : input;
                }
                pin (CLK) {
                  direction : input;
                }
                ff (IQ,IQN) {
                  clocked_on : "CLK";
                  next_state : "D";
                }
              }
            }
        """)
        cells = parse_lib_cells(lib)
        assert len(cells) == 1
        c = cells[0]
        assert c.name == "DFFx1"
        assert c.ff is not None
        assert c.ff.clocked_on == "CLK"
        assert c.ff.next_state == "D"
        assert c.ff.var1 == "IQ"
        assert c.ff.var2 == "IQN"
        assert len(c.pins) == 3

    def test_dff_with_inverted_output(self):
        lib = textwrap.dedent("""\
            library (test) {
              cell (DFFHQNx1) {
                pin (QN) {
                  direction : output;
                  function : "IQN";
                }
                pin (D) {
                  direction : input;
                }
                pin (CLK) {
                  direction : input;
                }
                ff (IQN,IQNN) {
                  clocked_on : "CLK";
                  next_state : "!D";
                }
              }
            }
        """)
        cells = parse_lib_cells(lib)
        assert len(cells) == 1
        c = cells[0]
        assert c.ff.var1 == "IQN"
        assert c.ff.next_state == "!D"

    def test_dff_with_async_reset(self):
        lib = textwrap.dedent("""\
            library (test) {
              cell (DFFASRx1) {
                pin (QN) {
                  direction : output;
                  function : "IQN";
                }
                pin (CLK) {
                  direction : input;
                }
                pin (D) {
                  direction : input;
                }
                pin (RESETN) {
                  direction : input;
                }
                pin (SETN) {
                  direction : input;
                }
                ff (IQN,IQNN) {
                  clear : "!SETN";
                  clocked_on : "CLK";
                  next_state : "!D";
                  preset : "!RESETN";
                }
              }
            }
        """)
        cells = parse_lib_cells(lib)
        assert len(cells) == 1
        c = cells[0]
        assert c.ff.clear == "!SETN"
        assert c.ff.preset == "!RESETN"

    def test_latch(self):
        lib = textwrap.dedent("""\
            library (test) {
              cell (DLLx1) {
                pin (Q) {
                  direction : output;
                  function : "IQ";
                }
                pin (D) {
                  direction : input;
                }
                pin (CLK) {
                  direction : input;
                }
                latch (IQ,IQN) {
                  enable : "CLK";
                  data_in : "D";
                }
              }
            }
        """)
        cells = parse_lib_cells(lib)
        assert len(cells) == 1
        c = cells[0]
        assert c.latch is not None
        assert c.latch.enable == "CLK"
        assert c.latch.data_in == "D"

    def test_keeps_combinational_cells(self):
        lib = textwrap.dedent("""\
            library (test) {
              cell (INVx1) {
                pin (Y) {
                  direction : output;
                  function : "!A";
                }
                pin (A) {
                  direction : input;
                }
              }
            }
        """)
        cells = parse_lib_cells(lib)
        assert len(cells) == 1
        c = cells[0]
        assert c.name == "INVx1"
        assert c.ff is None
        assert c.latch is None
        out = next(p for p in c.pins if p.direction == "output")
        assert out.function == "!A"

    def test_skips_pure_physical_cells(self):
        """A cell with no ff/latch and no function on its outputs is dropped."""
        lib = textwrap.dedent("""\
            library (test) {
              cell (TAPCELL) {
                pin (VDD) { direction : input; }
              }
            }
        """)
        cells = parse_lib_cells(lib)
        assert len(cells) == 0

    def test_multiple_cells(self):
        lib = textwrap.dedent("""\
            library (test) {
              cell (DFFx1) {
                pin (Q) { direction : output; function : "IQ"; }
                pin (D) { direction : input; }
                pin (CLK) { direction : input; }
                ff (IQ,IQN) { clocked_on : "CLK"; next_state : "D"; }
              }
              cell (BUFx1) {
                pin (Y) { direction : output; function : "A"; }
                pin (A) { direction : input; }
              }
              cell (DFFx2) {
                pin (Q) { direction : output; function : "IQ"; }
                pin (D) { direction : input; }
                pin (CLK) { direction : input; }
                ff (IQ,IQN) { clocked_on : "CLK"; next_state : "D"; }
              }
            }
        """)
        cells = parse_lib_cells(lib)
        assert len(cells) == 3
        assert cells[0].name == "DFFx1"
        assert cells[1].name == "BUFx1"
        assert cells[2].name == "DFFx2"

    def test_nested_braces_in_timing(self):
        """Verify parser handles deeply nested timing groups without confusion."""
        lib = textwrap.dedent("""\
            library (test) {
              cell (DFFx1) {
                pin (Q) {
                  direction : output;
                  function : "IQ";
                  timing () {
                    cell_rise (delay_7x7) {
                      index_1 ("0.1, 0.2");
                      values ("0.01, 0.02");
                    }
                    cell_fall (delay_7x7) {
                      index_1 ("0.1, 0.2");
                      values ("0.01, 0.02");
                    }
                  }
                }
                pin (D) { direction : input; }
                pin (CLK) { direction : input; }
                ff (IQ,IQN) { clocked_on : "CLK"; next_state : "D"; }
              }
            }
        """)
        cells = parse_lib_cells(lib)
        assert len(cells) == 1
        assert cells[0].ff.clocked_on == "CLK"

    def test_ignores_power_down_function(self):
        """power_down_function should not override function."""
        lib = textwrap.dedent("""\
            library (test) {
              cell (DFFx1) {
                pin (QN) {
                  direction : output;
                  function : "IQN";
                  power_down_function : "(!VDD) + (VSS)";
                }
                pin (D) { direction : input; }
                pin (CLK) { direction : input; }
                ff (IQN,IQNN) { clocked_on : "CLK"; next_state : "!D"; }
              }
            }
        """)
        cells = parse_lib_cells(lib)
        assert len(cells) == 1
        assert cells[0].pins[0].function == "IQN"

    def test_ignores_pg_pins(self):
        """pg_pin (VDD/VSS) should not appear as regular pins."""
        lib = textwrap.dedent("""\
            library (test) {
              cell (DFFx1) {
                pg_pin (VDD) { pg_type : primary_power; }
                pg_pin (VSS) { pg_type : primary_ground; }
                pin (Q) { direction : output; function : "IQ"; }
                pin (D) { direction : input; }
                pin (CLK) { direction : input; }
                ff (IQ,IQN) { clocked_on : "CLK"; next_state : "D"; }
              }
            }
        """)
        cells = parse_lib_cells(lib)
        assert len(cells) == 1
        pin_names = [p.name for p in cells[0].pins]
        assert "VDD" not in pin_names
        assert "VSS" not in pin_names


class TestGenerateFFVerilog:
    def test_simple_dff_qn(self):
        cell = Cell(
            name="DFFHQNx1_ASAP7_75t_R",
            pins=[
                Pin("QN", "output", "IQN"),
                Pin("D", "input"),
                Pin("CLK", "input"),
            ],
            ff=FfInfo(var1="IQN", var2="IQNN", clocked_on="CLK", next_state="!D"),
        )
        v = generate_ff_verilog(cell)
        assert "module DFFHQNx1_ASAP7_75t_R (QN, D, CLK);" in v
        assert "output reg QN;" in v
        assert "input D;" in v
        assert "input CLK;" in v
        assert "always @(posedge CLK)" in v
        assert "QN <= ~D;" in v

    def test_simple_dff_q(self):
        cell = Cell(
            name="DFFHQx4_ASAP7_75t_R",
            pins=[
                Pin("Q", "output", "IQ"),
                Pin("D", "input"),
                Pin("CLK", "input"),
            ],
            ff=FfInfo(var1="IQ", var2="IQN", clocked_on="CLK", next_state="D"),
        )
        v = generate_ff_verilog(cell)
        assert "Q <= D;" in v

    def test_async_reset_set(self):
        cell = Cell(
            name="DFFASRHQNx1_ASAP7_75t_R",
            pins=[
                Pin("QN", "output", "IQN"),
                Pin("CLK", "input"),
                Pin("D", "input"),
                Pin("RESETN", "input"),
                Pin("SETN", "input"),
            ],
            ff=FfInfo(
                var1="IQN", var2="IQNN",
                clocked_on="CLK", next_state="!D",
                clear="!SETN", preset="!RESETN",
            ),
        )
        v = generate_ff_verilog(cell)
        assert "negedge RESETN" in v or "negedge SETN" in v
        assert "if (~RESETN)" in v  # preset
        assert "else if (~SETN)" in v  # clear

    def test_produces_valid_module(self):
        cell = Cell(
            name="TestDFF",
            pins=[
                Pin("Q", "output", "IQ"),
                Pin("D", "input"),
                Pin("CLK", "input"),
            ],
            ff=FfInfo(var1="IQ", var2="IQN", clocked_on="CLK", next_state="D"),
        )
        v = generate_ff_verilog(cell)
        assert v.startswith("module TestDFF")
        assert v.endswith("endmodule")


class TestGenerateLatchVerilog:
    def test_simple_latch(self):
        cell = Cell(
            name="DLLx1_ASAP7_75t_R",
            pins=[
                Pin("Q", "output", "IQ"),
                Pin("D", "input"),
                Pin("CLK", "input"),
            ],
            latch=LatchInfo(var1="IQ", var2="IQN", enable="CLK", data_in="D"),
        )
        v = generate_latch_verilog(cell)
        assert "module DLLx1_ASAP7_75t_R (Q, D, CLK);" in v
        assert "always @(*)" in v
        assert "if (CLK)" in v
        assert "Q <= D;" in v


class TestGenerateCombinationalVerilog:
    def test_inverter(self):
        cell = Cell(
            name="INVx1_ASAP7_75t_R",
            pins=[
                Pin("Y", "output", "!A"),
                Pin("A", "input"),
            ],
        )
        v = generate_combinational_verilog(cell)
        assert "module INVx1_ASAP7_75t_R (Y, A);" in v
        assert "output Y;" in v
        assert "input A;" in v
        assert "assign Y = ~A;" in v
        assert v.endswith("endmodule")

    def test_buffer(self):
        cell = Cell(
            name="BUFx2_ASAP7_75t_R",
            pins=[
                Pin("Y", "output", "A"),
                Pin("A", "input"),
            ],
        )
        v = generate_combinational_verilog(cell)
        assert "assign Y = A;" in v

    def test_aoi(self):
        cell = Cell(
            name="AOI21x1_ASAP7_75t_R",
            pins=[
                Pin("Y", "output", "!((A1*A2)+B)"),
                Pin("A1", "input"),
                Pin("A2", "input"),
                Pin("B", "input"),
            ],
        )
        v = generate_combinational_verilog(cell)
        assert "assign Y = ~((A1 & A2) | B);" in v

    def test_multi_output(self):
        """Some cells (e.g. HAxN) have multiple driven outputs."""
        cell = Cell(
            name="HAx1_ASAP7_75t_R",
            pins=[
                Pin("SO", "output", "A^B"),
                Pin("CO", "output", "A*B"),
                Pin("A", "input"),
                Pin("B", "input"),
            ],
        )
        v = generate_combinational_verilog(cell)
        assert "assign SO = A^B;" in v
        assert "assign CO = A & B;" in v


class TestParseLefMacros:
    def test_basic(self):
        lef = textwrap.dedent("""\
            MACRO TAPCELL_ASAP7_75t_R
              CLASS CORE ENDCAP ;
              SIZE 0.27 BY 0.27 ;
            END TAPCELL_ASAP7_75t_R

            MACRO INVx1_ASAP7_75t_R
              CLASS CORE ;
              SIZE 0.54 BY 0.27 ;
            END INVx1_ASAP7_75t_R
        """)
        macros = parse_lef_macros(lef)
        assert macros == {"TAPCELL_ASAP7_75t_R", "INVx1_ASAP7_75t_R"}

    def test_empty(self):
        assert parse_lef_macros("") == set()


class TestGenerateEmptyV:
    def test_physical_only(self):
        lef_macros = {"TAPCELL_X", "FILLER_X", "INVx1", "DFFx1"}
        lib_cells = {"INVx1", "DFFx1"}
        v = generate_empty_v(lef_macros, lib_cells)
        assert "module FILLER_X;" in v
        assert "endmodule" in v
        assert "module TAPCELL_X;" in v
        assert "INVx1" not in v
        assert "DFFx1" not in v

    def test_no_physical_only(self):
        v = generate_empty_v({"INVx1"}, {"INVx1"})
        assert v == ""

    def test_sorted_output(self):
        v = generate_empty_v({"Z_CELL", "A_CELL"}, set())
        lines = v.strip().split("\n")
        module_lines = [l for l in lines if l.startswith("module ")]
        assert module_lines[0] == "module A_CELL;"
        assert module_lines[1] == "module Z_CELL;"


class TestGenerateDffV:
    def test_header(self):
        v = generate_dff_v([])
        assert "Auto-generated" in v
        assert "Verilator" in v

    def test_includes_ff_and_latch(self):
        cells = [
            Cell(
                name="DFF1",
                pins=[
                    Pin("Q", "output", "IQ"),
                    Pin("D", "input"),
                    Pin("CLK", "input"),
                ],
                ff=FfInfo(var1="IQ", var2="IQN", clocked_on="CLK", next_state="D"),
            ),
            Cell(
                name="LATCH1",
                pins=[
                    Pin("Q", "output", "IQ"),
                    Pin("D", "input"),
                    Pin("G", "input"),
                ],
                latch=LatchInfo(var1="IQ", var2="IQN", enable="G", data_in="D"),
            ),
        ]
        v = generate_dff_v(cells)
        assert "module DFF1" in v
        assert "module LATCH1" in v


class TestRealAsap7Lib:
    """Integration tests using real ASAP7 .lib data snippets."""

    ASAP7_DFFHQN = textwrap.dedent("""\
        library (asap7) {
          cell (DFFHQNx1_ASAP7_75t_R) {
            area : 0.2916;
            pg_pin (VDD) {
              pg_type : primary_power;
              voltage_name : "VDD";
            }
            pg_pin (VSS) {
              pg_type : primary_ground;
              voltage_name : "VSS";
            }
            leakage_power () {
              value : 3106.35;
              when : "(CLK * D * !QN)";
              related_pg_pin : VDD;
            }
            pin (QN) {
              direction : output;
              function : "IQN";
              timing () {
                cell_rise (delay_template_7x7) {
                  index_1 ("0.0 0.1 0.2 0.3 0.4 0.5 0.6");
                  index_2 ("0.0 0.1 0.2 0.3 0.4 0.5 0.6");
                  values ("0.01 0.02 0.03 0.04 0.05 0.06 0.07", \\
                          "0.01 0.02 0.03 0.04 0.05 0.06 0.07");
                }
                cell_fall (delay_template_7x7) {
                  index_1 ("0.0 0.1 0.2 0.3 0.4 0.5 0.6");
                  index_2 ("0.0 0.1 0.2 0.3 0.4 0.5 0.6");
                  values ("0.01 0.02 0.03 0.04 0.05 0.06 0.07", \\
                          "0.01 0.02 0.03 0.04 0.05 0.06 0.07");
                }
              }
            }
            pin (CLK) {
              direction : input;
            }
            pin (D) {
              direction : input;
            }
            ff (IQN,IQNN) {
              clocked_on : "CLK";
              next_state : "!D";
            }
          }
          cell (DFFHQNx2_ASAP7_75t_R) {
            area : 0.3888;
            pg_pin (VDD) { pg_type : primary_power; }
            pg_pin (VSS) { pg_type : primary_ground; }
            pin (QN) {
              direction : output;
              function : "IQN";
            }
            pin (CLK) { direction : input; }
            pin (D) { direction : input; }
            ff (IQN,IQNN) {
              clocked_on : "CLK";
              next_state : "!D";
            }
          }
        }
    """)

    def test_parse_asap7_dff(self):
        cells = parse_lib_cells(self.ASAP7_DFFHQN)
        assert len(cells) == 2
        assert cells[0].name == "DFFHQNx1_ASAP7_75t_R"
        assert cells[1].name == "DFFHQNx2_ASAP7_75t_R"
        for c in cells:
            assert c.ff.clocked_on == "CLK"
            assert c.ff.next_state == "!D"
            pin_names = [p.name for p in c.pins]
            assert "VDD" not in pin_names
            assert "QN" in pin_names

    def test_generated_matches_handwritten(self):
        """Output should be functionally equivalent to the hand-written dff.v."""
        cells = parse_lib_cells(self.ASAP7_DFFHQN)
        for c in cells:
            v = generate_ff_verilog(c)
            assert f"module {c.name} (QN, D, CLK);" in v or f"module {c.name} (QN, CLK, D);" in v
            assert "always @(posedge CLK)" in v
            assert "QN <= ~D;" in v
            assert "endmodule" in v
