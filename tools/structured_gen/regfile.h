// structured_gen: a multi-port register file as a placed standard-cell
// macro, built directly in odb.
//
// A register file synthesised to flops is a flop per bit, a W-way write
// mux on each flop's D and an R-way read mux tree per bit: dense, and the
// legaliser cannot spread it. Here it is laid out the way a bitcell array
// is: word rows by bit columns, one tile per (word, bit) holding the flop,
// its write select and R read AND gates; the read wordlines run along the
// rows and are decoded in a header column, the read bitlines are OR trees
// in a footer row. Every cell is placed by construction; nothing is left
// to a placer.
#pragma once

#include <string>
#include <vector>

namespace odb {
class dbDatabase;
class dbBlock;
class dbMaster;
class dbNet;
class dbInst;
}  // namespace odb

namespace utl {
class Logger;
}

namespace structured_gen {

// One read or write port, with the RTL's own pin names so the macro drops
// in for the module it replaces.
struct Port {
  std::string addr;  // bus name; bits are <addr>[i]
  std::string data;  // bus name; bits are <data>[i]
  std::string en;    // write ports only; empty means always enabled
};

// The cells the array is built from, by name in the loaded LEF.
struct Cells {
  std::string flop;      // D flip-flop, Q output (QN accepted, see below)
  std::string and2;      // read select AND
  std::string or2;       // bitline OR tree node
  std::string ao22;      // write mux node: (sel & new) | (hold & old)
  std::string inv;       // decoder inverters
  std::string tap;       // well tap, one column per tap_columns
  std::string tie_lo;    // for unused inputs
};

struct Spec {
  std::string module;    // generated module and block name
  int words = 0;
  int bits = 0;
  std::string clock = "clock";
  std::vector<Port> read;
  std::vector<Port> write;
  Cells cells;
  int tap_columns = 8;    // a tap column every N bit columns
  int service_sites = 40; // free sites beside each tap, for the clock tree
  int banks = 1;          // word columns side by side; words % banks == 0
};

// Reads a spec from a small `key value` text file (see README.md).
// Throws std::runtime_error with the offending line on anything it does
// not understand: a spec is either complete or refused.
Spec ReadSpec(const std::string& path);

// Builds the netlist and placement of `spec` into a new block of `db`,
// whose tech and libs must already hold the cells named in the spec.
// Returns the block. Throws std::runtime_error naming the cell or pin
// when the library does not fit the spec.
odb::dbBlock* Generate(odb::dbDatabase* db, utl::Logger* logger,
                       const Spec& spec);

// Writes the block as a structural Verilog module, cells as instances,
// for simulation and for the flow's netlist view.
void WriteVerilog(odb::dbBlock* block, const std::string& path);

}  // namespace structured_gen
