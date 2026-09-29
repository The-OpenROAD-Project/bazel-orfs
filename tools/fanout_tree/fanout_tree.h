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

#include <map>
#include <string>
#include <vector>

namespace odb {
class dbBlock;
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
};

struct Stats {
  int nets_rebuilt = 0;
  int buffers_removed = 0;
  int buffers_added = 0;
  int max_depth_before = 0;
  int max_depth_after = 0;
  long sinks = 0;
};

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
  // Rebuilds the tree rooted at one net only.
  void RebuildNet(odb::dbNet* root);
  // Every witness recorded by Run/RebuildNet: its sink still reaches the
  // same driver through buffers only. Returns problems, empty if none.
  std::vector<std::string> Check() const;
  const Stats& stats() const { return stats_; }

 private:
  bool IsBuffer(odb::dbMaster* m) const;
  const Buffer& Pick(double load_ff) const;
  double SinkCap(odb::dbITerm* it) const;

  odb::dbBlock* block_;
  std::vector<Buffer> buffers_;  // ascending drive
  const PinCaps& caps_;
  Options opt_;
  Stats stats_;
  std::vector<Witness> witnesses_;
  long serial_ = 0;
};

}  // namespace fanout_tree
