// array_reroll: a packed register vector, read and written at a variable
// index, back into the memory it is.
//
// slang elaborates `reg [N-1:0][W-1:0] r` (firtool's --preserve-aggregate
// output, and RTL written packed) into one $dff per word, a $bmux per
// read and, per write, a $demux of the address into a word mask that a
// $bwmux merges the data under, behind a $mux on the write enable. yosys's
// memory inference starts from unpacked arrays and never sees it. This
// pass finds the words a $bmux reads, walks their D input back through
// the write ports to their Q, and replaces the lot with one $mem_v2:
// asynchronous reads, synchronous writes, the later write winning. A
// vector whose updates are not of that shape (per-entry counters, flags,
// range clears) is left as it is and listed with the reason, for the
// classifier to take.

#include "kernel/mem.h"
#include "kernel/sigtools.h"
#include "kernel/yosys.h"

USING_YOSYS_NAMESPACE
PRIVATE_NAMESPACE_BEGIN

struct WritePort
{
  // the write's own enable, and the bits of the word it writes (a byte
  // lane's, or all of them)
  SigBit en;
  std::vector<bool> lanes;
  SigSpec addr;
  SigSpec data;
  // conditions around the write that hold the vector instead: a reset
  // branch, for one; (signal, true) when the write needs it low
  std::vector<std::pair<SigBit, bool>> holds;
  std::vector<Cell*> cells;
};

struct Reroller
{
  Module* module;
  SigMap sigmap;
  // a bit's driver: the cell and the output port's offset
  dict<SigBit, std::pair<Cell*, int>> driver;

  explicit Reroller(Module* m) : module(m), sigmap(m)
  {
    for (auto cell : module->cells()) {
      for (auto& conn : cell->connections()) {
        if (!cell->output(conn.first)) {
          continue;
        }
        SigSpec sig = sigmap(conn.second);
        for (int i = 0; i < GetSize(sig); i++) {
          driver[sig[i]] = {cell, i};
        }
      }
    }
  }

  // the one cell driving all of sig from its output Y, in order, or null
  Cell* whole_driver(const SigSpec& sig)
  {
    Cell* found = nullptr;
    for (int i = 0; i < GetSize(sig); i++) {
      auto it = driver.find(sig[i]);
      if (it == driver.end() || it->second.second != i) {
        return nullptr;
      }
      if (found && found != it->second.first) {
        return nullptr;
      }
      found = it->second.first;
    }
    if (found && sigmap(found->getPort(ID::Y)) != sig) {
      return nullptr;
    }
    return found;
  }

  // the words a $bmux reads, one $dff each, or empty
  std::vector<Cell*> words_of(Cell* bmux)
  {
    int width = bmux->getParam(ID::WIDTH).as_int();
    SigSpec a = sigmap(bmux->getPort(ID::A));
    int n = GetSize(a) / width;
    std::vector<Cell*> words;
    SigSpec clk;
    for (int i = 0; i < n; i++) {
      SigSpec chunk = a.extract(i * width, width);
      auto it = driver.find(chunk[0]);
      if (it == driver.end()) {
        return {};
      }
      Cell* dff = it->second.first;
      if (dff->type != ID($dff) || dff->getParam(ID::WIDTH).as_int() != width
          || sigmap(dff->getPort(ID::Q)) != chunk) {
        return {};
      }
      if (i == 0) {
        clk = sigmap(dff->getPort(ID::CLK));
      } else if (sigmap(dff->getPort(ID::CLK)) != clk
                 || dff->getParam(ID::CLK_POLARITY)
                        != words[0]->getParam(ID::CLK_POLARITY)) {
        return {};
      }
      words.push_back(dff);
    }
    return words;
  }

  // the write ports from the words' D back to their Q, last applied
  // first; false with a reason when a step is not a write port
  bool write_ports(const std::vector<Cell*>& words,
                   std::vector<WritePort>& ports,
                   std::string& why)
  {
    int width = words[0]->getParam(ID::WIDTH).as_int();
    int n = GetSize(words);
    SigSpec q, cur;
    for (auto dff : words) {
      q.append(sigmap(dff->getPort(ID::Q)));
      cur.append(sigmap(dff->getPort(ID::D)));
    }
    // conditions found so far, outermost first, that hold the vector
    std::vector<std::pair<SigBit, bool>> holds;
    std::vector<Cell*> hold_cells;
    while (cur != q) {
      Cell* top = whole_driver(cur);
      if (!top) {
        why = "a word's next value is not one cell over the whole vector";
        return false;
      }
      // a branch that keeps the vector as it is (the reset branch of a
      // FIFO that writes in its else): a condition on every write inside
      // (the innermost write's own enable mux also has Q on A, its B a
      // $bwmux over Q: that is a write, not a hold)
      auto is_write_of = [&](const SigSpec& sig, const SigSpec& base) {
        Cell* c = whole_driver(sig);
        return c && c->type == ID($bwmux) && sigmap(c->getPort(ID::A)) == base;
      };
      bool b_holds = top->type == ID($mux) && sigmap(top->getPort(ID::B)) == q;
      bool a_holds = top->type == ID($mux) && sigmap(top->getPort(ID::A)) == q
                     && !is_write_of(sigmap(top->getPort(ID::B)), q);
      if (GetSize(top->getPort(ID::S)) == 1 && (a_holds || b_holds)) {
        bool hold_when_high = b_holds;
        holds.push_back({sigmap(top->getPort(ID::S))[0], hold_when_high});
        hold_cells.push_back(top);
        cur = sigmap(top->getPort(hold_when_high ? ID::A : ID::B));
        continue;
      }
      // a branch that assigns x (proc's "not assigned here") may as well
      // keep the other input
      if (top->type == ID($mux)
          && (sigmap(top->getPort(ID::A)).is_fully_undef()
              || sigmap(top->getPort(ID::B)).is_fully_undef())) {
        hold_cells.push_back(top);
        cur = sigmap(top->getPort(ID::A)).is_fully_undef()
                  ? sigmap(top->getPort(ID::B))
                  : sigmap(top->getPort(ID::A));
        continue;
      }
      WritePort port;
      port.holds = holds;
      SigSpec merged;
      if (top->type == ID($mux) && GetSize(top->getPort(ID::S)) == 1) {
        port.en = sigmap(top->getPort(ID::S))[0];
        port.cells.push_back(top);
        merged = sigmap(top->getPort(ID::B));
        cur = sigmap(top->getPort(ID::A));
      } else if (top->type == ID($bwmux)) {
        port.en = State::S1;
        merged = cur;
      } else {
        why = std::string("an update by ") + log_id(top->type) + ", not a write port";
        return false;
      }
      Cell* bw = whole_driver(merged);
      if (!bw || bw->type != ID($bwmux)
          || sigmap(bw->getPort(ID::A)) != cur) {
        why = "a write's merge is not a $bwmux over the vector";
        return false;
      }
      // the word mask: a $demux of a constant by the address, ones in the
      // bits the write covers (all of them, or a byte lane's)
      Cell* mask = whole_driver(sigmap(bw->getPort(ID::S)));
      SigSpec pattern = sigmap(mask ? mask->getPort(ID::A) : SigSpec());
      if (!mask || mask->type != ID($demux) || !pattern.is_fully_const()
          || GetSize(pattern) != width || pattern.is_fully_zero()) {
        why = "a write's word mask is not a $demux of the address";
        return false;
      }
      port.lanes.resize(width);
      for (int k = 0; k < width; k++) {
        port.lanes[k] = pattern[k] == State::S1;
      }
      SigSpec data = sigmap(bw->getPort(ID::B));
      SigSpec word = data.extract(0, width);
      for (int i = 1; i < n; i++) {
        SigSpec other = data.extract(i * width, width);
        for (int k = 0; k < width; k++) {
          if (port.lanes[k] && other[k] != word[k]) {
            why = "a write's data is not one word repeated";
            return false;
          }
        }
      }
      for (int k = 0; k < width; k++) {
        if (!port.lanes[k]) {
          word[k] = State::Sx;
        }
      }
      port.addr = sigmap(mask->getPort(ID::S));
      port.data = word;
      port.cells.push_back(bw);
      port.cells.push_back(mask);
      ports.push_back(port);
    }
    for (auto cell : hold_cells) {
      if (!ports.empty()) {
        ports.back().cells.push_back(cell);
      }
    }
    return true;
  }

  // a write's enable per bit: its own, its lanes, and no hold around it
  SigSpec enable(const WritePort& port)
  {
    SigBit en = port.en;
    for (auto& [sig, hold_when_high] : port.holds) {
      SigBit open = hold_when_high ? module->Not(NEW_ID, sig)[0] : sig;
      en = en == State::S1 ? open : module->And(NEW_ID, en, open)[0];
    }
    SigSpec bits;
    for (bool lane : port.lanes) {
      bits.append(lane ? en : SigBit(State::S0));
    }
    return bits;
  }

  void run()
  {
    // the reads of each vector, by its words
    dict<std::vector<Cell*>, std::vector<Cell*>> reads;
    for (auto cell : module->selected_cells()) {
      if (cell->type != ID($bmux)) {
        continue;
      }
      auto words = words_of(cell);
      if (!words.empty()) {
        reads[words].push_back(cell);
      }
    }
    for (auto& [words, bmuxes] : reads) {
      std::vector<WritePort> ports;
      std::string why;
      int width = words[0]->getParam(ID::WIDTH).as_int();
      int n = GetSize(words);
      if (!write_ports(words, ports, why)) {
        log("array_reroll: %s.%s, %d x %d, left as registers: %s\n",
            log_id(module), log_id(words[0]), n, width, why.c_str());
        continue;
      }
      std::reverse(ports.begin(), ports.end());
      Mem mem(module, NEW_ID, width, 0, n);
      SigSpec clk = sigmap(words[0]->getPort(ID::CLK));
      bool polarity = words[0]->getParam(ID::CLK_POLARITY).as_bool();
      for (int i = 0; i < GetSize(ports); i++) {
        MemWr wr;
        wr.wide_log2 = 0;
        wr.clk_enable = true;
        wr.clk_polarity = polarity;
        wr.clk = clk;
        wr.en = enable(ports[i]);
        wr.addr = ports[i].addr;
        wr.data = ports[i].data;
        // a later port overrides every earlier one
        wr.priority_mask = std::vector<bool>(GetSize(ports), false);
        for (int j = 0; j < i; j++) {
          wr.priority_mask[j] = true;
        }
        mem.wr_ports.push_back(wr);
      }
      for (auto bmux : bmuxes) {
        MemRd rd;
        rd.wide_log2 = 0;
        rd.clk_enable = false;
        rd.clk_polarity = true;
        rd.clk = State::Sx;
        rd.en = State::S1;
        rd.arst = State::S0;
        rd.srst = State::S0;
        rd.ce_over_srst = false;
        rd.arst_value = Const(State::Sx, width);
        rd.srst_value = Const(State::Sx, width);
        rd.init_value = Const(State::Sx, width);
        rd.transparency_mask = std::vector<bool>(GetSize(ports), false);
        rd.collision_x_mask = std::vector<bool>(GetSize(ports), false);
        rd.addr = sigmap(bmux->getPort(ID::S));
        rd.data = bmux->getPort(ID::Y);
        mem.rd_ports.push_back(rd);
      }
      for (auto bmux : bmuxes) {
        module->remove(bmux);
      }
      pool<Cell*> gone;
      for (auto& port : ports) {
        for (auto cell : port.cells) {
          gone.insert(cell);
        }
      }
      for (auto cell : gone) {
        module->remove(cell);
      }
      for (auto dff : words) {
        module->remove(dff);
      }
      mem.emit();
      log("array_reroll: %s, %d x %d, %d reads, %d writes: one memory\n",
          log_id(module), n, width, GetSize(bmuxes), GetSize(ports));
    }
  }
};

struct ArrayRerollPass : public Pass
{
  ArrayRerollPass()
      : Pass("array_reroll",
             "a packed register vector read and written by index, as a memory")
  {
  }

  void help() override
  {
    log("\n");
    log("    array_reroll [selection]\n");
    log("\n");
    log("Finds packed register vectors that are read with $bmux and written\n");
    log("through $demux word masks and $bwmux merges, and replaces each with\n");
    log("one $mem_v2. Run after proc and opt; vectors of another shape are\n");
    log("left as registers and listed with the reason.\n");
    log("\n");
  }

  void execute(std::vector<std::string> args, Design* design) override
  {
    log_header(design, "Executing ARRAY_REROLL pass.\n");
    extra_args(args, 1, design);
    for (auto module : design->selected_modules()) {
      Reroller(module).run();
    }
  }
} ArrayRerollPass;

PRIVATE_NAMESPACE_END
