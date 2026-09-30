// structured_gen: buffer trees for a generated block's wide nets, built
// and placed by construction.
//
// The array's address literals, word selects, write data and enables
// each fan out to hundreds of pins: on FtqMetaQueueResolve (64 x 954,
// eight bit folds) one address inverter drives 256 pins and 194 fF, and
// the read path is 3,625 ps on its own gates. fanout_tree rebuilds every
// such net as a balanced tree of buffers; each new buffer is then put
// on the free sites nearest the pins it drives, service columns first
// by construction of the layout, so the block stays legal and FIRM.
#pragma once

#include <string>
#include <vector>

namespace odb {
class dbBlock;
}

namespace structured_gen {

struct BufferSpec {
  std::vector<std::string> cells;  // buffer masters, any order
  int max_fanout = 16;
  double max_load_ff = 24.0;
  double input_load_ff = 0.6;      // a std cell input, for sizing
  double root_ff_per_drive = 2.5;  // an x1 driver keeps 2.5 fF
  // Two-pin nets longer than this get repeaters of about repeater_drive;
  // 0 turns repeaters off.
  double max_wire_um = 0;
  double repeater_drive = 8;
  bool enabled() const { return !cells.empty(); }
};

struct BufferResult {
  int nets = 0;
  int buffers = 0;
  int repeaters = 0;
  double max_displacement_um = 0;  // buffer to the centroid of its pins
};

// Rebuilds and places. Throws std::runtime_error when a buffer finds no
// free site within its search window: the layout needs more service
// sites, and the spec says how many.
BufferResult BufferWideNets(odb::dbBlock* block, const BufferSpec& spec);

}  // namespace structured_gen
