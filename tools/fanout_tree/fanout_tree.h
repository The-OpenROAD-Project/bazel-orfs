// fanout_tree: rebuild a netlist's buffer trees by construction.
//
// ABC's `buffer -c` limits fanout by chaining: a BUFx2 drives ten loads,
// one of them the next BUFx2, so the last sinks of a broadcast net sit
// four to twelve buffers from their driver (ideas/xiangshan-frontend-
// synth.md). This takes each net with its buffer tree, removes the
// buffers, and builds a balanced tree over the same sinks: at most
// `max_fanout` pins and `max_load_ff` of pin capacitance per driver,
// each new buffer sized to its load. Sinks are grouped in instance-name
// order, which keeps a module's sinks together in a synthesis netlist
// that has no placement yet.
//
// Only buffers are removed, never inverters, so every sink keeps the
// polarity it had; Check() proves that each sink recorded before the
// rebuild still reaches its original driver through buffers only.
#pragma once

#include <functional>
#include <map>
#include <string>
#include <vector>

namespace odb {
class dbBlock;
class dbInst;
class dbITerm;
class dbMaster;
class dbNet;
}  // namespace odb

namespace fanout_tree {

// Input pin capacitance in fF by master and pin name, from liberty.
class PinCaps {
 public:
  // Reads `cell (...)`, `pin (...)`, `bus (...)` and their plain
  // `capacitance : v;` from a liberty file; a bus's capacitance applies
  // to each of its bits. Returns the number of cells read.
  int ReadLiberty(const std::string& path);
  // The capacitance of `pin` on `master`, `fallback` if unknown.
  double Get(const std::string& master, const std::string& pin,
             double fallback) const;
  void Set(const std::string& master, const std::string& pin, double ff) {
    caps_[master][pin] = ff;
  }

 private:
  std::map<std::string, std::map<std::string, double>> caps_;
};

struct Buffer {
  odb::dbMaster* master = nullptr;
  std::string in = "A";
  std::string out = "Y";
  double drive = 1;  // the x in BUFx<drive>
};

struct Options {
  int max_fanout = 16;
  double max_load_ff = 24.0;
  // Load a buffer of drive x is sized for: x >= load / ff_per_drive.
  double ff_per_drive = 2.5;
  double default_pin_ff = 0.6;
  // Nets with fewer sinks than this and no buffers are left alone.
  int min_sinks = 2;
  // A root driver of drive x (read from its master's name, INVx1: 1,
  // INVxp33: 0.33) is given at most x times this much load; the rest
  // goes behind buffers. 0 gives every root max_load_ff. A top port
  // driver always gets max_load_ff.
  double root_ff_per_drive = 0;
  // With a placer: wire capacitance per micron of a group's
  // half-perimeter, counted in its load.
  double wire_ff_per_um = 0.2;
  // Instead of a root load limit, swap a root driver whose load exceeds
  // drive * ff_per_drive for the smallest cell of its family that meets
  // it (AND2x2 -> AND2x4), the family being the name with its drive
  // taken out. Names containing any of `dont_use` are never chosen.
  bool upsize_roots = false;
  std::vector<std::string> dont_use;
};

// The x in a cell name: BUFx12f_ASAP7_75t_R 12, INVxp33_ASAP7_75t_R 0.33,
// 1 when there is none.
double DriveOf(const std::string& master_name);

struct Stats {
  int nets_rebuilt = 0;
  int buffers_removed = 0;
  int buffers_added = 0;
  int max_depth_before = 0;
  int max_depth_after = 0;
  long sinks = 0;
  int roots_upsized = 0;
};

// A cell name with its drive taken out, the key of its family:
// AND2x4_ASAP7_75t_R -> AND2x#_ASAP7_75t_R. Empty when it has none.
std::string FamilyOf(const std::string& master_name);

// A sink and the driver it must still reach: the original root driver
// as an (instance, pin) name pair, or a top port name with an empty pin.
struct Witness {
  odb::dbITerm* sink;
  std::string driver_inst;
  std::string driver_pin;
};

class Rebuilder {
 public:
  Rebuilder(odb::dbBlock* block, std::vector<Buffer> buffers,
            const PinCaps& caps, Options opt);
  // Rebuilds every signal net that roots a buffer tree or has more than
  // max_fanout sinks. Clock nets and do-not-touch nets are skipped.
  Stats Run();
  // Swaps every driver in the block whose pin load exceeds its drive
  // times ff_per_drive for the smallest family member that meets it
  // (needs upsize_roots for the families). Returns how many.
  int UpsizeAll();
  // Rebuilds the tree rooted at one net only.
  void RebuildNet(odb::dbNet* root);
  // Every witness recorded by Run/RebuildNet: its sink still reaches the
  // same driver through buffers only. Returns problems, empty if none.
  std::vector<std::string> Check() const;
  const Stats& stats() const { return stats_; }
  // Places a new buffer as it is made, near (x, y) in dbu. Set, and with
  // every sink of a net placed, groups are formed by position.
  void SetPlacer(std::function<void(odb::dbInst*, int, int)> place) {
    place_ = std::move(place);
  }

 private:
  bool IsBuffer(odb::dbMaster* m) const;
  const Buffer& Pick(double load_ff) const;
  double SinkCap(odb::dbITerm* it) const;
  void UpsizeRoot(odb::dbITerm* drv, double load_ff);

  odb::dbBlock* block_;
  std::vector<Buffer> buffers_;  // ascending drive
  const PinCaps& caps_;
  Options opt_;
  Stats stats_;
  std::vector<Witness> witnesses_;
  long serial_ = 0;
  std::function<void(odb::dbInst*, int, int)> place_;
  // family -> (drive, master), ascending
  std::map<std::string, std::vector<std::pair<double, odb::dbMaster*>>> families_;
};

}  // namespace fanout_tree
