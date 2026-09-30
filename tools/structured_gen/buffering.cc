// structured_gen: see buffering.h.
#include "buffering.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <map>
#include <stdexcept>
#include <vector>

#include "odb/db.h"
#include "tools/fanout_tree/fanout_tree.h"

namespace structured_gen {

namespace {

// Free sites per row, from every placed instance's footprint.
class Occupancy {
 public:
  explicit Occupancy(odb::dbBlock* block) {
    for (odb::dbRow* row : block->getRows()) {
      rows_.push_back(row);
    }
    std::sort(rows_.begin(), rows_.end(), [](odb::dbRow* a, odb::dbRow* b) {
      return a->getOrigin().y() < b->getOrigin().y();
    });
    if (rows_.empty()) {
      throw std::runtime_error("structured_gen: block has no rows to buffer into");
    }
    site_w_ = static_cast<int>(rows_[0]->getSite()->getWidth());
    row_h_ = static_cast<int>(rows_[0]->getSite()->getHeight());
    y0_ = rows_[0]->getOrigin().y();
    x0_ = rows_[0]->getOrigin().x();
    sites_ = rows_[0]->getSiteCount();
    used_.assign(rows_.size(), std::vector<char>(sites_, 0));
    for (odb::dbInst* inst : block->getInsts()) {
      if (inst->getPlacementStatus().isPlaced()) {
        Mark(inst);
      }
    }
  }
  void Mark(odb::dbInst* inst, char v = 1) {
    odb::Rect b = inst->getBBox()->getBox();
    int r0 = (b.yMin() - y0_) / row_h_;
    int r1 = (b.yMax() - 1 - y0_) / row_h_;
    int s0 = (b.xMin() - x0_) / site_w_;
    int s1 = (b.xMax() - 1 - x0_) / site_w_;
    for (int r = std::max(r0, 0); r <= r1 && r < static_cast<int>(rows_.size()); ++r) {
      for (int s = std::max(s0, 0); s <= s1 && s < sites_; ++s) {
        used_[r][s] = v;
      }
    }
  }
  // The free span of `w` sites nearest (x, y), searching `rows` rows
  // either side and the whole row width; false if none.
  bool Find(int x, int y, int w, int rows, int& row_out, int& site_out) const {
    int r_target = std::clamp((y - y0_) / row_h_, 0, static_cast<int>(rows_.size()) - 1);
    int s_target = std::clamp((x - x0_) / site_w_, 0, sites_ - 1);
    long best = -1;
    for (int dr = 0; dr <= rows; ++dr) {
      for (int sign : {1, -1}) {
        if (dr == 0 && sign < 0) {
          continue;
        }
        int r = r_target + sign * dr;
        if (r < 0 || r >= static_cast<int>(rows_.size())) {
          continue;
        }
        const long row_cost = static_cast<long>(dr) * row_h_;
        if (best >= 0 && row_cost >= best) {
          continue;
        }
        // Scan outward from the target site for a free run of w.
        for (int ds = 0; ds < sites_; ++ds) {
          const long cost = row_cost + static_cast<long>(ds) * site_w_;
          if (best >= 0 && cost >= best) {
            break;
          }
          for (int ss : {1, -1}) {
            int s = s_target + ss * ds;
            if (s < 0 || s + w > sites_) {
              continue;
            }
            bool free = true;
            for (int k = 0; k < w && free; ++k) {
              free = !used_[r][s + k];
            }
            if (free) {
              best = cost;
              row_out = r;
              site_out = s;
              break;
            }
          }
        }
      }
    }
    return best >= 0;
  }
  odb::dbRow* Row(int r) const { return rows_[r]; }
  int X(int s) const { return x0_ + s * site_w_; }
  int Y(int r) const { return y0_ + r * row_h_; }
  int SiteW() const { return site_w_; }

 private:
  std::vector<odb::dbRow*> rows_;
  std::vector<std::vector<char>> used_;
  int site_w_ = 1, row_h_ = 1, x0_ = 0, y0_ = 0, sites_ = 0;
};

}  // namespace

BufferResult BufferWideNets(odb::dbBlock* block, const BufferSpec& spec) {
  BufferResult res;
  if (!spec.enabled()) {
    return res;
  }
  odb::dbDatabase* db = block->getDb();
  std::vector<fanout_tree::Buffer> buffers;
  for (const auto& name : spec.cells) {
    fanout_tree::Buffer b;
    b.master = db->findMaster(name.c_str());
    if (b.master == nullptr) {
      throw std::runtime_error("structured_gen: buffer cell not in the loaded LEF: " + name);
    }
    b.drive = fanout_tree::DriveOf(name);
    buffers.push_back(b);
  }
  fanout_tree::PinCaps caps;  // no liberty here: every pin is input_load_ff
  fanout_tree::Options opt;
  opt.max_fanout = spec.max_fanout;
  opt.max_load_ff = spec.max_load_ff;
  opt.default_pin_ff = spec.input_load_ff;
  opt.root_ff_per_drive = spec.root_ff_per_drive;
  for (const auto& b : buffers) {
    // A buffer's input: one std cell input per unit of the first stage,
    // which on asap7's two-stage buffers is about a quarter of its drive.
    caps.Set(b.master->getName(), b.in, spec.input_load_ff * std::max(1.0, b.drive / 4));
  }
  // Each buffer goes on the free sites nearest the centroid of what it
  // drives as fanout_tree makes it, so the level above sees where it is.
  Occupancy occ(block);
  const double dbu = block->getDbUnitsPerMicron();
  fanout_tree::Rebuilder rb(block, buffers, caps, opt);
  rb.SetPlacer([&](odb::dbInst* inst, int cx, int cy) {
    const int w = static_cast<int>((inst->getMaster()->getWidth() + occ.SiteW() - 1) /
                                   occ.SiteW());
    if (inst->getPlacementStatus().isPlaced()) {
      occ.Mark(inst, 0);  // moved: its old sites are free again
      inst->setPlacementStatus(odb::dbPlacementStatus::PLACED);  // FIRM cannot move
    }
    int r = 0, s = 0;
    if (!occ.Find(cx, cy, w, 64, r, s)) {
      throw std::runtime_error("structured_gen: no free site for " + inst->getName() +
                               " within 64 rows: raise service_sites");
    }
    odb::dbRow* row = occ.Row(r);
    inst->setOrient(row->getOrient());
    inst->setLocation(occ.X(s), occ.Y(r));
    inst->setPlacementStatus(odb::dbPlacementStatus::FIRM);
    occ.Mark(inst);
    const double d = (std::abs(occ.X(s) - cx) + std::abs(occ.Y(r) - cy)) / dbu;
    res.max_displacement_um = std::max(res.max_displacement_um, d);
  });
  fanout_tree::Stats st = rb.Run();
  auto problems = rb.Check();
  if (!problems.empty()) {
    throw std::runtime_error("structured_gen: buffering broke a connection: " + problems[0]);
  }
  res.nets = st.nets_rebuilt;
  res.buffers = st.buffers_added;

  // Repeaters on every long two-pin net: the port to its first buffer,
  // a tree's root buffer to the port, a bitline's root to its pin. A
  // net longer than max_wire_um is cut into equal spans along an L
  // (horizontal first), one buffer per cut, each placed like the rest.
  if (spec.max_wire_um > 0) {
    const fanout_tree::Buffer* rep = nullptr;
    for (const auto& b : buffers) {
      if (rep == nullptr || std::abs(b.drive - spec.repeater_drive) <
                                std::abs(rep->drive - spec.repeater_drive)) {
        rep = &b;
      }
    }
    auto pos = [](odb::dbITerm* it, odb::dbBTerm* bt, int& x, int& y) {
      odb::Rect b;
      if (it != nullptr) {
        if (!it->getInst()->getPlacementStatus().isPlaced()) {
          return false;
        }
        b = it->getInst()->getBBox()->getBox();
      } else {
        bool any = false;
        for (odb::dbBPin* bp : bt->getBPins()) {
          b = bp->getBBox();
          any = true;
        }
        if (!any) {
          return false;
        }
      }
      x = (b.xMin() + b.xMax()) / 2;
      y = (b.yMin() + b.yMax()) / 2;
      return true;
    };
    std::vector<odb::dbNet*> nets(block->getNets().begin(), block->getNets().end());
    long serial = 0;
    for (odb::dbNet* net : nets) {
      if (net->getSigType() != odb::dbSigType::SIGNAL) {
        continue;
      }
      odb::dbITerm *di = nullptr, *si = nullptr;
      odb::dbBTerm *db_ = nullptr, *sb = nullptr;
      int nd = 0, ns = 0;
      for (odb::dbITerm* it : net->getITerms()) {
        if (it->getIoType() == odb::dbIoType::OUTPUT) {
          di = it;
          ++nd;
        } else {
          si = it;
          ++ns;
        }
      }
      for (odb::dbBTerm* bt : net->getBTerms()) {
        if (bt->getIoType() == odb::dbIoType::INPUT) {
          db_ = bt;
          ++nd;
        } else {
          sb = bt;
          ++ns;
        }
      }
      if (nd != 1 || ns != 1 || (si != nullptr && si->getSigType() == odb::dbSigType::CLOCK)) {
        continue;
      }
      int x0, y0, x1, y1;
      if (!pos(di, db_, x0, y0) || !pos(si, sb, x1, y1)) {
        continue;
      }
      const double len_um = (std::abs(x1 - x0) + std::abs(y1 - y0)) / dbu;
      const int cuts = static_cast<int>(std::ceil(len_um / spec.max_wire_um)) - 1;
      if (cuts <= 0) {
        continue;
      }
      // The chain runs driver -> repeaters -> sink. A port keeps its own
      // net, so for an output port the driver moves onto a new first
      // net and the last repeater drives the port's; otherwise the sink
      // moves onto the last repeater's net.
      odb::dbNet* first = net;
      if (sb != nullptr) {
        if (di == nullptr) {
          continue;  // port to port: nothing to place between them
        }
        first = odb::dbNet::create(block, ("rep_n" + std::to_string(serial++)).c_str());
        di->disconnect();
        di->connect(first);
      } else {
        si->disconnect();
      }
      odb::dbNet* cur = first;
      const long total = std::abs(x1 - x0) + std::abs(y1 - y0);
      for (int k = 1; k <= cuts; ++k) {
        long along = total * k / (cuts + 1);
        int px, py;
        if (along <= std::abs(x1 - x0)) {
          px = x0 + static_cast<int>(x1 > x0 ? along : -along);
          py = y0;
        } else {
          px = x1;
          long up = along - std::abs(x1 - x0);
          py = y0 + static_cast<int>(y1 > y0 ? up : -up);
        }
        const std::string id = std::to_string(serial++);
        odb::dbInst* r = odb::dbInst::create(block, rep->master, ("rep_b" + id).c_str());
        odb::dbNet* out = k == cuts && sb != nullptr
                              ? net
                              : odb::dbNet::create(block, ("rep_n" + id).c_str());
        r->findITerm(rep->in.c_str())->connect(cur);
        r->findITerm(rep->out.c_str())->connect(out);
        const int w = static_cast<int>((r->getMaster()->getWidth() + occ.SiteW() - 1) /
                                       occ.SiteW());
        int row = 0, site = 0;
        if (!occ.Find(px, py, w, 64, row, site)) {
          throw std::runtime_error("structured_gen: no free site for repeater " + r->getName());
        }
        r->setOrient(occ.Row(row)->getOrient());
        r->setLocation(occ.X(site), occ.Y(row));
        r->setPlacementStatus(odb::dbPlacementStatus::FIRM);
        occ.Mark(r);
        cur = out;
        ++res.repeaters;
      }
      if (si != nullptr) {
        si->connect(cur);
      }
    }
  }
  for (odb::dbInst* inst : block->getInsts()) {
    if (!inst->getPlacementStatus().isPlaced()) {
      throw std::runtime_error("structured_gen: " + inst->getName() + " left unplaced");
    }
  }
  return res;
}

}  // namespace structured_gen
