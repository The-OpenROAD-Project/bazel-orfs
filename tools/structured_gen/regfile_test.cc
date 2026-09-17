// An 8x4 2R2W register file against the real asap7 LEF: every cell placed
// on a row, none overlapping, every port pinned, the Verilog written.
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <vector>

#include "odb/db.h"
#include "odb/lefin.h"
#include "regfile.h"
#include "utl/Logger.h"

#define CHECK(cond)                                                       \
  do {                                                                    \
    if (!(cond)) {                                                        \
      std::cerr << __FILE__ << ":" << __LINE__ << ": CHECK failed: " #cond \
                << "\n";                                                  \
      return 1;                                                           \
    }                                                                     \
  } while (0)

int main(int argc, char** argv) {
  if (argc < 3) {
    std::cerr << "usage: regfile_test TECH.lef CELLS.lef\n";
    return 2;
  }
  // The LEFs arrive as rlocationpaths, relative to the runfiles root.
  const char* srcdir = std::getenv("TEST_SRCDIR");
  auto runfile = [&](const char* rel) {
    return srcdir ? std::string(srcdir) + "/" + rel : std::string(rel);
  };
  std::string tech_lef = runfile(argv[1]);
  std::string cell_lef = runfile(argv[2]);
  const char* tmp = std::getenv("TEST_TMPDIR");
  std::string dir = tmp ? tmp : ".";
  std::string spec_path = dir + "/rf.spec";
  {
    std::ofstream f(spec_path);
    f << "module rf8x4\nwords 8\nbits 4\nclock clock\n"
         "read io_readPorts_0_addr io_readPorts_0_data\n"
         "read io_readPorts_1_addr io_readPorts_1_data\n"
         "write io_writePorts_0_addr io_writePorts_0_data io_writePorts_0_wen\n"
         "write io_writePorts_1_addr io_writePorts_1_data io_writePorts_1_wen\n"
         "cell flop DFFHQNx1_ASAP7_75t_R\ncell and2 AND2x2_ASAP7_75t_R\n"
         "cell or2 OR2x2_ASAP7_75t_R\ncell ao22 AO22x2_ASAP7_75t_R\n"
         "cell inv INVx1_ASAP7_75t_R\ncell tap TAPCELL_ASAP7_75t_R\n"
         "pin_layer M4\ntap_columns 4\n";
  }
  utl::Logger logger;
  odb::dbDatabase* db = odb::dbDatabase::create();
  db->setLogger(&logger);
  odb::lefin reader(db, &logger, false);
  odb::dbTech* tech = reader.createTech("asap7", tech_lef.c_str());
  CHECK(tech != nullptr);
  CHECK(reader.createLib(tech, "asap7sc7p5t", cell_lef.c_str()) != nullptr);

  structured_gen::Spec spec = structured_gen::ReadSpec(spec_path);
  CHECK(spec.words == 8 && spec.bits == 4);
  CHECK(spec.read.size() == 2 && spec.write.size() == 2);
  odb::dbBlock* block = structured_gen::Generate(db, &logger, spec);
  CHECK(block != nullptr);

  // Storage: one flop per bit.
  int flops = 0;
  std::map<int, std::vector<std::pair<int, int>>> by_y;  // y -> [x0, x1)
  odb::Rect die = block->getDieArea();
  for (odb::dbInst* inst : block->getInsts()) {
    CHECK(inst->getPlacementStatus() == odb::dbPlacementStatus::FIRM);
    odb::Rect box = inst->getBBox()->getBox();
    CHECK(die.contains(box));
    if (inst->getMaster()->getName() == "DFFHQNx1_ASAP7_75t_R") {
      ++flops;
    }
    by_y[box.yMin()].emplace_back(box.xMin(), box.xMax());
  }
  CHECK(flops == 8 * 4);
  // No two cells overlap on a row.
  for (auto& [y, spans] : by_y) {
    std::sort(spans.begin(), spans.end());
    for (size_t i = 1; i < spans.size(); ++i) {
      CHECK(spans[i].first >= spans[i - 1].second);
    }
  }
  // Every signal port has a pin box, and the widths are the RTL's.
  int bterms = 0;
  for (odb::dbBTerm* t : block->getBTerms()) {
    ++bterms;
    CHECK(t->getBPins().size() == 1);
  }
  // clock + 2*(3 addr) + 2*(3 addr + 4 data + wen) + 2*4 rdata
  CHECK(bterms == 1 + 2 * 3 + 2 * (3 + 4 + 1) + 2 * 4);
  // Every instance pin is connected, except power/ground pins.
  for (odb::dbInst* inst : block->getInsts()) {
    for (odb::dbITerm* it : inst->getITerms()) {
      if (it->getSigType() == odb::dbSigType::POWER ||
          it->getSigType() == odb::dbSigType::GROUND) {
        continue;
      }
      CHECK(it->getNet() != nullptr);
    }
  }

  std::string v_path = dir + "/rf8x4.v";
  structured_gen::WriteVerilog(block, v_path);
  std::ifstream v(v_path);
  std::string text((std::istreambuf_iterator<char>(v)),
                   std::istreambuf_iterator<char>());
  CHECK(text.find("module rf8x4(") != std::string::npos);
  CHECK(text.find("input [2:0] io_readPorts_0_addr") != std::string::npos);
  CHECK(text.find("output [3:0] io_readPorts_1_data") != std::string::npos);
  CHECK(text.find("input io_writePorts_0_wen") != std::string::npos);
  CHECK(text.find("endmodule") != std::string::npos);

  std::string odb_path = dir + "/rf8x4.odb";
  {
    std::ofstream out(odb_path, std::ios::binary);
    db->write(out);
  }
  CHECK(std::ifstream(odb_path).good());
  std::cout << "regfile_test: " << block->getInsts().size() << " instances, "
            << bterms << " ports, OK\n";
  return 0;
}
