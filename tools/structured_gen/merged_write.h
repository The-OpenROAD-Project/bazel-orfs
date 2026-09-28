// structured_gen: a merged write as a placed standard-cell block, from a
// JSON domain specification.
//
// The shape is a write and a flush merged per way into registers held
// for a cycle, as XiangShan's main BTB enqueues its entry write buffer
// (MainBtbWriteBufferEnq): per way `valid = write & way | flush & way &
// !conflict`, a valid register, and per field a register that loads the
// write's value, or the flush's (zero when the flush has none), when
// valid. `conflict` is the write's set index equal to the flush's and the
// write's tag zero. The generator lays each way out as a column of bit
// tiles with its enables beside them, the conflict compare in a column
// between the ways, every cell placed by construction.
#pragma once

#include <string>
#include <vector>

namespace odb {
class dbDatabase;
class dbBlock;
}  // namespace odb

namespace utl {
class Logger;
}

namespace structured_gen {

// A cell by name in the loaded LEF, with its pins in the order the
// builder uses them (inputs, then the output).
struct CellRef {
  std::string master;
  std::vector<std::string> pins;
};

// One registered field of a way: its port and register names come from
// the templates in MergedWriteSpec with {w} the way and {field} this name.
struct MergedField {
  std::string name;        // e.g. "setIdx", "entry_tag"
  std::string reg;         // register name suffix, e.g. "setIdx_r"
  int width = 1;
  std::string write;       // input bus the write carries
  std::string flush;       // input bus the flush carries; empty means zero
};

struct MergedWriteSpec {
  std::string module;
  std::string clock = "clock";
  std::string reset = "reset";  // active high, asynchronous, valid only
  int ways = 1;
  std::string write_valid;
  std::string write_way_mask;
  std::string flush_valid;
  std::string flush_way_mask;
  std::string conflict_equal_a;  // write's set index
  std::string conflict_equal_b;  // flush's set index
  std::string conflict_zero;     // write's tag
  std::vector<MergedField> fields;
  // Names, with {w} and {field} substituted.
  std::string out_valid = "io_write_{w}_valid";
  std::string out_field = "io_write_{w}_bits_{field}";
  std::string reg_valid = "io_write_{w}_valid_REG";
  std::string reg_field = "io_write_{w}_bits_{reg}";
  // Cells: flop (D CLK QN), rflop (D CLK QN RESETN SETN), inv, buf,
  // and2, and3, nand3, and4, nor4, or2, xnor2, ao22, ao222, tiehi.
  std::vector<std::pair<std::string, CellRef>> cells;
  // Most loads one enable buffer drives before another is added.
  int max_fanout = 14;
  // Empty band between the cells and the outline, on every side. A
  // dissolved block's outline may abut another macro, and that macro's
  // power-grid halo (asap7: 2 um) must fall on no row holding a cell.
  double margin_um = 2.0;
  std::string pin_layer_h = "M4";
  std::string pin_layer_v = "M5";
  double pin_track_offset_um = 0.012;
  double pin_track_pitch_um = 0.048;
};

// Reads the JSON specification; throws std::runtime_error naming what is
// missing or not understood.
MergedWriteSpec ReadMergedWriteSpec(const std::string& path);

// Builds the netlist and placement into a new block of `db`.
odb::dbBlock* GenerateMergedWrite(odb::dbDatabase* db, utl::Logger* logger,
                                  const MergedWriteSpec& spec);

// A model liberty for the block as a macro: every output is a register,
// so an output arc is clock to Q and an input a setup check.
void WriteMergedWriteLiberty(odb::dbBlock* block, const MergedWriteSpec& spec,
                             const std::string& path);

}  // namespace structured_gen
