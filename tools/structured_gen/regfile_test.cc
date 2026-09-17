// An 8x4 2R2W register file against the real asap7 LEF: every cell placed
// on a row, none overlapping, every port pinned, the Verilog written.
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

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
         "pin_layer M4\ntap_columns 4\nbanks 2\n";
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

  // The views a parent consumes before the block is routed.
  std::string lef_path = dir + "/rf8x4.lef";
  structured_gen::WriteLef(block, &logger, lef_path);
  std::ifstream lf(lef_path);
  std::string lef((std::istreambuf_iterator<char>(lf)),
                  std::istreambuf_iterator<char>());
  CHECK(lef.find("MACRO rf8x4") != std::string::npos);
  CHECK(lef.find("PIN io_readPorts_0_addr[0]") != std::string::npos);
  CHECK(lef.find("PIN clock") != std::string::npos);
  CHECK(lef.find("OBS") != std::string::npos);

  std::string lib_path = dir + "/rf8x4.lib";
  structured_gen::WriteLiberty(block, spec, spec.lib, lib_path, false);
  std::ifstream bf(lib_path);
  std::string lib((std::istreambuf_iterator<char>(bf)),
                  std::istreambuf_iterator<char>());
  CHECK(lib.find("cell(rf8x4)") != std::string::npos);
  CHECK(lib.find("bus(io_readPorts_0_addr)") != std::string::npos);
  CHECK(lib.find("bus(io_readPorts_1_data)") != std::string::npos);
  CHECK(lib.find("timing_type : combinational") != std::string::npos);
  CHECK(lib.find("timing_type : setup_rising") != std::string::npos);
  CHECK(lib.find("pin(io_writePorts_1_wen)") != std::string::npos);
  CHECK(lib.find("clock : true") != std::string::npos);

  // The spec against an RTL header in firtool's style: a match, then a
  // width that differs, then a port the spec never mentions.
  std::string rtl_path = dir + "/rf8x4_rtl.v";
  {
    std::ofstream f(rtl_path);
    f << "module rf8x4(\n"
         "  input        clock,\n"
         "  input  [2:0] io_readPorts_0_addr,\n"
         "               io_readPorts_1_addr,\n"
         "  output [3:0] io_readPorts_0_data,\n"
         "               io_readPorts_1_data,\n"
         "  input  [2:0] io_writePorts_0_addr,\n"
         "  input  [3:0] io_writePorts_0_data,\n"
         "  input        io_writePorts_0_wen,\n"
         "  input  [2:0] io_writePorts_1_addr,\n"
         "  input  [3:0] io_writePorts_1_data,\n"
         "  input        io_writePorts_1_wen\n"
         ");\nendmodule\n";
  }
  auto ports = structured_gen::ReadModulePorts(rtl_path, "rf8x4");
  CHECK(ports.size() == 11);
  CHECK(structured_gen::CheckPorts(spec, ports).empty());
  {
    auto bad = ports;
    bad[1].width = 4;  // io_readPorts_0_addr
    auto problems = structured_gen::CheckPorts(spec, bad);
    CHECK(problems.size() == 1);
    CHECK(problems[0].find("io_readPorts_0_addr") != std::string::npos);
    bad.push_back(structured_gen::RtlPort{"io_extra", 1, true});
    CHECK(structured_gen::CheckPorts(spec, bad).size() == 2);
  }

  // A banked read port, the RegfileBank shape: per-bank address and data
  // buses, no footer OR; the outputs are the banks' own.
  std::string banked_spec = dir + "/rfb.spec";
  {
    std::ofstream f(banked_spec);
    f << "module rfb8x4\nwords 8\nbits 4\nbanks 2\nclock clock\n"
         "read_banked io_readPorts_0_addr_0 io_readPorts_0_data_0 "
         "io_readPorts_0_addr_1 io_readPorts_0_data_1\n"
         "write io_writePorts_0_addr io_writePorts_0_data io_writePorts_0_wen\n"
         "cell flop DFFHQNx1_ASAP7_75t_R\ncell and2 AND2x2_ASAP7_75t_R\n"
         "cell or2 OR2x2_ASAP7_75t_R\ncell ao22 AO22x2_ASAP7_75t_R\n"
         "cell inv INVx1_ASAP7_75t_R\ncell tap TAPCELL_ASAP7_75t_R\n";
  }
  structured_gen::Spec bspec = structured_gen::ReadSpec(banked_spec);
  CHECK(bspec.read.size() == 1 && bspec.read[0].banked());
  // One generation per database: a second one gets its own.
  odb::dbDatabase* db2 = odb::dbDatabase::create();
  db2->setLogger(&logger);
  odb::lefin reader2(db2, &logger, false);
  odb::dbTech* tech2 = reader2.createTech("asap7", tech_lef.c_str());
  CHECK(reader2.createLib(tech2, "asap7sc7p5t", cell_lef.c_str()) != nullptr);
  odb::dbBlock* bblock = structured_gen::Generate(db2, &logger, bspec);
  CHECK(bblock != nullptr);
  int bank_outputs = 0;
  for (odb::dbBTerm* t : bblock->getBTerms()) {
    std::string n = t->getName();
    if (n.rfind("io_readPorts_0_data_", 0) == 0) {
      ++bank_outputs;
      CHECK(t->getIoType() == odb::dbIoType::OUTPUT);
      CHECK(t->getBPins().size() == 1);
    }
  }
  CHECK(bank_outputs == 2 * 4);  // two banks, four bits each
  // Bank-local addresses are 2 bits (4 words per bank), the write address 3.
  CHECK(bblock->findBTerm("io_readPorts_0_addr_1[1]") != nullptr);
  CHECK(bblock->findBTerm("io_readPorts_0_addr_1[2]") == nullptr);
  CHECK(bblock->findBTerm("io_writePorts_0_addr[2]") != nullptr);
  {
    std::string blib = dir + "/rfb.lib";
    structured_gen::WriteLiberty(bblock, bspec, bspec.lib, blib, false);
    std::ifstream f(blib);
    std::string text((std::istreambuf_iterator<char>(f)),
                     std::istreambuf_iterator<char>());
    CHECK(text.find("bus(io_readPorts_0_data_1)") != std::string::npos);
    CHECK(text.find("bus(io_readPorts_0_addr_0)") != std::string::npos);
  }

  // Stacked banks: the same file with its two banks one above the other
  // is half as wide and twice as tall as with them side by side, and has
  // the same cells.
  std::string stacked_spec = dir + "/rfs.spec";
  {
    std::ifstream in(spec_path);
    std::ofstream f(stacked_spec);
    f << in.rdbuf() << "bank_columns 1\n";
  }
  structured_gen::Spec sspec = structured_gen::ReadSpec(stacked_spec);
  CHECK(sspec.bank_columns == 1);
  odb::dbDatabase* db3 = odb::dbDatabase::create();
  db3->setLogger(&logger);
  odb::lefin reader3(db3, &logger, false);
  odb::dbTech* tech3 = reader3.createTech("asap7", tech_lef.c_str());
  CHECK(reader3.createLib(tech3, "asap7sc7p5t", cell_lef.c_str()) != nullptr);
  odb::dbBlock* sblock = structured_gen::Generate(db3, &logger, sspec);
  CHECK(sblock != nullptr);
  CHECK(sblock->getInsts().size() == block->getInsts().size());
  CHECK(sblock->getDieArea().dx() < block->getDieArea().dx());
  CHECK(sblock->getDieArea().dy() > block->getDieArea().dy());
  CHECK(sblock->getDieArea().dx() * 2 > block->getDieArea().dx());
  // Bit folds: the 4-bit word in two bands is narrower and taller again,
  // with the same cells plus a second copy of each word's decode.
  std::string folded_spec = dir + "/rff.spec";
  {
    std::ifstream in(spec_path);
    std::ofstream f(folded_spec);
    f << in.rdbuf() << "bit_folds 2\n";
  }
  odb::dbDatabase* db4 = odb::dbDatabase::create();
  db4->setLogger(&logger);
  odb::lefin reader4(db4, &logger, false);
  odb::dbTech* tech4 = reader4.createTech("asap7", tech_lef.c_str());
  CHECK(reader4.createLib(tech4, "asap7sc7p5t", cell_lef.c_str()) != nullptr);
  odb::dbBlock* fblock = structured_gen::Generate(
      db4, &logger, structured_gen::ReadSpec(folded_spec));
  CHECK(fblock != nullptr);
  CHECK(fblock->getInsts().size() > block->getInsts().size());
  CHECK(fblock->getDieArea().dx() < block->getDieArea().dx());
  CHECK(fblock->getDieArea().dy() > block->getDieArea().dy());
  {
    int fflops = 0;
    std::map<int, std::vector<std::pair<int, int>>> rows;
    odb::Rect fdie = fblock->getDieArea();
    for (odb::dbInst* inst : fblock->getInsts()) {
      odb::Rect box = inst->getBBox()->getBox();
      CHECK(fdie.contains(box));
      if (inst->getMaster()->getName() == "DFFHQNx1_ASAP7_75t_R") {
        ++fflops;
      }
      rows[box.yMin()].emplace_back(box.xMin(), box.xMax());
    }
    CHECK(fflops == 8 * 4);
    for (auto& [y, spans] : rows) {
      std::sort(spans.begin(), spans.end());
      for (size_t i = 1; i < spans.size(); ++i) {
        CHECK(spans[i].first >= spans[i - 1].second);
      }
    }
    for (odb::dbBTerm* t : fblock->getBTerms()) {
      CHECK(t->getBPins().size() == 1);
    }
  }

  {
    // A bank_columns that does not divide banks is refused.
    std::ofstream f(stacked_spec, std::ios::app);
    f << "bank_columns 3\n";
    bool refused = false;
    try {
      structured_gen::Generate(db3, &logger, structured_gen::ReadSpec(stacked_spec));
    } catch (const std::runtime_error&) {
      refused = true;
    }
    CHECK(refused);
  }

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
