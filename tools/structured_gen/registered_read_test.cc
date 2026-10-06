// A 4x4 2R2W register file whose read address is registered, as firtool
// writes XiangShan's datapath register files: the address ports feed only
// flops, the flops carry the RTL's register names, and the model liberty
// times the read from the clock.
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <set>
#include <sstream>
#include <string>

#include "odb/db.h"
#include "odb/lefin.h"
#include "regfile.h"
#include "utl/Logger.h"
#include "views.h"

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
    std::cerr << "usage: registered_read_test TECH.lef CELLS.lef\n";
    return 2;
  }
  const char* srcdir = std::getenv("TEST_SRCDIR");
  auto runfile = [&](const char* rel) {
    return srcdir ? std::string(srcdir) + "/" + rel : std::string(rel);
  };
  const char* tmp = std::getenv("TEST_TMPDIR");
  std::string dir = tmp ? tmp : ".";
  std::string spec_path = dir + "/rf.spec";
  {
    std::ofstream f(spec_path);
    f << "module SmallRegFile\nwords 4\nbits 4\nclock clock\n"
         "read io_readPorts_0_addr io_readPorts_0_data\n"
         "read io_readPorts_1_addr io_readPorts_1_data\n"
         "write io_writePorts_0_addr io_writePorts_0_data io_writePorts_0_wen\n"
         "write io_writePorts_1_addr io_writePorts_1_data io_writePorts_1_wen\n"
         "read_latency 1\n"
         "store_name mem_{word}[{bit}]\n"
         "read_reg_name io_readPorts_{port}_data_REG[{bit}]\n"
         "cell flop DFFHQNx1_ASAP7_75t_R\ncell and2 AND2x2_ASAP7_75t_R\n"
         "cell or2 OR2x2_ASAP7_75t_R\ncell ao22 AO22x2_ASAP7_75t_R\n"
         "cell inv INVx1_ASAP7_75t_R\npin_layer M4\n";
  }
  utl::Logger logger;
  odb::dbDatabase* db = odb::dbDatabase::create();
  db->setLogger(&logger);
  odb::lefin reader(db, &logger, false);
  odb::dbTech* tech = reader.createTech("asap7", runfile(argv[1]).c_str());
  CHECK(tech != nullptr);
  CHECK(reader.createLib(tech, "asap7sc7p5t", runfile(argv[2]).c_str()) != nullptr);

  structured_gen::Spec spec = structured_gen::ReadSpec(spec_path);
  CHECK(spec.read_latency == 1);
  odb::dbBlock* block = structured_gen::Generate(db, &logger, spec);
  CHECK(block != nullptr);

  // The flops are the RTL's registers by name: the storage and the two
  // read ports' two address bits each.
  std::set<std::string> flops;
  for (odb::dbInst* inst : block->getInsts()) {
    if (inst->getMaster()->getName() == spec.cells.flop) {
      flops.insert(inst->getName());
    }
    CHECK(block->getDieArea().contains(inst->getBBox()->getBox()));
  }
  std::set<std::string> want;
  for (int n = 0; n < 4; ++n) {
    for (int b = 0; b < 4; ++b) {
      want.insert("mem_" + std::to_string(n) + "[" + std::to_string(b) + "]");
    }
  }
  for (int r = 0; r < 2; ++r) {
    for (int i = 0; i < 2; ++i) {
      want.insert("io_readPorts_" + std::to_string(r) + "_data_REG[" +
                  std::to_string(i) + "]");
    }
  }
  CHECK(flops == want);

  // A read address reaches nothing but its register's D: no
  // combinational path from the port to the read data.
  for (int r = 0; r < 2; ++r) {
    for (int i = 0; i < 2; ++i) {
      std::string port = "io_readPorts_" + std::to_string(r) + "_addr[" +
                         std::to_string(i) + "]";
      odb::dbBTerm* t = block->findBTerm(port.c_str());
      CHECK(t != nullptr);
      int sinks = 0;
      for (odb::dbITerm* it : t->getNet()->getITerms()) {
        CHECK(it->getInst()->getMaster()->getName() == spec.cells.flop);
        CHECK(it->getMTerm()->getName() == "D");
        ++sinks;
      }
      CHECK(sinks == 1);
    }
  }

  // The model liberty: the address is checked against the clock, the
  // data launched from it.
  std::string lib_path = dir + "/rf.lib";
  structured_gen::WriteLiberty(block, spec, spec.lib, lib_path, false);
  std::ifstream lf(lib_path);
  std::stringstream ss;
  ss << lf.rdbuf();
  const std::string lib = ss.str();
  CHECK(lib.find("timing_type : rising_edge;") != std::string::npos);
  CHECK(lib.find("timing_type : combinational;") == std::string::npos);
  CHECK(lib.find("timing_type : setup_rising ;") != std::string::npos);
  std::cout << "registered_read_test: ok\n";
  return 0;
}
