// structured_gen: a multi-port register file as a placed standard-cell
// macro, built directly in odb. See regfile.h and README.md.
#include "regfile.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <functional>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "odb/db.h"
#include "odb/dbTypes.h"
#include "odb/geom.h"
#include "utl/Logger.h"

namespace structured_gen {

namespace {

using odb::dbBlock;
using odb::dbBTerm;
using odb::dbInst;
using odb::dbMaster;
using odb::dbNet;

std::string Bit(const std::string& bus, int i) {
  return bus + "[" + std::to_string(i) + "]";
}

int AddrBits(int words) {
  int a = 0;
  while ((1 << a) < words) {
    ++a;
  }
  return std::max(a, 1);
}

[[noreturn]] void Refuse(const std::string& what) {
  throw std::runtime_error(what);
}

// The pins of each cell kind, asap7's names by default; a spec may
// override them with `pins <kind> <name>...` in the same order.
struct Pins {
  std::vector<std::string> flop = {"D", "CLK", "QN"};  // data, clock, out
  std::vector<std::string> and2 = {"A", "B", "Y"};
  std::vector<std::string> or2 = {"A", "B", "Y"};
  std::vector<std::string> ao22 = {"A1", "A2", "B1", "B2", "Y"};
  std::vector<std::string> inv = {"A", "Y"};
  std::vector<std::string> tie_lo = {"L"};
  std::string pin_layer = "M4";
  bool flop_inverted = true;  // the flop's output is QN
};

Pins g_pins;  // set by ReadSpec, read by Generate

// Everything the builder needs while it lays cells into rows.
class Builder {
 public:
  Builder(odb::dbDatabase* db, utl::Logger* logger, const Spec& spec)
      : db_(db), logger_(logger), spec_(spec) {}

  dbBlock* Run();

 private:
  dbMaster* Master(const std::string& name, const char* role) {
    dbMaster* m = db_->findMaster(name.c_str());
    if (m == nullptr) {
      Refuse(std::string("cell for ") + role + " not in the loaded LEF: " + name);
    }
    return m;
  }
  void CheckPins(dbMaster* m, const std::vector<std::string>& pins) {
    for (const auto& p : pins) {
      if (m->findMTerm(p.c_str()) == nullptr) {
        Refuse("cell " + m->getName() + " has no pin " + p +
               "; give its pins with `pins <kind> ...` in the spec");
      }
    }
  }
  dbNet* Net(const std::string& name) {
    dbNet* n = block_->findNet(name.c_str());
    if (n == nullptr) {
      n = dbNet::create(block_, name.c_str());
    }
    return n;
  }
  dbBTerm* Input(const std::string& name) {
    dbNet* n = Net(name);
    dbBTerm* t = dbBTerm::create(n, name.c_str());
    t->setIoType(odb::dbIoType::INPUT);
    t->setSigType(odb::dbSigType::SIGNAL);
    return t;
  }
  dbBTerm* Output(const std::string& name, dbNet* net) {
    dbBTerm* t = dbBTerm::create(net, name.c_str());
    t->setIoType(odb::dbIoType::OUTPUT);
    t->setSigType(odb::dbSigType::SIGNAL);
    return t;
  }
  // A cell dropped into a row cursor: placed left to right, FIRM.
  struct Cursor {
    int row = 0;
    int x = 0;
  };
  dbInst* Place(Cursor& c, dbMaster* m, const std::string& name,
                const std::vector<std::pair<std::string, dbNet*>>& conns) {
    dbInst* inst = dbInst::create(block_, m, name.c_str());
    for (const auto& [pin, net] : conns) {
      odb::dbITerm* it = inst->findITerm(pin.c_str());
      if (it == nullptr) {
        Refuse("cell " + m->getName() + " has no pin " + pin);
      }
      it->connect(net);
    }
    inst->setOrient(c.row % 2 == 0 ? odb::dbOrientType::R0
                                   : odb::dbOrientType::MX);
    inst->setLocation(core_x0_ + c.x, core_y0_ + c.row * row_h_);
    inst->setPlacementStatus(odb::dbPlacementStatus::FIRM);
    c.x += static_cast<int>(m->getWidth());
    max_x_ = std::max(max_x_, c.x);
    return inst;
  }
  // A one-hot select for `bits` address literals and an enable: an AND2
  // tree over the literals, placed at the cursor.
  dbNet* Decode(Cursor& c, const std::string& prefix,
                const std::vector<dbNet*>& literals) {
    std::vector<dbNet*> level = literals;
    int k = 0;
    while (level.size() > 1) {
      std::vector<dbNet*> next;
      for (size_t i = 0; i + 1 < level.size(); i += 2) {
        dbNet* y = Net(prefix + "_a" + std::to_string(k++));
        Place(c, and2_, y->getName(),
              {{g_pins.and2[0], level[i]}, {g_pins.and2[1], level[i + 1]},
               {g_pins.and2[2], y}});
        next.push_back(y);
      }
      if (level.size() % 2 == 1) {
        next.push_back(level.back());
      }
      level = next;
    }
    return level.front();
  }
  // OR tree over `leaves`, each node placed by a caller-supplied hook so
  // the tree can run down a column rather than sit in a footer.
  dbNet* OrTree(const std::string& prefix, const std::vector<dbNet*>& leaves,
                const std::function<Cursor&(int lo, int hi)>& where) {
    std::function<dbNet*(int, int, int&)> rec = [&](int lo, int hi,
                                                     int& k) -> dbNet* {
      if (hi - lo == 1) {
        return leaves[lo];
      }
      int mid = (lo + hi) / 2;
      dbNet* a = rec(lo, mid, k);
      dbNet* b = rec(mid, hi, k);
      dbNet* y = Net(prefix + "_o" + std::to_string(k++));
      Place(where(lo, hi), or2_, y->getName(),
            {{g_pins.or2[0], a}, {g_pins.or2[1], b}, {g_pins.or2[2], y}});
      return y;
    };
    int k = 0;
    return rec(0, static_cast<int>(leaves.size()), k);
  }
  // The row of a tile or header with the least in it so far: cells of
  // different widths pack evenly, which a round robin does not do.
  static Cursor& Least(std::vector<Cursor>& rows) {
    return *std::min_element(
        rows.begin(), rows.end(),
        [](const Cursor& a, const Cursor& b) { return a.x < b.x; });
  }
  void Pin(dbBTerm* t, int x, int y) {
    odb::dbBPin* bp = odb::dbBPin::create(t);
    int w = pin_w_;
    odb::dbBox::create(bp, pin_layer_, x - w / 2, y - w / 2, x + w / 2,
                       y + w / 2);
    bp->setPlacementStatus(odb::dbPlacementStatus::FIRM);
  }

  odb::dbDatabase* db_;
  utl::Logger* logger_;
  const Spec& spec_;
  dbBlock* block_ = nullptr;
  odb::dbSite* site_ = nullptr;
  odb::dbTechLayer* pin_layer_ = nullptr;
  dbMaster* flop_ = nullptr;
  dbMaster* and2_ = nullptr;
  dbMaster* or2_ = nullptr;
  dbMaster* ao22_ = nullptr;
  dbMaster* inv_ = nullptr;
  dbMaster* tap_ = nullptr;
  dbMaster* tie_lo_ = nullptr;
  int site_w_ = 0;
  int row_h_ = 0;
  int core_x0_ = 0;
  int core_y0_ = 0;
  int pin_w_ = 0;
  int max_x_ = 0;
  // One entry per (word, bit) tile in row-major order: its row cursors,
  // which the read OR trees keep filling after the tile's own cells, and
  // the x where the tile ends, checked once the trees are in.
  struct Tile {
    std::vector<Cursor> rows;
    int x_end = 0;
  };
  std::vector<Tile> tiles_;
};

dbBlock* Builder::Run() {
  const Spec& s = spec_;
  if (s.words < 2 || s.bits < 1 || s.read.empty() || s.write.empty()) {
    Refuse("a register file needs at least 2 words, 1 bit, 1 read and 1 "
           "write port");
  }
  flop_ = Master(s.cells.flop, "flop");
  and2_ = Master(s.cells.and2, "and2");
  or2_ = Master(s.cells.or2, "or2");
  ao22_ = Master(s.cells.ao22, "ao22");
  inv_ = Master(s.cells.inv, "inv");
  tap_ = s.cells.tap.empty() ? nullptr : Master(s.cells.tap, "tap");
  tie_lo_ = s.cells.tie_lo.empty() ? nullptr : Master(s.cells.tie_lo, "tie_lo");
  CheckPins(flop_, g_pins.flop);
  CheckPins(and2_, g_pins.and2);
  CheckPins(or2_, g_pins.or2);
  CheckPins(ao22_, g_pins.ao22);
  CheckPins(inv_, g_pins.inv);

  odb::dbTech* tech = db_->getTech();
  site_ = flop_->getSite();
  if (site_ == nullptr) {
    Refuse("flop " + flop_->getName() + " has no site");
  }
  site_w_ = site_->getWidth();
  row_h_ = site_->getHeight();
  pin_layer_ = tech->findLayer(g_pins.pin_layer.c_str());
  if (pin_layer_ == nullptr) {
    Refuse("pin layer not in the tech LEF: " + g_pins.pin_layer);
  }
  pin_w_ = std::max(pin_layer_->getWidth(), 1u);

  odb::dbChip* chip = db_->getChip();
  if (chip == nullptr) {
    chip = odb::dbChip::create(db_, tech, s.module.c_str());
  }
  block_ = dbBlock::create(chip, s.module.c_str());
  if (block_ == nullptr) {
    Refuse("block " + s.module + " exists already");
  }
  block_->setDefUnits(tech->getLefUnits());

  const int W = static_cast<int>(s.write.size());
  const int R = static_cast<int>(s.read.size());
  const int A = AddrBits(s.words);

  // ---- ports and their nets ------------------------------------------
  dbNet* clock = Net(s.clock);
  Input(s.clock);
  std::vector<std::vector<dbNet*>> raddr(R), waddr(W), wdata(W);
  std::vector<dbNet*> wen(W, nullptr);
  for (int r = 0; r < R; ++r) {
    for (int i = 0; i < A; ++i) {
      raddr[r].push_back(Net(Bit(s.read[r].addr, i)));
      Input(Bit(s.read[r].addr, i));
    }
  }
  for (int w = 0; w < W; ++w) {
    for (int i = 0; i < A; ++i) {
      waddr[w].push_back(Net(Bit(s.write[w].addr, i)));
      Input(Bit(s.write[w].addr, i));
    }
    for (int b = 0; b < s.bits; ++b) {
      wdata[w].push_back(Net(Bit(s.write[w].data, b)));
      Input(Bit(s.write[w].data, b));
    }
    if (!s.write[w].en.empty()) {
      wen[w] = Net(s.write[w].en);
      Input(s.write[w].en);
    }
  }
  dbNet* vdd = Net("VDD");
  vdd->setSigType(odb::dbSigType::POWER);
  vdd->setSpecial();
  dbNet* vss = Net("VSS");
  vss->setSigType(odb::dbSigType::GROUND);
  vss->setSpecial();

  // ---- geometry --------------------------------------------------------
  // A word is `rows_per_word` standard rows tall; a bit column holds one
  // tile per word. The header column to the left holds the decode for
  // that word: R read selects, W write selects, the hold term.
  //
  // Cells per tile: flop, inverter (Q from QN), W-way write mux as AO22
  // pairs and an OR2 tree, R read AND2s, and this bit's share of the R
  // read OR trees, which run down the column.
  const int write_pairs = (W + 1) / 2;  // AO22 nodes; the last may hold Q
  const int tile_cells_w =
      static_cast<int>(flop_->getWidth() + inv_->getWidth() +
                       write_pairs * ao22_->getWidth() +
                       std::max(write_pairs - 1, 0) * or2_->getWidth() +
                       R * and2_->getWidth() + R * or2_->getWidth());
  int rows_per_word = 1;
  // Keep a tile near square-ish: at most ~40 sites wide.
  while (tile_cells_w / rows_per_word > 40 * site_w_ && rows_per_word < 8) {
    rows_per_word *= 2;
  }
  // Rows are filled least-first, so a row is at most one widest cell over
  // the average; the tile width carries that slack.
  const int widest = static_cast<int>(
      std::max({flop_->getWidth(), ao22_->getWidth(), or2_->getWidth(),
                and2_->getWidth()}));
  const int tile_w =
      ((tile_cells_w + rows_per_word - 1) / rows_per_word + widest +
       site_w_ - 1) /
      site_w_ * site_w_;
  // Header: per word, (R+W) decodes of (A+1) literals as AND2 trees, the
  // address inverters live above the array. hold_n = ~(OR of write selects).
  const int header_cells_w = static_cast<int>(
      (R + W) * A * and2_->getWidth() + (W - 1) * or2_->getWidth() +
      inv_->getWidth());
  const int header_w =
      ((header_cells_w + rows_per_word - 1) / rows_per_word + widest +
       site_w_ - 1) /
      site_w_ * site_w_;
  // A service column every `tap_columns` bit columns: the tap cell and
  // then `service_sites` empty sites on every row. The placement is
  // legal without them; what needs the room is what comes after -- the
  // clock tree's buffers and any repair -- and the slack inside a tile
  // is a few sites at a time, which a BUFx24 cannot use. Contiguous free
  // sites next to the flops are where a clock buffer wants to be.
  const int tap_w = (tap_ ? static_cast<int>(tap_->getWidth()) : 0) +
                    std::max(s.service_sites, 0) * site_w_;
  const int tap_every = std::max(s.tap_columns, 1);
  const int tap_cols = (tap_ || s.service_sites > 0)
                           ? (s.bits + tap_every - 1) / tap_every
                           : 0;
  // Banks: the word column folded into `banks` columns side by side, each
  // with its own header and service columns, so a 256-word file is not
  // ten times taller than it is wide. The read bitlines are one OR tree
  // per bank and a final OR across banks in a footer band.
  const int banks = std::max(s.banks, 1);
  if (s.words % banks != 0) {
    Refuse("words (" + std::to_string(s.words) + ") is not a multiple of banks (" +
           std::to_string(banks) + ")");
  }
  const int words_per_bank = s.words / banks;
  const int bank_w = header_w + s.bits * tile_w + tap_cols * tap_w;
  // Address inverters: one row band above the array.
  const int inv_rows = 1;
  // Footer: (banks-1) OR2 per read port per bit, as many rows as it takes.
  const int core_w = banks * bank_w;
  const int footer_cells_w =
      banks > 1 ? (banks - 1) * R * s.bits * static_cast<int>(or2_->getWidth()) : 0;
  const int footer_rows = banks > 1 ? (footer_cells_w + core_w - 1) / core_w + 1 : 0;
  const int total_rows = footer_rows + words_per_bank * rows_per_word + inv_rows;

  // Core at a site multiple in from the die so a parent's ring fits.
  core_x0_ = 10 * site_w_;
  core_y0_ = 2 * row_h_;
  const int die_w = core_w + 20 * site_w_;
  const int die_h = total_rows * row_h_ + 4 * row_h_;
  block_->setDieArea(odb::Rect(0, 0, die_w, die_h));
  for (int r = 0; r < total_rows; ++r) {
    std::string rn = "ROW_" + std::to_string(r);
    odb::dbRow::create(block_, rn.c_str(), site_, core_x0_,
                       core_y0_ + r * row_h_,
                       r % 2 == 0 ? odb::dbOrientType::R0
                                  : odb::dbOrientType::MX,
                       odb::dbRowDir::HORIZONTAL, core_w / site_w_, site_w_);
  }

  // ---- address inverters, top band ------------------------------------
  std::vector<std::vector<dbNet*>> raddr_n(R), waddr_n(W);
  {
    Cursor c{total_rows - 1, 0};
    for (int r = 0; r < R; ++r) {
      for (int i = 0; i < A; ++i) {
        dbNet* y = Net("rd" + std::to_string(r) + "_na" + std::to_string(i));
        Place(c, inv_, y->getName(),
              {{g_pins.inv[0], raddr[r][i]}, {g_pins.inv[1], y}});
        raddr_n[r].push_back(y);
      }
    }
    for (int w = 0; w < W; ++w) {
      for (int i = 0; i < A; ++i) {
        dbNet* y = Net("wr" + std::to_string(w) + "_na" + std::to_string(i));
        Place(c, inv_, y->getName(),
              {{g_pins.inv[0], waddr[w][i]}, {g_pins.inv[1], y}});
        waddr_n[w].push_back(y);
      }
    }
  }

  // ---- per word: header decode, then tiles across the bits -------------
  std::vector<std::vector<dbNet*>> rsel(R, std::vector<dbNet*>(s.words));
  std::vector<std::vector<dbNet*>> wsel(W, std::vector<dbNet*>(s.words));
  std::vector<dbNet*> hold(s.words);
  // Read OR-tree leaves per (r, b): the AND outputs down the column.
  std::vector<std::vector<std::vector<dbNet*>>> leaves(
      R, std::vector<std::vector<dbNet*>>(s.bits));

  auto literals = [&](const std::vector<dbNet*>& a,
                      const std::vector<dbNet*>& an, int n) {
    std::vector<dbNet*> l;
    for (int i = 0; i < A; ++i) {
      l.push_back(((n >> i) & 1) ? a[i] : an[i]);
    }
    return l;
  };

  for (int n = 0; n < s.words; ++n) {
    const int bank = n / words_per_bank;
    const int row0 = footer_rows + (n % words_per_bank) * rows_per_word;
    const int bank_x0 = bank * bank_w;
    // Header column, spread over this word's rows.
    std::vector<Cursor> hc;
    for (int k = 0; k < rows_per_word; ++k) {
      hc.push_back(Cursor{row0 + k, bank_x0});
    }
    auto hcur = [&]() -> Cursor& { return Least(hc); };
    std::string wn = "w" + std::to_string(n);
    for (int r = 0; r < R; ++r) {
      rsel[r][n] = Decode(hcur(), wn + "_rsel" + std::to_string(r),
                          literals(raddr[r], raddr_n[r], n));
    }
    std::vector<dbNet*> wsels;
    for (int w = 0; w < W; ++w) {
      std::vector<dbNet*> l = literals(waddr[w], waddr_n[w], n);
      if (wen[w] != nullptr) {
        l.push_back(wen[w]);
      }
      wsel[w][n] = Decode(hcur(), wn + "_wsel" + std::to_string(w), l);
      wsels.push_back(wsel[w][n]);
    }
    // hold = ~(wsel0 | wsel1 | ...): the word keeps its value.
    dbNet* any_write = wsels.size() == 1
                           ? wsels[0]
                           : OrTree(wn + "_anyw", wsels,
                                    [&](int, int) -> Cursor& { return hcur(); });
    hold[n] = Net(wn + "_hold");
    Place(hcur(), inv_, hold[n]->getName(),
          {{g_pins.inv[0], any_write}, {g_pins.inv[1], hold[n]}});
    for (auto& c : hc) {
      if (c.x > bank_x0 + header_w) {
        Refuse("header column overflow at word " + std::to_string(n) +
               ": widen the header estimate");
      }
    }

    // Tiles.
    int x = bank_x0 + header_w;
    for (int b = 0; b < s.bits; ++b) {
      if (tap_cols > 0 && b % tap_every == 0) {
        if (tap_) {
          for (int k = 0; k < rows_per_word; ++k) {
            Cursor tc{row0 + k, x};
            Place(tc, tap_, "tap_" + wn + "_c" + std::to_string(b / tap_every) +
                                "_r" + std::to_string(k), {});
          }
        }
        x += tap_w;  // the rest of the service column stays empty
      }
      std::string tn = wn + "_b" + std::to_string(b);
      std::vector<Cursor> tc;
      for (int k = 0; k < rows_per_word; ++k) {
        tc.push_back(Cursor{row0 + k, x});
      }
      auto tcur = [&]() -> Cursor& { return Least(tc); };

      // Storage. The flop's QN holds ~value; Q is recovered by an inverter.
      dbNet* d = Net(tn + "_d");
      dbNet* qn = Net(tn + "_qn");
      dbNet* q = g_pins.flop_inverted ? Net(tn + "_q") : qn;
      Place(tcur(), flop_, tn + "_ff",
            {{g_pins.flop[0], d}, {g_pins.flop[1], clock}, {g_pins.flop[2], qn}});
      if (g_pins.flop_inverted) {
        Place(tcur(), inv_, tn + "_qinv", {{g_pins.inv[0], qn}, {g_pins.inv[1], q}});
      }
      // Write mux: d = OR_w (wsel_w & wdata_w[b]) | (hold & q), as AO22
      // pairs then an OR2 tree.
      std::vector<std::pair<dbNet*, dbNet*>> terms;
      for (int w = 0; w < W; ++w) {
        terms.emplace_back(wsel[w][n], wdata[w][b]);
      }
      terms.emplace_back(hold[n], q);
      std::vector<dbNet*> partial;
      for (size_t i = 0; i < terms.size(); i += 2) {
        dbNet* y = Net(tn + "_wm" + std::to_string(i / 2));
        if (i + 1 < terms.size()) {
          Place(tcur(), ao22_, y->getName(),
                {{g_pins.ao22[0], terms[i].first},
                 {g_pins.ao22[1], terms[i].second},
                 {g_pins.ao22[2], terms[i + 1].first},
                 {g_pins.ao22[3], terms[i + 1].second},
                 {g_pins.ao22[4], y}});
        } else {
          Place(tcur(), and2_, y->getName(),
                {{g_pins.and2[0], terms[i].first},
                 {g_pins.and2[1], terms[i].second},
                 {g_pins.and2[2], y}});
        }
        partial.push_back(y);
      }
      dbNet* mux = partial.size() == 1
                       ? partial[0]
                       : OrTree(tn + "_wo", partial,
                                [&](int, int) -> Cursor& { return tcur(); });
      // The OR tree's root must be the flop's D net: alias by re-connecting.
      if (mux != d) {
        // Move every iterm on `mux` to `d`.
        std::vector<odb::dbITerm*> its(mux->getITerms().begin(),
                                       mux->getITerms().end());
        for (auto* it : its) {
          it->disconnect();
          it->connect(d);
        }
        dbNet::destroy(mux);
      }
      // Read ANDs: one per port, the leaves of that port's bitline.
      for (int r = 0; r < R; ++r) {
        dbNet* y = Net(tn + "_r" + std::to_string(r));
        Place(tcur(), and2_, y->getName(),
              {{g_pins.and2[0], rsel[r][n]}, {g_pins.and2[1], q},
               {g_pins.and2[2], y}});
        leaves[r][b].push_back(y);
      }
      // Keep the row cursors: the read OR trees fill the tile's leftover.
      tiles_.push_back(Tile{tc, x + tile_w});
      x += tile_w;
    }
  }

  // ---- read bitlines: OR trees down each column ------------------------
  // A node covering words [lo, hi) is dropped into the tile of word
  // (lo+hi)/2 in that bit column, round-robin over its rows.
  std::vector<std::vector<dbNet*>> rdata(R);
  std::vector<Cursor> footer;
  for (int k = 0; k < footer_rows; ++k) {
    footer.push_back(Cursor{k, 0});
  }
  for (int r = 0; r < R; ++r) {
    for (int b = 0; b < s.bits; ++b) {
      std::string prefix = "rd" + std::to_string(r) + "_b" + std::to_string(b);
      std::vector<dbNet*> bank_roots;
      for (int k = 0; k < banks; ++k) {
        std::vector<dbNet*> bank_leaves(
            leaves[r][b].begin() + k * words_per_bank,
            leaves[r][b].begin() + (k + 1) * words_per_bank);
        bank_roots.push_back(OrTree(
            prefix + "_k" + std::to_string(k), bank_leaves,
            [&](int lo, int hi) -> Cursor& {
              int n = k * words_per_bank + (lo + hi) / 2;
              return Least(tiles_[n * s.bits + b].rows);
            }));
      }
      dbNet* root = banks == 1
                        ? bank_roots[0]
                        : OrTree(prefix + "_f", bank_roots,
                                 [&](int, int) -> Cursor& { return Least(footer); });
      // Output port, its own net so the bterm has the RTL name.
      std::string name = Bit(s.read[r].data, b);
      std::vector<odb::dbITerm*> its(root->getITerms().begin(),
                                     root->getITerms().end());
      dbNet* out = Net(name);
      for (auto* it : its) {
        it->disconnect();
        it->connect(out);
      }
      dbNet::destroy(root);
      Output(name, out);
      rdata[r].push_back(out);
    }
  }
  for (size_t i = 0; i < tiles_.size(); ++i) {
    for (const auto& c : tiles_[i].rows) {
      if (c.x > tiles_[i].x_end) {
        Refuse("tile " + std::to_string(i) + " overflowed by " +
               std::to_string(c.x - tiles_[i].x_end) +
               " dbu once its read OR trees were in: widen the tile estimate");
      }
    }
  }
  for (const auto& c : footer) {
    if (c.x > core_w) {
      Refuse("footer overflow: widen the footer estimate");
    }
  }
  if (max_x_ > core_w) {
    Refuse("placement ran past the core: " + std::to_string(max_x_) + " > " +
           std::to_string(core_w));
  }

  // ---- pins on the die edge --------------------------------------------
  // Read data along the bottom, write data along the top, addresses,
  // enables and the clock on the left, spread on the pin layer's pitch.
  const int pitch = std::max(pin_layer_->getPitch(), pin_w_ * 2);
  int px = core_x0_ + pitch;
  for (int r = 0; r < R; ++r) {
    for (int b = 0; b < s.bits; ++b) {
      Pin(block_->findBTerm(Bit(s.read[r].data, b).c_str()), px, pin_w_);
      px += pitch;
    }
  }
  px = core_x0_ + pitch;
  for (int w = 0; w < W; ++w) {
    for (int b = 0; b < s.bits; ++b) {
      Pin(block_->findBTerm(Bit(s.write[w].data, b).c_str()), px, die_h - pin_w_);
      px += pitch;
    }
  }
  int py = core_y0_ + pitch;
  auto left = [&](const std::string& name) {
    Pin(block_->findBTerm(name.c_str()), pin_w_, py);
    py += pitch;
  };
  left(s.clock);
  for (int r = 0; r < R; ++r) {
    for (int i = 0; i < A; ++i) {
      left(Bit(s.read[r].addr, i));
    }
  }
  for (int w = 0; w < W; ++w) {
    for (int i = 0; i < A; ++i) {
      left(Bit(s.write[w].addr, i));
    }
    if (wen[w] != nullptr) {
      left(s.write[w].en);
    }
  }
  if (px > die_w || py > die_h) {
    Refuse("more pins than the die edge holds at this pitch; the array is "
           "too narrow for its ports");
  }

  logger_->report(
      "structured_gen: {} {}x{} {}R{}W in {} bank(s): {} rows of {} sites, die "
      "{} x {} um, {} instances",
      s.module, s.words, s.bits, R, W, banks, total_rows, core_w / site_w_,
      die_w / static_cast<double>(tech->getLefUnits()),
      die_h / static_cast<double>(tech->getLefUnits()),
      block_->getInsts().size());
  return block_;
}

}  // namespace

Spec ReadSpec(const std::string& path) {
  std::ifstream in(path);
  if (!in) {
    Refuse("cannot read spec " + path);
  }
  Spec s;
  g_pins = Pins();
  std::string line;
  int lineno = 0;
  while (std::getline(in, line)) {
    ++lineno;
    auto hash = line.find('#');
    if (hash != std::string::npos) {
      line = line.substr(0, hash);
    }
    std::istringstream ss(line);
    std::string key;
    if (!(ss >> key)) {
      continue;
    }
    std::vector<std::string> v;
    for (std::string t; ss >> t;) {
      v.push_back(t);
    }
    auto need = [&](size_t n) {
      if (v.size() != n) {
        Refuse(path + ":" + std::to_string(lineno) + ": `" + key + "` takes " +
               std::to_string(n) + " value(s)");
      }
    };
    if (key == "module") {
      need(1);
      s.module = v[0];
    } else if (key == "words") {
      need(1);
      s.words = std::stoi(v[0]);
    } else if (key == "bits") {
      need(1);
      s.bits = std::stoi(v[0]);
    } else if (key == "clock") {
      need(1);
      s.clock = v[0];
    } else if (key == "read") {
      need(2);
      s.read.push_back(Port{v[0], v[1], ""});
    } else if (key == "write") {
      if (v.size() != 2 && v.size() != 3) {
        Refuse(path + ":" + std::to_string(lineno) +
               ": `write` takes addr data [en]");
      }
      s.write.push_back(Port{v[0], v[1], v.size() == 3 ? v[2] : ""});
    } else if (key == "cell") {
      need(2);
      const std::string& kind = v[0];
      if (kind == "flop") s.cells.flop = v[1];
      else if (kind == "and2") s.cells.and2 = v[1];
      else if (kind == "or2") s.cells.or2 = v[1];
      else if (kind == "ao22") s.cells.ao22 = v[1];
      else if (kind == "inv") s.cells.inv = v[1];
      else if (kind == "tap") s.cells.tap = v[1];
      else if (kind == "tie_lo") s.cells.tie_lo = v[1];
      else Refuse(path + ":" + std::to_string(lineno) + ": unknown cell kind " + kind);
    } else if (key == "pins") {
      if (v.size() < 2) {
        Refuse(path + ":" + std::to_string(lineno) + ": `pins <kind> <pin>...`");
      }
      std::vector<std::string> pins(v.begin() + 1, v.end());
      const std::string& kind = v[0];
      auto set = [&](std::vector<std::string>& dst, size_t n) {
        if (pins.size() != n) {
          Refuse(path + ":" + std::to_string(lineno) + ": `pins " + kind +
                 "` takes " + std::to_string(n) + " pin names");
        }
        dst = pins;
      };
      if (kind == "flop") set(g_pins.flop, 3);
      else if (kind == "and2") set(g_pins.and2, 3);
      else if (kind == "or2") set(g_pins.or2, 3);
      else if (kind == "ao22") set(g_pins.ao22, 5);
      else if (kind == "inv") set(g_pins.inv, 2);
      else Refuse(path + ":" + std::to_string(lineno) + ": unknown pins kind " + kind);
    } else if (key == "flop_output") {
      need(1);
      if (v[0] == "QN") g_pins.flop_inverted = true;
      else if (v[0] == "Q") g_pins.flop_inverted = false;
      else Refuse(path + ":" + std::to_string(lineno) + ": flop_output is Q or QN");
    } else if (key == "pin_layer") {
      need(1);
      g_pins.pin_layer = v[0];
    } else if (key == "tap_columns") {
      need(1);
      s.tap_columns = std::stoi(v[0]);
    } else if (key == "service_sites") {
      need(1);
      s.service_sites = std::stoi(v[0]);
    } else if (key == "banks") {
      need(1);
      s.banks = std::stoi(v[0]);
    } else {
      Refuse(path + ":" + std::to_string(lineno) + ": unknown key `" + key + "`");
    }
  }
  if (s.module.empty()) Refuse(path + ": no `module`");
  if (s.cells.flop.empty() || s.cells.and2.empty() || s.cells.or2.empty() ||
      s.cells.ao22.empty() || s.cells.inv.empty()) {
    Refuse(path + ": cells flop, and2, or2, ao22 and inv are all required");
  }
  return s;
}

odb::dbBlock* Generate(odb::dbDatabase* db, utl::Logger* logger,
                       const Spec& spec) {
  Builder b(db, logger, spec);
  return b.Run();
}

void WriteVerilog(odb::dbBlock* block, const std::string& path) {
  std::ofstream out(path);
  if (!out) {
    Refuse("cannot write " + path);
  }
  // Group bterms into buses by `name[i]`.
  struct Bus {
    odb::dbIoType io;
    int hi = -1;
    bool scalar = false;
  };
  std::map<std::string, Bus> buses;
  std::vector<std::string> order;
  for (odb::dbBTerm* t : block->getBTerms()) {
    std::string n = t->getName();
    if (t->getSigType() != odb::dbSigType::SIGNAL) {
      continue;
    }
    auto lb = n.rfind('[');
    std::string base = n;
    int idx = -1;
    if (lb != std::string::npos && n.back() == ']') {
      base = n.substr(0, lb);
      idx = std::stoi(n.substr(lb + 1, n.size() - lb - 2));
    }
    auto it = buses.find(base);
    if (it == buses.end()) {
      order.push_back(base);
      it = buses.emplace(base, Bus{t->getIoType(), -1, idx < 0}).first;
    }
    it->second.hi = std::max(it->second.hi, idx);
  }
  out << "// Generated by structured_gen. Structural: every cell placed.\n";
  out << "module " << block->getName() << "(\n";
  for (size_t i = 0; i < order.size(); ++i) {
    const Bus& b = buses[order[i]];
    out << "  " << (b.io == odb::dbIoType::INPUT ? "input" : "output");
    if (!b.scalar) {
      out << " [" << b.hi << ":0]";
    }
    out << " " << order[i] << (i + 1 < order.size() ? ",\n" : "\n");
  }
  out << ");\n";
  for (odb::dbNet* n : block->getNets()) {
    if (n->getBTerms().begin() != n->getBTerms().end()) {
      continue;  // a port
    }
    if (n->getSigType() == odb::dbSigType::POWER ||
        n->getSigType() == odb::dbSigType::GROUND) {
      continue;
    }
    out << "  wire \\" << n->getName() << " ;\n";
  }
  for (odb::dbInst* inst : block->getInsts()) {
    out << "  " << inst->getMaster()->getName() << " \\" << inst->getName()
        << " (";
    bool first = true;
    for (odb::dbITerm* it : inst->getITerms()) {
      odb::dbNet* n = it->getNet();
      if (n == nullptr) {
        continue;
      }
      if (n->getSigType() == odb::dbSigType::POWER ||
          n->getSigType() == odb::dbSigType::GROUND) {
        continue;
      }
      out << (first ? "" : ", ") << "." << it->getMTerm()->getName() << "(";
      // A port net is written by its port name, buses with [i] intact.
      out << (n->getBTerms().begin() != n->getBTerms().end()
                  ? n->getName()
                  : "\\" + n->getName() + " ")
          << ")";
      first = false;
    }
    out << ");\n";
  }
  out << "endmodule\n";
}

}  // namespace structured_gen
