// ABC's shape against the real asap7 LEF: an inverter drives a chain of
// five BUFx2, each driving nine sinks and the next buffer, the last ten.
// Rebuilt with at most 8 pins per driver, every sink still reaches the
// inverter through buffers only, no sink is more than two buffers deep,
// none of the chain is left, and a sink moved to another driver is
// caught by the check.
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "fanout_tree.h"
#include "odb/db.h"
#include "odb/lefin.h"
#include "utl/Logger.h"

#define CHECK(cond)                                                       \
  do {                                                                    \
    if (!(cond)) {                                                        \
      std::cerr << __FILE__ << ":" << __LINE__ << ": CHECK failed: " #cond \
                << "\n";                                                  \
      return 1;                                                           \
    }                                                                     \
  } while (0)

namespace {

int Depth(odb::dbITerm* sink, const std::string& root_inst) {
  odb::dbNet* net = sink->getNet();
  for (int d = 0; d < 64 && net != nullptr; ++d) {
    odb::dbITerm* drv = nullptr;
    for (odb::dbITerm* it : net->getITerms()) {
      if (it->getIoType() == odb::dbIoType::OUTPUT) {
        drv = it;
      }
    }
    if (drv == nullptr) {
      return -1;
    }
    if (drv->getInst()->getName() == root_inst) {
      return d;
    }
    net = drv->getInst()->findITerm("A")->getNet();
  }
  return -1;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 3) {
    std::cerr << "usage: fanout_tree_test TECH.lef CELLS.lef\n";
    return 2;
  }
  const char* srcdir = std::getenv("TEST_SRCDIR");
  auto runfile = [&](const char* rel) {
    return srcdir ? std::string(srcdir) + "/" + rel : std::string(rel);
  };
  const char* tmp = std::getenv("TEST_TMPDIR");
  const std::string dir = tmp ? tmp : ".";

  // Liberty pin capacitances: a plain pin, a bus, a cell-level
  // capacitance that is not a pin's, comments and quotes.
  {
    std::ofstream f(dir + "/t.lib");
    f << "library(t) { /* capacitance : 9; */\n"
         "  cell (\"BUFx2_ASAP7_75t_R\") { area : 1;\n"
         "    pin (A) { direction : input; capacitance : 0.577; "
         "rise_capacitance : 0.6; }\n"
         "    pin (Y) { direction : output; max_capacitance : 46; } }\n"
         "  cell (rf) { bus (addr) { bus_type : a6; capacitance : 19.8; }\n"
         "    pin (wen) { capacitance : 38.4; } } }\n";
  }
  fanout_tree::PinCaps caps;
  CHECK(caps.ReadLiberty(dir + "/t.lib") == 2);
  CHECK(caps.Get("BUFx2_ASAP7_75t_R", "A", -1) == 0.577);
  CHECK(caps.Get("BUFx2_ASAP7_75t_R", "Y", -1) == -1);
  CHECK(caps.Get("rf", "addr[5]", -1) == 19.8);
  CHECK(caps.Get("rf", "wen", -1) == 38.4);
  CHECK(caps.Get("nope", "A", 0.6) == 0.6);

  utl::Logger logger;
  odb::dbDatabase* db = odb::dbDatabase::create();
  db->setLogger(&logger);
  odb::lefin reader(db, &logger, false);
  odb::dbTech* tech = reader.createTech("asap7", runfile(argv[1]).c_str());
  CHECK(tech != nullptr);
  CHECK(reader.createLib(tech, "asap7sc7p5t", runfile(argv[2]).c_str()) != nullptr);
  odb::dbChip* chip = odb::dbChip::create(db, tech, "top");
  odb::dbBlock* block = odb::dbBlock::create(chip, "top");
  odb::dbMaster* inv = db->findMaster("INVx1_ASAP7_75t_R");
  odb::dbMaster* buf2 = db->findMaster("BUFx2_ASAP7_75t_R");
  odb::dbMaster* and2 = db->findMaster("AND2x2_ASAP7_75t_R");
  CHECK(inv && buf2 && and2);

  odb::dbNet* in = odb::dbNet::create(block, "in");
  odb::dbBTerm::create(in, "in")->setIoType(odb::dbIoType::INPUT);
  odb::dbNet* root = odb::dbNet::create(block, "root");
  odb::dbInst* drv = odb::dbInst::create(block, inv, "drv");
  drv->findITerm("A")->connect(in);
  drv->findITerm("Y")->connect(root);
  std::vector<odb::dbITerm*> sinks;
  odb::dbNet* net = root;
  int k = 0;
  for (int stage = 0; stage < 5; ++stage) {
    for (int s = 0; s < 9; ++s, ++k) {
      odb::dbInst* g = odb::dbInst::create(block, and2, ("s" + std::to_string(k)).c_str());
      g->findITerm("A")->connect(net);
      g->findITerm("B")->connect(in);
      sinks.push_back(g->findITerm("A"));
    }
    odb::dbNet* next = odb::dbNet::create(block, ("c" + std::to_string(stage)).c_str());
    odb::dbInst* b = odb::dbInst::create(block, buf2, ("abc" + std::to_string(stage)).c_str());
    b->findITerm("A")->connect(net);
    b->findITerm("Y")->connect(next);
    net = next;
  }
  for (int s = 0; s < 10; ++s, ++k) {
    odb::dbInst* g = odb::dbInst::create(block, and2, ("s" + std::to_string(k)).c_str());
    g->findITerm("A")->connect(net);
    g->findITerm("B")->connect(in);
    sinks.push_back(g->findITerm("A"));
  }
  CHECK(Depth(sinks.back(), "drv") == 5);

  std::vector<fanout_tree::Buffer> buffers;
  for (const char* n : {"BUFx2_ASAP7_75t_R", "BUFx4_ASAP7_75t_R", "BUFx8_ASAP7_75t_R"}) {
    fanout_tree::Buffer b;
    b.master = db->findMaster(n);
    CHECK(b.master != nullptr);
    b.drive = std::string(n).find("x2") != std::string::npos ? 2
              : std::string(n).find("x4") != std::string::npos ? 4 : 8;
    buffers.push_back(b);
  }
  fanout_tree::Options opt;
  opt.max_fanout = 8;
  fanout_tree::Rebuilder rb(block, buffers, caps, opt);
  fanout_tree::Stats st = rb.Run();
  CHECK(rb.Check().empty());
  CHECK(st.nets_rebuilt == 2);  // the chain, and `in`, which feeds every B pin
  CHECK(st.buffers_removed == 5);
  CHECK(st.max_depth_before == 5);
  CHECK(st.max_depth_after <= 2);
  for (int s = 0; s < 5; ++s) {
    CHECK(block->findInst(("abc" + std::to_string(s)).c_str()) == nullptr);
  }
  for (auto* s : sinks) {
    int d = Depth(s, "drv");
    CHECK(d >= 1 && d <= 2);
  }
  for (odb::dbNet* n : block->getNets()) {
    int loads = 0;
    for (odb::dbITerm* it : n->getITerms()) {
      loads += it->getIoType() == odb::dbIoType::INPUT ? 1 : 0;
    }
    CHECK(n == in || loads <= 8);
  }

  // The mutant: one sink moved behind another driver must be caught.
  odb::dbNet* stray = odb::dbNet::create(block, "stray");
  odb::dbInst* other = odb::dbInst::create(block, inv, "other");
  other->findITerm("A")->connect(in);
  other->findITerm("Y")->connect(stray);
  sinks[17]->disconnect();
  sinks[17]->connect(stray);
  auto problems = rb.Check();
  CHECK(problems.size() == 1);
  CHECK(problems[0].find("s17/A") != std::string::npos);
  // Families and drives by name, the platform's dont-use kept out.
  CHECK(fanout_tree::FamilyOf("AND2x4_ASAP7_75t_R") == "AND2x#_ASAP7_75t_R");
  CHECK(fanout_tree::FamilyOf("INVxp33_ASAP7_75t_R") == "INVx#_ASAP7_75t_R");
  CHECK(fanout_tree::FamilyOf("XOR2xp5_ASAP7_75t_R") == "XOR2x#_ASAP7_75t_R");
  CHECK(fanout_tree::FamilyOf("BUFx12f_ASAP7_75t_R") == "BUFx#_ASAP7_75t_R");
  CHECK(fanout_tree::FamilyOf("TAPCELL_ASAP7_75t_R").empty());
  CHECK(fanout_tree::DriveOf("INVxp33_ASAP7_75t_R") == 0.33);
  CHECK(fanout_tree::DriveOf("BUFx12f_ASAP7_75t_R") == 12);

  // A root upsized: an INVx1 behind which ABC put one BUFx2 for twelve
  // sinks (7.2 fF at 0.6 each). Rebuilt, the sinks fit on the root, and
  // the root becomes the smallest INV that drives them, never an xp or
  // x1p cell.
  {
    odb::dbNet* n2 = odb::dbNet::create(block, "n2");
    odb::dbNet* n3 = odb::dbNet::create(block, "n3");
    odb::dbInst* d2 = odb::dbInst::create(block, inv, "d2");
    d2->findITerm("A")->connect(in);
    d2->findITerm("Y")->connect(n2);
    odb::dbInst* b2 = odb::dbInst::create(block, buf2, "abc_d2");
    b2->findITerm("A")->connect(n2);
    b2->findITerm("Y")->connect(n3);
    for (int s = 0; s < 12; ++s) {
      odb::dbInst* g = odb::dbInst::create(block, and2, ("u" + std::to_string(s)).c_str());
      g->findITerm("A")->connect(n3);
      g->findITerm("B")->connect(in);
    }
    fanout_tree::Options up;
    up.max_fanout = 16;
    up.upsize_roots = true;
    up.dont_use = {"xp", "x1p"};
    fanout_tree::Rebuilder rb3(block, buffers, caps, up);
    rb3.RebuildNet(n2);
    CHECK(rb3.Check().empty());
    CHECK(rb3.stats().buffers_removed == 1);
    CHECK(rb3.stats().buffers_added == 0);
    const std::string m = d2->getMaster()->getName();
    CHECK(m.rfind("INVx", 0) == 0);
    CHECK(m.find("xp") == std::string::npos && m.find("x1p") == std::string::npos);
    CHECK(fanout_tree::DriveOf(m) >= 7.2 / up.ff_per_drive);
    CHECK(rb3.stats().roots_upsized == 1);
  }
  // A weak driver: AOI211 has nothing above x1 once xp5 is banned, so
  // twelve sinks go behind a buffer and the gate drives only that.
  {
    odb::dbMaster* aoi = db->findMaster("AOI211x1_ASAP7_75t_R");
    CHECK(aoi != nullptr);
    odb::dbNet* n4 = odb::dbNet::create(block, "n4");
    odb::dbInst* w = odb::dbInst::create(block, aoi, "weak");
    for (const char* p : {"A1", "A2", "B", "C"}) {
      w->findITerm(p)->connect(in);
    }
    w->findITerm("Y")->connect(n4);
    for (int s = 0; s < 12; ++s) {
      odb::dbInst* g = odb::dbInst::create(block, and2, ("v" + std::to_string(s)).c_str());
      g->findITerm("A")->connect(n4);
      g->findITerm("B")->connect(in);
    }
    fanout_tree::Options up;
    up.max_fanout = 32;
    up.max_load_ff = 48;
    up.upsize_roots = true;
    up.dont_use = {"xp", "x1p"};
    up.weak_ff_per_drive = 2.5;
    fanout_tree::Rebuilder rb4(block, buffers, caps, up);
    rb4.UpsizeAll();
    CHECK(rb4.Check().empty());
    CHECK(rb4.stats().weak_rebuilt >= 1);
    CHECK(w->getMaster() == aoi);
    int loads = 0;
    for (odb::dbITerm* it : n4->getITerms()) {
      loads += it->getIoType() == odb::dbIoType::INPUT ? 1 : 0;
    }
    CHECK(loads == 1);
  }
  std::cout << "fanout_tree_test: ok\n";
  return 0;
}
