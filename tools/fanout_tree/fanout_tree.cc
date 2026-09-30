// fanout_tree: see fanout_tree.h.
#include "fanout_tree.h"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <functional>
#include <sstream>
#include <stdexcept>
#include <climits>
#include <cstdint>
#include <unordered_set>

#include "odb/db.h"

namespace fanout_tree {

using odb::dbBTerm;
using odb::dbInst;
using odb::dbITerm;
using odb::dbMaster;
using odb::dbNet;

// ---- liberty pin capacitances --------------------------------------------

namespace {

// Liberty as a stream of tokens: identifiers, punctuation, strings with
// their quotes dropped; comments skipped.
class Lexer {
 public:
  explicit Lexer(const std::string& text) : s_(text) {}
  bool Next(std::string& tok) {
    for (;;) {
      while (i_ < s_.size() && (std::isspace(static_cast<unsigned char>(s_[i_])) ||
                                s_[i_] == '\\')) {
        ++i_;
      }
      if (i_ + 1 < s_.size() && s_[i_] == '/' && s_[i_ + 1] == '*') {
        size_t e = s_.find("*/", i_ + 2);
        i_ = e == std::string::npos ? s_.size() : e + 2;
        continue;
      }
      break;
    }
    if (i_ >= s_.size()) {
      return false;
    }
    char c = s_[i_];
    if (c == '"') {
      size_t e = s_.find('"', i_ + 1);
      if (e == std::string::npos) {
        e = s_.size();
      }
      tok = s_.substr(i_ + 1, e - i_ - 1);
      i_ = e + 1;
      return true;
    }
    if (std::string("(){}:;,").find(c) != std::string::npos) {
      tok = std::string(1, c);
      ++i_;
      return true;
    }
    size_t b = i_;
    while (i_ < s_.size() && !std::isspace(static_cast<unsigned char>(s_[i_])) &&
           std::string("(){}:;,\"").find(s_[i_]) == std::string::npos) {
      ++i_;
    }
    tok = s_.substr(b, i_ - b);
    return true;
  }

 private:
  const std::string& s_;
  size_t i_ = 0;
};

std::string StripBit(const std::string& pin) {
  size_t b = pin.find('[');
  return b == std::string::npos ? pin : pin.substr(0, b);
}

}  // namespace

int PinCaps::ReadLiberty(const std::string& path) {
  std::ifstream in(path);
  if (!in) {
    throw std::runtime_error("cannot read liberty " + path);
  }
  std::stringstream ss;
  ss << in.rdbuf();
  const std::string text = ss.str();
  Lexer lex(text);
  // A group is `kind ( name ) {`; the stack holds each open group's kind
  // and name so a `capacitance` is credited to the pin or bus it sits in.
  struct Group {
    std::string kind, name;
  };
  std::vector<Group> stack;
  std::vector<std::string> window;  // the last few tokens
  std::string tok;
  int cells = 0;
  std::string cell;
  while (lex.Next(tok)) {
    if (tok == "{") {
      // window: kind ( name ) -- or kind ( ) for anonymous groups
      Group g;
      size_t n = window.size();
      if (n >= 4 && window[n - 1] == ")" && window[n - 3] == "(") {
        g.kind = window[n - 4];
        g.name = window[n - 2];
      } else if (n >= 3 && window[n - 1] == ")" && window[n - 2] == "(") {
        g.kind = window[n - 3];
      }
      if (g.kind == "cell") {
        cell = g.name;
        ++cells;
      }
      stack.push_back(g);
      window.clear();
      continue;
    }
    if (tok == "}") {
      if (!stack.empty()) {
        if (stack.back().kind == "cell") {
          cell.clear();
        }
        stack.pop_back();
      }
      window.clear();
      continue;
    }
    if (tok == ";") {
      size_t n = window.size();
      if (n >= 3 && window[n - 3] == "capacitance" && window[n - 2] == ":" &&
          !stack.empty() && !cell.empty() &&
          (stack.back().kind == "pin" || stack.back().kind == "bus")) {
        caps_[cell][stack.back().name] = std::atof(window[n - 1].c_str());
      }
      window.clear();
      continue;
    }
    window.push_back(tok);
    if (window.size() > 8) {
      window.erase(window.begin());
    }
  }
  return cells;
}

double PinCaps::Get(const std::string& master, const std::string& pin,
                    double fallback) const {
  auto c = caps_.find(master);
  if (c == caps_.end()) {
    return fallback;
  }
  auto p = c->second.find(pin);
  if (p == c->second.end()) {
    p = c->second.find(StripBit(pin));
  }
  return p == c->second.end() ? fallback : p->second;
}

// ---- the rebuilder ---------------------------------------------------------

namespace {

dbITerm* DriverITerm(dbNet* net) {
  for (dbITerm* it : net->getITerms()) {
    if (it->getIoType() == odb::dbIoType::OUTPUT) {
      return it;
    }
  }
  return nullptr;
}

dbBTerm* DriverBTerm(dbNet* net) {
  for (dbBTerm* bt : net->getBTerms()) {
    if (bt->getIoType() == odb::dbIoType::INPUT) {
      return bt;
    }
  }
  return nullptr;
}

bool IsClockPin(dbITerm* it) {
  if (it->getSigType() == odb::dbSigType::CLOCK) {
    return true;
  }
  std::string n = it->getMTerm()->getName();
  std::transform(n.begin(), n.end(), n.begin(), ::tolower);
  return n == "clk" || n.find("clk") != std::string::npos ||
         n.find("clock") != std::string::npos;
}

std::string FullName(dbITerm* it) {
  return it->getInst()->getName() + "/" + it->getMTerm()->getName();
}

}  // namespace

double DriveOf(const std::string& name) {
  size_t x = name.find('x');
  while (x != std::string::npos && x + 1 < name.size() &&
         !std::isdigit(static_cast<unsigned char>(name[x + 1])) && name[x + 1] != 'p') {
    x = name.find('x', x + 1);
  }
  if (x == std::string::npos || x + 1 >= name.size()) {
    return 1.0;
  }
  if (name[x + 1] == 'p') {
    return std::max(std::atof(("0." + name.substr(x + 2)).c_str()), 0.1);
  }
  return std::max(std::atof(name.c_str() + x + 1), 0.1);
}

Rebuilder::Rebuilder(odb::dbBlock* block, std::vector<Buffer> buffers,
                     const PinCaps& caps, Options opt)
    : block_(block), buffers_(std::move(buffers)), caps_(caps), opt_(opt) {
  if (buffers_.empty()) {
    throw std::runtime_error("fanout_tree: no buffer cells given");
  }
  std::sort(buffers_.begin(), buffers_.end(),
            [](const Buffer& a, const Buffer& b) { return a.drive < b.drive; });
}

bool Rebuilder::IsBuffer(dbMaster* m) const {
  for (const auto& b : buffers_) {
    if (b.master == m) {
      return true;
    }
  }
  return false;
}

const Buffer& Rebuilder::Pick(double load_ff) const {
  const double need = load_ff / opt_.ff_per_drive;
  for (const auto& b : buffers_) {
    if (b.drive >= need) {
      return b;
    }
  }
  return buffers_.back();
}

double Rebuilder::SinkCap(dbITerm* it) const {
  return caps_.Get(it->getInst()->getMaster()->getName(),
                   it->getMTerm()->getName(), opt_.default_pin_ff);
}

void Rebuilder::RebuildNet(dbNet* root) {
  if (root->isDoNotTouch() || root->getSigType() != odb::dbSigType::SIGNAL) {
    return;
  }
  dbITerm* drv = DriverITerm(root);
  dbBTerm* drv_bt = drv ? nullptr : DriverBTerm(root);
  if (drv == nullptr && drv_bt == nullptr) {
    return;
  }
  // The tree behind the net: sinks, the buffers to remove, the inner
  // nets they drive, the depth reached.
  std::vector<dbITerm*> sinks;
  std::vector<dbInst*> bufs;
  std::vector<dbNet*> inner;
  int depth_max = 0;
  bool refuse = false;
  std::function<void(dbNet*, int)> walk = [&](dbNet* net, int depth) {
    depth_max = std::max(depth_max, depth);
    for (dbBTerm* bt : net->getBTerms()) {
      if (net != root && bt->getIoType() != odb::dbIoType::INPUT) {
        refuse = true;  // a port on an inner net: leave the tree alone
      }
    }
    for (dbITerm* it : net->getITerms()) {
      if (it->getIoType() == odb::dbIoType::OUTPUT) {
        continue;
      }
      if (it->getIoType() != odb::dbIoType::INPUT) {
        refuse = true;
        continue;
      }
      if (IsClockPin(it)) {
        refuse = true;
        continue;
      }
      dbInst* inst = it->getInst();
      if (IsBuffer(inst->getMaster()) && !inst->isDoNotTouch() &&
          !inst->getPlacementStatus().isFixed()) {
        dbITerm* out = nullptr;
        for (dbITerm* o : inst->getITerms()) {
          if (o->getIoType() == odb::dbIoType::OUTPUT) {
            out = o;
          }
        }
        dbNet* on = out ? out->getNet() : nullptr;
        if (on == nullptr || on->isDoNotTouch()) {
          refuse = true;
          continue;
        }
        bufs.push_back(inst);
        inner.push_back(on);
        walk(on, depth + 1);
      } else {
        sinks.push_back(it);
      }
    }
  };
  walk(root, 0);
  if (refuse) {
    return;
  }
  if (static_cast<int>(sinks.size()) < opt_.min_sinks) {
    return;
  }
  double root_load = opt_.max_load_ff;
  if (drv != nullptr && opt_.root_ff_per_drive > 0) {
    root_load = std::min(root_load,
                         DriveOf(drv->getInst()->getMaster()->getName()) *
                             opt_.root_ff_per_drive);
  }
  double total = 0;
  for (dbITerm* s : sinks) {
    total += SinkCap(s);
  }
  if (bufs.empty() && static_cast<int>(sinks.size()) <= opt_.max_fanout &&
      total <= root_load) {
    return;
  }

  // Witnesses first, while the old tree still stands.
  const std::string dname = drv ? drv->getInst()->getName() : drv_bt->getName();
  const std::string dpin = drv ? drv->getMTerm()->getName() : "";
  for (dbITerm* s : sinks) {
    witnesses_.push_back(Witness{s, dname, dpin});
  }

  // Take the old tree down.
  for (dbITerm* s : sinks) {
    s->disconnect();
  }
  for (dbInst* b : bufs) {
    dbInst::destroy(b);
  }
  for (dbNet* n : inner) {
    dbNet::destroy(n);
  }
  stats_.buffers_removed += static_cast<int>(bufs.size());
  stats_.max_depth_before = std::max(stats_.max_depth_before, depth_max);

  // Build the new one, bottom-up. With a placer and every sink placed,
  // a level's items are grouped by recursive bisection of their
  // positions, each group's load its pins plus its half-perimeter at
  // wire_ff_per_um, and each buffer is placed as it is made, so the
  // level above groups real positions. Otherwise in instance-name order.
  std::sort(sinks.begin(), sinks.end(), [](dbITerm* a, dbITerm* b) {
    return a->getInst()->getName() < b->getInst()->getName();
  });
  struct Item {
    dbITerm* it;
    double cap;
    int x = 0, y = 0;
    bool placed = false;
  };
  auto locate = [](Item& i) {
    dbInst* inst = i.it->getInst();
    i.placed = inst->getPlacementStatus().isPlaced();
    if (i.placed) {
      odb::Rect b = inst->getBBox()->getBox();
      i.x = (b.xMin() + b.xMax()) / 2;
      i.y = (b.yMin() + b.yMax()) / 2;
    }
  };
  std::vector<Item> level;
  bool spatial = static_cast<bool>(place_);
  for (dbITerm* s : sinks) {
    Item i{s, SinkCap(s)};
    locate(i);
    spatial = spatial && i.placed;
    level.push_back(i);
  }
  const double um = block_->getDbUnitsPerMicron();
  auto load_of = [&](const std::vector<Item>& v, size_t lo, size_t hi) {
    double l = 0;
    int x0 = INT32_MAX, x1 = INT32_MIN, y0 = INT32_MAX, y1 = INT32_MIN;
    for (size_t k = lo; k < hi; ++k) {
      l += v[k].cap;
      x0 = std::min(x0, v[k].x);
      x1 = std::max(x1, v[k].x);
      y0 = std::min(y0, v[k].y);
      y1 = std::max(y1, v[k].y);
    }
    if (spatial && hi > lo) {
      l += ((x1 - x0) + (y1 - y0)) / um * opt_.wire_ff_per_um;
    }
    return l;
  };
  int depth = 0;
  auto fits = [&](const std::vector<Item>& v) {
    return static_cast<int>(v.size()) <= opt_.max_fanout &&
           load_of(v, 0, v.size()) <= root_load;
  };
  // Groups as [lo, hi) ranges of `v`, reordered in place.
  std::function<void(std::vector<Item>&, size_t, size_t,
                     std::vector<std::pair<size_t, size_t>>&)>
      bisect = [&](std::vector<Item>& v, size_t lo, size_t hi,
                   std::vector<std::pair<size_t, size_t>>& out) {
        if (hi - lo <= 1 || (static_cast<int>(hi - lo) <= opt_.max_fanout &&
                             load_of(v, lo, hi) <= opt_.max_load_ff)) {
          out.emplace_back(lo, hi);
          return;
        }
        int x0 = INT32_MAX, x1 = INT32_MIN, y0 = INT32_MAX, y1 = INT32_MIN;
        for (size_t k = lo; k < hi; ++k) {
          x0 = std::min(x0, v[k].x);
          x1 = std::max(x1, v[k].x);
          y0 = std::min(y0, v[k].y);
          y1 = std::max(y1, v[k].y);
        }
        const bool by_x = (x1 - x0) >= (y1 - y0);
        size_t mid = lo + (hi - lo) / 2;
        std::nth_element(v.begin() + lo, v.begin() + mid, v.begin() + hi,
                         [&](const Item& a, const Item& b) {
                           return by_x ? a.x < b.x : a.y < b.y;
                         });
        bisect(v, lo, mid, out);
        bisect(v, mid, hi, out);
      };
  while (!fits(level)) {
    std::vector<std::pair<size_t, size_t>> groups;
    if (spatial) {
      bisect(level, 0, level.size(), groups);
    } else {
      size_t lo = 0;
      double load = 0;
      for (size_t k = 0; k < level.size(); ++k) {
        if (k > lo && (static_cast<int>(k - lo) >= opt_.max_fanout ||
                       load + level[k].cap > opt_.max_load_ff)) {
          groups.emplace_back(lo, k);
          lo = k;
          load = 0;
        }
        load += level[k].cap;
      }
      groups.emplace_back(lo, level.size());
    }
    std::vector<Item> next;
    for (auto [lo, hi] : groups) {
      const Buffer& b = Pick(load_of(level, lo, hi));
      const std::string id = std::to_string(serial_++);
      dbNet* n = dbNet::create(block_, ("fot_n" + id).c_str());
      dbInst* inst = dbInst::create(block_, b.master, ("fot_b" + id).c_str());
      if (n == nullptr || inst == nullptr) {
        throw std::runtime_error("fanout_tree: name clash on fot_" + id);
      }
      inst->findITerm(b.out.c_str())->connect(n);
      long sx = 0, sy = 0;
      for (size_t k = lo; k < hi; ++k) {
        level[k].it->connect(n);
        sx += level[k].x;
        sy += level[k].y;
      }
      Item up{inst->findITerm(b.in.c_str()), caps_.Get(b.master->getName(), b.in, 1.0)};
      if (spatial) {
        place_(inst, static_cast<int>(sx / static_cast<long>(hi - lo)),
               static_cast<int>(sy / static_cast<long>(hi - lo)));
        locate(up);
        spatial = up.placed;
      }
      next.push_back(up);
      ++stats_.buffers_added;
    }
    ++depth;
    if (next.size() >= level.size()) {
      // Every group is a single pin over the load limit; buffering again
      // gains nothing. Drive what is left from the root.
      level = next;
      break;
    }
    level = next;
  }
  // The buffers the root drives go beside it, not among their sinks: the
  // long wire is then driven by a buffer sized for it (its load counts
  // the half-perimeter) rather than by the root, which may be an x1
  // inverter or a port.
  if (spatial && depth > 0) {
    int dx = 0, dy = 0;
    bool have = false;
    if (drv != nullptr && drv->getInst()->getPlacementStatus().isPlaced()) {
      odb::Rect b = drv->getInst()->getBBox()->getBox();
      dx = (b.xMin() + b.xMax()) / 2;
      dy = (b.yMin() + b.yMax()) / 2;
      have = true;
    } else if (drv_bt != nullptr) {
      for (odb::dbBPin* bp : drv_bt->getBPins()) {
        odb::Rect b = bp->getBBox();
        dx = (b.xMin() + b.xMax()) / 2;
        dy = (b.yMin() + b.yMax()) / 2;
        have = true;
      }
    }
    if (have) {
      for (const auto& i : level) {
        if (i.it->getInst()->getName().rfind("fot_b", 0) == 0) {
          place_(i.it->getInst(), dx, dy);
        }
      }
    }
  }
  for (const auto& i : level) {
    i.it->connect(root);
  }
  stats_.max_depth_after = std::max(stats_.max_depth_after, depth);
  stats_.sinks += static_cast<long>(sinks.size());
  ++stats_.nets_rebuilt;
}

Stats Rebuilder::Run() {
  // Roots are nets not driven by a removable buffer; collected before any
  // change, and only inner (buffer-driven) nets are ever destroyed.
  std::vector<dbNet*> roots;
  for (dbNet* n : block_->getNets()) {
    dbITerm* d = DriverITerm(n);
    if (d != nullptr && IsBuffer(d->getInst()->getMaster()) &&
        !d->getInst()->isDoNotTouch() &&
        !d->getInst()->getPlacementStatus().isFixed()) {
      continue;
    }
    roots.push_back(n);
  }
  for (dbNet* n : roots) {
    RebuildNet(n);
  }
  return stats_;
}

std::vector<std::string> Rebuilder::Check() const {
  std::vector<std::string> problems;
  for (const auto& w : witnesses_) {
    dbNet* net = w.sink->getNet();
    bool ok = false;
    for (int step = 0; step < 64 && net != nullptr; ++step) {
      dbITerm* d = DriverITerm(net);
      if (d == nullptr) {
        dbBTerm* bt = DriverBTerm(net);
        ok = bt != nullptr && w.driver_pin.empty() && bt->getName() == w.driver_inst;
        break;
      }
      dbInst* inst = d->getInst();
      if (IsBuffer(inst->getMaster()) &&
          inst->getName().rfind("fot_b", 0) == 0) {
        dbITerm* in = nullptr;
        for (dbITerm* it : inst->getITerms()) {
          if (it->getIoType() == odb::dbIoType::INPUT) {
            in = it;
          }
        }
        net = in ? in->getNet() : nullptr;
        continue;
      }
      ok = inst->getName() == w.driver_inst &&
           d->getMTerm()->getName() == w.driver_pin;
      break;
    }
    if (!ok) {
      problems.push_back(FullName(w.sink) + " no longer reaches " + w.driver_inst +
                         (w.driver_pin.empty() ? "" : "/" + w.driver_pin));
    }
  }
  return problems;
}

}  // namespace fanout_tree
