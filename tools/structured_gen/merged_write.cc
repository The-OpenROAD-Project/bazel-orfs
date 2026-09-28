// structured_gen: a merged write as a placed block. See merged_write.h.
#include "merged_write.h"

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "nlohmann/json.hpp"
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

[[noreturn]] void Refuse(const std::string& what) {
  throw std::runtime_error(what);
}

std::string Bit(const std::string& bus, int width, int i) {
  return width == 1 ? bus : bus + "[" + std::to_string(i) + "]";
}

std::string Subst(std::string t, int w, const std::string& field,
                  const std::string& reg) {
  auto rep = [&](const std::string& key, const std::string& val) {
    for (size_t p = t.find(key); p != std::string::npos; p = t.find(key, p)) {
      t.replace(p, key.size(), val);
      p += val.size();
    }
  };
  rep("{w}", std::to_string(w));
  rep("{field}", field);
  rep("{reg}", reg);
  return t;
}

// The kinds of cell the builder places, and how many pins each has.
const std::map<std::string, int> kCellPins = {
    {"flop", 3},  {"rflop", 5}, {"inv", 2},  {"buf", 2},   {"and2", 3},
    {"and3", 4},  {"nand3", 4}, {"and4", 5}, {"nor4", 5},  {"or2", 3},
    {"xnor2", 3}, {"ao22", 5},  {"ao222", 7}, {"tiehi", 1},
};

// Every cell is placed into a column and a row, left to right within
// the column; the columns' x offsets are known only once all are full.
struct Slot {
  dbInst* inst;
  int col;
  int row;
  int x;  // within the column, DBU
};

class Builder {
 public:
  Builder(odb::dbDatabase* db, const MergedWriteSpec& spec)
      : db_(db), spec_(spec) {}

  dbBlock* Run();

 private:
  const CellRef& Cell(const std::string& kind) {
    auto it = cells_.find(kind);
    if (it == cells_.end()) {
      Refuse("spec names no cell for `" + kind + "`");
    }
    return it->second;
  }
  dbNet* Net(const std::string& name) {
    dbNet* n = block_->findNet(name.c_str());
    if (n == nullptr) {
      n = dbNet::create(block_, name.c_str());
    }
    return n;
  }
  dbNet* Input(const std::string& name) {
    dbNet* n = Net(name);
    if (block_->findBTerm(name.c_str()) == nullptr) {
      dbBTerm* t = dbBTerm::create(n, name.c_str());
      t->setIoType(odb::dbIoType::INPUT);
      t->setSigType(odb::dbSigType::SIGNAL);
      inputs_.push_back(t);
    }
    return n;
  }
  // An output port whose net is named after it: the Verilog writer
  // writes a port net by its own name.
  dbNet* Output(const std::string& name) {
    dbNet* n = Net(name);
    dbBTerm* t = dbBTerm::create(n, name.c_str());
    t->setIoType(odb::dbIoType::OUTPUT);
    t->setSigType(odb::dbSigType::SIGNAL);
    outputs_.push_back(t);
    return n;
  }
  // A cell named `name` in column `col`, row `row`, pins in the spec's
  // order connected to `nets`.
  dbInst* Put(const std::string& kind, const std::string& name, int col,
              int row, const std::vector<dbNet*>& nets) {
    const CellRef& c = Cell(kind);
    dbMaster* m = db_->findMaster(c.master.c_str());
    if (m == nullptr) {
      Refuse("cell for " + kind + " not in the loaded LEF: " + c.master);
    }
    if (nets.size() != c.pins.size()) {
      Refuse("internal: " + kind + " takes " + std::to_string(c.pins.size()) +
             " nets");
    }
    std::string inst_name = name;
    if (block_->findNet(name.c_str()) != nullptr) {
      inst_name += "_g";
    }
    dbInst* inst = dbInst::create(block_, m, inst_name.c_str());
    for (size_t i = 0; i < nets.size(); ++i) {
      odb::dbITerm* it = inst->findITerm(c.pins[i].c_str());
      if (it == nullptr) {
        Refuse("cell " + c.master + " has no pin " + c.pins[i]);
      }
      it->connect(nets[i]);
    }
    int& x = cursor_[{col, row}];
    slots_.push_back({inst, col, row, x});
    x += static_cast<int>(m->getWidth());
    return inst;
  }
  // `kind` gate named `prefix`: output net, input nets.
  dbNet* Gate(const std::string& kind, const std::string& prefix, int col,
              int row, const std::vector<dbNet*>& ins) {
    dbNet* y = Net(prefix);
    std::vector<dbNet*> nets = ins;
    nets.push_back(y);
    Put(kind, prefix, col, row, nets);
    return y;
  }
  // AND over `ins` as a tree of AND4/AND3/AND2, rows from `row` on.
  dbNet* AndTree(const std::string& prefix, std::vector<dbNet*> ins, int col,
                 int row) {
    int k = 0;
    while (ins.size() > 1) {
      std::vector<dbNet*> next;
      for (size_t i = 0; i < ins.size(); i += 4) {
        size_t n = std::min<size_t>(4, ins.size() - i);
        std::vector<dbNet*> g(ins.begin() + i, ins.begin() + i + n);
        if (n == 1) {
          next.push_back(g[0]);
          continue;
        }
        const char* kind = n == 4 ? "and4" : n == 3 ? "and3" : "and2";
        next.push_back(
            Gate(kind, prefix + "_a" + std::to_string(k), col, row + k % 4, g));
        ++k;
      }
      ins = next;
    }
    return ins.front();
  }
  // One buffer per `max_fanout` loads: returns, per load index, the net
  // that load connects to. The buffers sit in the spine column rows of
  // the loads they drive.
  std::vector<dbNet*> Fanout(const std::string& prefix, dbNet* src,
                             const std::vector<int>& load_rows, int col) {
    std::vector<dbNet*> out(load_rows.size());
    const int per = std::max(spec_.max_fanout, 1);
    for (size_t i = 0; i < load_rows.size(); i += per) {
      size_t n = std::min<size_t>(per, load_rows.size() - i);
      int mid = load_rows[i + n / 2];
      dbNet* b = Gate("buf", prefix + "_b" + std::to_string(i / per), col, mid,
                      {src});
      for (size_t j = 0; j < n; ++j) {
        out[i + j] = b;
      }
    }
    return out;
  }
  void Pin(dbBTerm* t, odb::dbTechLayer* layer, int x, int y) {
    odb::dbBPin* bp = odb::dbBPin::create(t);
    int w = std::max(static_cast<int>(layer->getWidth()), 1);
    odb::dbBox::create(bp, layer, x - w / 2, y - w / 2, x + w / 2, y + w / 2);
    bp->setPlacementStatus(odb::dbPlacementStatus::FIRM);
  }
  int Width(const std::string& bus) const {
    auto it = widths_.find(bus);
    if (it == widths_.end()) {
      Refuse("no field carries bus " + bus + "; its width is unknown");
    }
    return it->second;
  }

  odb::dbDatabase* db_;
  const MergedWriteSpec& spec_;
  dbBlock* block_ = nullptr;
  std::map<std::string, CellRef> cells_;
  std::map<std::string, int> widths_;
  std::map<std::pair<int, int>, int> cursor_;
  std::vector<Slot> slots_;
  std::vector<dbBTerm*> inputs_;
  std::vector<dbBTerm*> outputs_;
};

dbBlock* Builder::Run() {
  const MergedWriteSpec& s = spec_;
  for (const auto& [kind, ref] : s.cells) {
    auto it = kCellPins.find(kind);
    if (it == kCellPins.end()) {
      Refuse("unknown cell kind `" + kind + "`");
    }
    if (static_cast<int>(ref.pins.size()) != it->second) {
      Refuse("cell kind `" + kind + "` takes " + std::to_string(it->second) +
             " pins, spec gives " + std::to_string(ref.pins.size()));
    }
    cells_[kind] = ref;
  }
  if (s.ways < 1 || s.fields.empty()) {
    Refuse("a merged write needs at least one way and one field");
  }
  for (const auto& f : s.fields) {
    widths_[f.write] = f.width;
    if (!f.flush.empty()) {
      widths_[f.flush] = f.width;
    }
  }
  odb::dbTech* tech = db_->getTech();
  odb::dbChip* chip = db_->getChip();
  if (chip == nullptr) {
    chip = odb::dbChip::create(db_, tech, s.module.c_str());
  }
  if (chip->getBlock() != nullptr) {
    Refuse("the database already has a top block; one generation per database");
  }
  block_ = dbBlock::create(chip, s.module.c_str());
  if (block_ == nullptr) {
    Refuse("could not create block " + s.module);
  }
  block_->setDefUnits(tech->getLefUnits());
  const int dbu = tech->getLefUnits();

  // The rows' site is the flop's.
  dbMaster* flop = db_->findMaster(Cell("flop").master.c_str());
  if (flop == nullptr || flop->getSite() == nullptr) {
    Refuse("flop " + Cell("flop").master + " not in the LEF or has no site");
  }
  odb::dbSite* site = flop->getSite();
  const int site_w = static_cast<int>(site->getWidth());
  const int row_h = static_cast<int>(site->getHeight());

  // ---- ports -----------------------------------------------------------
  dbNet* clock = Input(s.clock);
  dbNet* reset = Input(s.reset);
  dbNet* wvalid = Input(s.write_valid);
  dbNet* fvalid = Input(s.flush_valid);
  std::vector<dbNet*> wmask, fmask;
  for (int w = 0; w < s.ways; ++w) {
    wmask.push_back(Input(Bit(s.write_way_mask, s.ways, w)));
  }
  for (int w = 0; w < s.ways; ++w) {
    fmask.push_back(Input(Bit(s.flush_way_mask, s.ways, w)));
  }
  std::map<std::string, std::vector<dbNet*>> bus;
  for (const auto& f : s.fields) {
    for (const std::string& b : {f.write, f.flush}) {
      if (b.empty() || bus.count(b)) {
        continue;
      }
      for (int i = 0; i < f.width; ++i) {
        bus[b].push_back(Input(Bit(b, f.width, i)));
      }
    }
  }
  for (const std::string& b :
       {s.conflict_equal_a, s.conflict_equal_b, s.conflict_zero}) {
    if (!bus.count(b)) {
      Refuse("conflict names bus " + b + ", which no field carries");
    }
  }
  dbNet* vdd = Net("VDD");
  vdd->setSigType(odb::dbSigType::POWER);
  vdd->setSpecial();
  dbNet* vss = Net("VSS");
  vss->setSigType(odb::dbSigType::GROUND);
  vss->setSpecial();

  // ---- rows of a way: valid first, then every field bit -----------------
  struct TileBit {
    const MergedField* f;
    int i;
  };
  std::vector<TileBit> tiles;
  for (const auto& f : s.fields) {
    for (int i = 0; i < f.width; ++i) {
      tiles.push_back({&f, i});
    }
  }
  const int rows = 1 + static_cast<int>(tiles.size());
  const int mid = rows / 2;
  // Columns: the first half of the ways, the shared control, the rest.
  // Each way is two columns, its spine (enables, buffers) then its tiles.
  const int half = (s.ways + 1) / 2;
  auto spine_col = [&](int w) { return 2 * w + (w >= half ? 1 : 0); };
  auto tile_col = [&](int w) { return spine_col(w) + 1; };
  const int ctrl_col = 2 * half;

  // ---- shared control: conflict, reset, tie ----------------------------
  const auto& ea = bus[s.conflict_equal_a];
  const auto& eb = bus[s.conflict_equal_b];
  if (ea.size() != eb.size()) {
    Refuse("conflict compares buses of different widths");
  }
  std::vector<dbNet*> eq_bits;
  for (size_t i = 0; i < ea.size(); ++i) {
    eq_bits.push_back(Gate("xnor2", "conflict_eq" + std::to_string(i),
                           ctrl_col, mid - 4 + static_cast<int>(i % 8),
                           {ea[i], eb[i]}));
  }
  dbNet* eq = AndTree("conflict_eq", eq_bits, ctrl_col, mid - 2);
  const auto& z = bus[s.conflict_zero];
  std::vector<dbNet*> zero_parts;
  for (size_t i = 0; i < z.size(); i += 4) {
    std::vector<dbNet*> g(z.begin() + i,
                          z.begin() + std::min(z.size(), i + 4));
    while (g.size() < 4) {
      g.push_back(g.back());  // a repeated input leaves the NOR unchanged
    }
    zero_parts.push_back(Gate("nor4", "conflict_z" + std::to_string(i / 4),
                              ctrl_col, mid + 2 + static_cast<int>(i / 4), g));
  }
  dbNet* zero = AndTree("conflict_z", zero_parts, ctrl_col, mid + 2);
  dbNet* nconflict =
      Gate("nand3", "nconflict", ctrl_col, mid, {wvalid, eq, zero});
  dbNet* nreset = Gate("inv", "nreset", ctrl_col, mid + 1, {reset});
  dbNet* tiehi = Net("tiehi");
  Put("tiehi", "tiehi_g", ctrl_col, mid + 1, {tiehi});

  // ---- ways ------------------------------------------------------------
  for (int w = 0; w < s.ways; ++w) {
    const std::string p = "w" + std::to_string(w);
    const int sc = spine_col(w);
    const int tc = tile_col(w);
    dbNet* wv = Gate("and2", p + "_writeValid", sc, mid - 1, {wvalid, wmask[w]});
    dbNet* fo =
        Gate("and3", p + "_flushValid", sc, mid, {fvalid, fmask[w], nconflict});
    dbNet* v = Gate("or2", p + "_valid", sc, mid + 1, {wv, fo});
    dbNet* nv = Gate("inv", p + "_nvalid", sc, mid + 1, {v});
    dbNet* nwv = Gate("inv", p + "_nwriteValid", sc, mid - 1, {wv});
    dbNet* fonly = Gate("and2", p + "_flushOnly", sc, mid, {fo, nwv});

    // The valid register, reset asynchronously, in the way's first row.
    const std::string vreg = Subst(s.reg_valid, w, "", "");
    dbNet* vqn = Net(vreg + "_qn");
    Put("rflop", vreg, tc, 0, {v, clock, vqn, nreset, tiehi});
    dbNet* vout = Output(Subst(s.out_valid, w, "", ""));
    Put("inv", vreg + "_qinv", tc, 0, {vqn, vout});

    // Enable fanout: the rows each enable reaches.
    std::vector<int> all_rows, flush_rows;
    for (size_t t = 0; t < tiles.size(); ++t) {
      all_rows.push_back(1 + static_cast<int>(t));
      if (!tiles[t].f->flush.empty()) {
        flush_rows.push_back(1 + static_cast<int>(t));
      }
    }
    auto wv_b = Fanout(p + "_writeValid", wv, all_rows, sc);
    auto nv_b = Fanout(p + "_nvalid", nv, all_rows, sc);
    auto fonly_b = Fanout(p + "_flushOnly", fonly, flush_rows, sc);
    size_t fk = 0;
    for (size_t t = 0; t < tiles.size(); ++t) {
      const MergedField& f = *tiles[t].f;
      const int i = tiles[t].i;
      const int row = 1 + static_cast<int>(t);
      const std::string reg = Subst(s.reg_field, w, f.name, f.reg);
      const std::string rbit = Bit(reg, f.width, i);
      dbNet* qn = Net(rbit + "_qn");
      dbNet* q = Output(Bit(Subst(s.out_field, w, f.name, f.reg), f.width, i));
      dbNet* d = Net(rbit + "_d");
      dbNet* a = bus[f.write][i];
      if (f.flush.empty()) {
        // valid & writeValid is writeValid: d = wv & a | !valid & q.
        Put("ao22", rbit + "_mux", tc, row, {wv_b[t], a, nv_b[t], q, d});
      } else {
        dbNet* b = bus[f.flush][i];
        Put("ao222", rbit + "_mux", tc, row,
            {wv_b[t], a, fonly_b[fk], b, nv_b[t], q, d});
        ++fk;
      }
      Put("flop", rbit, tc, row, {d, clock, qn});
      Put("inv", rbit + "_qinv", tc, row, {qn, q});
    }
  }

  // ---- placement: column offsets, rows, die ----------------------------
  const int cols = ctrl_col + 1 + 2 * (s.ways - half);
  std::vector<int> col_w(cols, 0);
  for (const auto& [key, x] : cursor_) {
    col_w[key.first] = std::max(col_w[key.first], x);
  }
  const int gap = 4 * site_w;
  std::vector<int> col_x(cols, 0);
  int x = 0;
  for (int c = 0; c < cols; ++c) {
    col_x[c] = x;
    int w = (col_w[c] + site_w - 1) / site_w * site_w;
    x += w + (w > 0 ? gap : 0);
  }
  const int core_w = x;
  const int margin = static_cast<int>(s.margin_um * dbu);
  const int margin_sites = std::max(10, (margin + site_w - 1) / site_w);
  // An even number of rows below, so the first row stays R0 once the
  // block is dissolved onto a parent's alternating rows.
  int margin_rows = std::max(2, (margin + row_h - 1) / row_h);
  margin_rows += margin_rows % 2;
  const int core_x0 = margin_sites * site_w;
  const int core_y0 = margin_rows * row_h;
  const int die_w = core_w + 2 * margin_sites * site_w;
  const int die_h = rows * row_h + 2 * margin_rows * row_h;
  block_->setDieArea(odb::Rect(0, 0, die_w, die_h));
  for (int r = 0; r < rows; ++r) {
    std::string rn = "ROW_" + std::to_string(r);
    odb::dbRow::create(block_, rn.c_str(), site, core_x0, core_y0 + r * row_h,
                       r % 2 == 0 ? odb::dbOrientType::R0
                                  : odb::dbOrientType::MX,
                       odb::dbRowDir::HORIZONTAL, core_w / site_w, site_w);
  }
  for (const Slot& sl : slots_) {
    if (sl.row < 0 || sl.row >= rows) {
      Refuse("internal: a cell was given row " + std::to_string(sl.row));
    }
    sl.inst->setOrient(sl.row % 2 == 0 ? odb::dbOrientType::R0
                                       : odb::dbOrientType::MX);
    sl.inst->setLocation(core_x0 + col_x[sl.col] + sl.x,
                         core_y0 + sl.row * row_h);
    sl.inst->setPlacementStatus(odb::dbPlacementStatus::FIRM);
  }

  // ---- pins: inputs on the left edge, outputs on the right -------------
  odb::dbTechLayer* layer = tech->findLayer(s.pin_layer_h.c_str());
  if (layer == nullptr) {
    Refuse("pin layer " + s.pin_layer_h + " not in the tech LEF");
  }
  const int pitch = static_cast<int>(s.pin_track_pitch_um * dbu);
  const int offset = static_cast<int>(s.pin_track_offset_um * dbu);
  auto place_edge = [&](const std::vector<dbBTerm*>& terms, int edge_x) {
    const int tracks = (die_h - offset) / pitch;
    if (static_cast<int>(terms.size()) > tracks) {
      Refuse(std::to_string(terms.size()) + " pins on one edge, " +
             std::to_string(tracks) + " tracks");
    }
    const double step = static_cast<double>(tracks) / terms.size();
    for (size_t i = 0; i < terms.size(); ++i) {
      int track = static_cast<int>(i * step + step / 2);
      Pin(terms[i], layer, edge_x, offset + track * pitch);
    }
  };
  place_edge(inputs_, 0);
  place_edge(outputs_, die_w);
  (void) vdd;
  (void) vss;
  return block_;
}

std::string F(double v) {
  char buf[32];
  std::snprintf(buf, sizeof buf, "%.4f", v);
  return buf;
}

void Table2(std::ostream& o, const char* kind, const std::string& tmpl,
            double value_ns) {
  o << "            " << kind << "(" << tmpl << ") {\n"
    << "                index_1 (\"0.009, 0.227\");\n"
    << "                index_2 (\"0.005, 0.500\");\n"
    << "                values (\"" << F(value_ns) << ", " << F(value_ns)
    << "\", \"" << F(value_ns) << ", " << F(value_ns) << "\");\n"
    << "            }\n";
}

}  // namespace

MergedWriteSpec ReadMergedWriteSpec(const std::string& path) {
  std::ifstream in(path);
  if (!in) {
    Refuse("cannot read " + path);
  }
  nlohmann::json j;
  try {
    in >> j;
  } catch (const std::exception& e) {
    Refuse(path + ": " + e.what());
  }
  MergedWriteSpec s;
  auto req = [&](const nlohmann::json& o, const char* key) -> const nlohmann::json& {
    if (!o.contains(key)) {
      Refuse(path + ": missing `" + key + "`");
    }
    return o.at(key);
  };
  if (req(j, "kind").get<std::string>() != "merged_write") {
    Refuse(path + ": kind is not merged_write");
  }
  s.module = req(j, "module").get<std::string>();
  s.clock = j.value("clock", s.clock);
  s.reset = j.value("reset", s.reset);
  s.ways = req(j, "ways").get<int>();
  const auto& wr = req(j, "write");
  s.write_valid = req(wr, "valid").get<std::string>();
  s.write_way_mask = req(wr, "way_mask").get<std::string>();
  const auto& fl = req(j, "flush");
  s.flush_valid = req(fl, "valid").get<std::string>();
  s.flush_way_mask = req(fl, "way_mask").get<std::string>();
  const auto& cf = req(j, "conflict");
  const auto& eq = req(cf, "equal");
  if (!eq.is_array() || eq.size() != 2) {
    Refuse(path + ": conflict.equal is two bus names");
  }
  s.conflict_equal_a = eq[0].get<std::string>();
  s.conflict_equal_b = eq[1].get<std::string>();
  s.conflict_zero = req(cf, "zero").get<std::string>();
  for (const auto& f : req(j, "fields")) {
    MergedField m;
    m.name = req(f, "name").get<std::string>();
    m.reg = req(f, "reg").get<std::string>();
    m.width = req(f, "width").get<int>();
    m.write = req(f, "write").get<std::string>();
    m.flush = f.value("flush", std::string());
    s.fields.push_back(m);
  }
  if (j.contains("names")) {
    const auto& n = j.at("names");
    s.out_valid = n.value("out_valid", s.out_valid);
    s.out_field = n.value("out_field", s.out_field);
    s.reg_valid = n.value("reg_valid", s.reg_valid);
    s.reg_field = n.value("reg_field", s.reg_field);
  }
  for (const auto& [kind, c] : req(j, "cells").items()) {
    CellRef r;
    r.master = req(c, "master").get<std::string>();
    for (const auto& p : req(c, "pins")) {
      r.pins.push_back(p.get<std::string>());
    }
    s.cells.emplace_back(kind, r);
  }
  s.max_fanout = j.value("max_fanout", s.max_fanout);
  s.margin_um = j.value("margin_um", s.margin_um);
  s.pin_layer_h = j.value("pin_layer_h", s.pin_layer_h);
  s.pin_track_offset_um = j.value("pin_track_offset_um", s.pin_track_offset_um);
  s.pin_track_pitch_um = j.value("pin_track_pitch_um", s.pin_track_pitch_um);
  return s;
}

dbBlock* GenerateMergedWrite(odb::dbDatabase* db, utl::Logger* /*logger*/,
                             const MergedWriteSpec& spec) {
  Builder b(db, spec);
  return b.Run();
}

void WriteMergedWriteLiberty(odb::dbBlock* block, const MergedWriteSpec& spec,
                             const std::string& path) {
  std::ofstream o(path);
  if (!o) {
    Refuse("cannot write " + path);
  }
  const std::string cell = spec.module;
  // A model: registered outputs, clock to Q through a flop and an
  // inverter; inputs set up through the compare, the enables and the mux.
  const double clk_q_ns = 0.045;
  const double setup_ns = 0.120;
  const double in_pf = 0.0012;
  const odb::Rect die = block->getDieArea();
  const double dbu = block->getDbUnitsPerMicron();
  // Buses by `name[i]`, in port order.
  std::map<std::string, int> width;
  std::map<std::string, bool> is_input;
  std::vector<std::string> order;
  for (dbBTerm* t : block->getBTerms()) {
    std::string n = t->getName();
    std::string base = n;
    int idx = 0;
    auto lb = n.rfind('[');
    if (lb != std::string::npos && n.back() == ']') {
      base = n.substr(0, lb);
      idx = std::stoi(n.substr(lb + 1)) + 1;
    }
    if (!width.count(base)) {
      order.push_back(base);
      is_input[base] = t->getIoType() == odb::dbIoType::INPUT;
    }
    width[base] = std::max(width[base], idx);
  }
  o << "library(" << cell << ") {\n"
    << "    delay_model : table_lookup;\n"
    << "    comment : \"structured_gen merged_write model\";\n"
    << "    time_unit : \"1ns\";\n"
    << "    voltage_unit : \"1V\";\n"
    << "    current_unit : \"1uA\";\n"
    << "    leakage_power_unit : \"1uW\";\n"
    << "    capacitive_load_unit (1,pf);\n"
    << "    pulling_resistance_unit : \"1kohm\";\n"
    << "    nom_process : 1;\n"
    << "    nom_temperature : 25.000;\n"
    << "    nom_voltage : 0.700;\n"
    << "    default_max_transition : 0.227;\n"
    << "    slew_lower_threshold_pct_fall : 20.000;\n"
    << "    slew_upper_threshold_pct_fall : 80.000;\n"
    << "    slew_lower_threshold_pct_rise : 20.000;\n"
    << "    slew_upper_threshold_pct_rise : 80.000;\n"
    << "    input_threshold_pct_fall : 50.000;\n"
    << "    input_threshold_pct_rise : 50.000;\n"
    << "    output_threshold_pct_fall : 50.000;\n"
    << "    output_threshold_pct_rise : 50.000;\n"
    << "    lu_table_template(" << cell << "_t) {\n"
    << "        variable_1 : input_net_transition;\n"
    << "        variable_2 : total_output_net_capacitance;\n"
    << "        index_1 (\"1000, 1001\");\n"
    << "        index_2 (\"1000, 1001\");\n"
    << "    }\n"
    << "    lu_table_template(" << cell << "_c) {\n"
    << "        variable_1 : related_pin_transition;\n"
    << "        variable_2 : constrained_pin_transition;\n"
    << "        index_1 (\"1000, 1001\");\n"
    << "        index_2 (\"1000, 1001\");\n"
    << "    }\n";
  std::set<int> widths;
  for (const auto& [b, w] : width) {
    if (w > 0) {
      widths.insert(w);
    }
  }
  for (int w : widths) {
    o << "    type (" << cell << "_bus_" << w << ") {\n"
      << "        base_type : array ;\n"
      << "        data_type : bit ;\n"
      << "        bit_width : " << w << ";\n"
      << "        bit_from : " << w - 1 << ";\n"
      << "        bit_to : 0 ;\n"
      << "        downto : true ;\n"
      << "    }\n";
  }
  o << "cell(" << cell << ") {\n"
    << "    area : " << F(die.dx() / dbu * (die.dy() / dbu)) << ";\n"
    << "    is_macro_cell : true;\n"
    << "    interface_timing : true;\n";
  for (const std::string& b : order) {
    const bool bus = width[b] > 0;
    const bool clk = b == spec.clock;
    o << "    " << (bus ? "bus" : "pin") << "(" << b << ") {\n";
    if (bus) {
      o << "        bus_type : " << cell << "_bus_" << width[b] << ";\n";
    }
    o << "        direction : " << (is_input[b] ? "input" : "output") << ";\n";
    if (clk) {
      o << "        capacitance : 0.0100;\n        clock : true;\n    }\n";
      continue;
    }
    if (is_input[b]) {
      o << "        capacitance : " << F(in_pf) << ";\n";
      if (b != spec.reset) {
        o << "        timing() {\n"
          << "            related_pin : " << spec.clock << ";\n"
          << "            timing_type : setup_rising ;\n";
        Table2(o, "rise_constraint", cell + "_c", setup_ns);
        Table2(o, "fall_constraint", cell + "_c", setup_ns);
        o << "        }\n";
      }
    } else {
      o << "        timing() {\n"
        << "            related_pin : " << spec.clock << ";\n"
        << "            timing_type : rising_edge ;\n";
      Table2(o, "cell_rise", cell + "_t", clk_q_ns);
      Table2(o, "cell_fall", cell + "_t", clk_q_ns);
      Table2(o, "rise_transition", cell + "_t", 0.02);
      Table2(o, "fall_transition", cell + "_t", 0.02);
      o << "        }\n";
    }
    o << "    }\n";
  }
  o << "}\n}\n";
}

}  // namespace structured_gen
