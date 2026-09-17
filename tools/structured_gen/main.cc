// structured_gen: placed register files as macros. See README.md.
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "odb/db.h"
#include "odb/defout.h"
#include "odb/lefin.h"
#include "regfile.h"
#include "utl/Logger.h"

namespace {

void Usage() {
  std::cerr << "usage: structured_gen --spec FILE --lef FILE [--lef FILE ...]"
               " --odb OUT.odb [--verilog OUT.v] [--def OUT.def]\n";
}

}  // namespace

int main(int argc, char** argv) {
  std::string spec_path, odb_path, verilog_path, def_path;
  std::vector<std::string> lefs;
  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    auto next = [&]() -> std::string {
      if (i + 1 >= argc) {
        Usage();
        std::exit(2);
      }
      return argv[++i];
    };
    if (a == "--spec") {
      spec_path = next();
    } else if (a == "--lef") {
      lefs.push_back(next());
    } else if (a == "--odb") {
      odb_path = next();
    } else if (a == "--verilog") {
      verilog_path = next();
    } else if (a == "--def") {
      def_path = next();
    } else {
      Usage();
      return 2;
    }
  }
  if (spec_path.empty() || lefs.empty() || odb_path.empty()) {
    Usage();
    return 2;
  }
  try {
    utl::Logger logger;
    odb::dbDatabase* db = odb::dbDatabase::create();
    db->setLogger(&logger);
    odb::lefin reader(db, &logger, /*ignore_non_routing_layers=*/false);
    // The first LEF is the technology, the rest are cell libraries.
    odb::dbTech* tech = reader.createTech("tech", lefs[0].c_str());
    if (tech == nullptr) {
      throw std::runtime_error("could not read tech LEF " + lefs[0]);
    }
    for (size_t i = 1; i < lefs.size(); ++i) {
      std::string name = "lib" + std::to_string(i);
      if (reader.createLib(tech, name.c_str(), lefs[i].c_str()) == nullptr) {
        throw std::runtime_error("could not read LEF " + lefs[i]);
      }
    }
    structured_gen::Spec spec = structured_gen::ReadSpec(spec_path);
    odb::dbBlock* block = structured_gen::Generate(db, &logger, spec);
    if (!verilog_path.empty()) {
      structured_gen::WriteVerilog(block, verilog_path);
    }
    if (!def_path.empty()) {
      // For ORFS's FLOORPLAN_DEF: die, rows, placed components and pins,
      // read back with `read_def -floorplan_initialize` so the flow can
      // start from this placement with no rule of its own.
      odb::DefOut writer(&logger);
      if (!writer.writeBlock(block, def_path.c_str())) {
        throw std::runtime_error("cannot write " + def_path);
      }
    }
    std::ofstream out(odb_path, std::ios::binary);
    if (!out) {
      throw std::runtime_error("cannot write " + odb_path);
    }
    db->write(out);
    std::cout << "structured_gen: " << spec.module << " " << spec.words << "x"
              << spec.bits << " " << spec.read.size() << "R" << spec.write.size()
              << "W: " << block->getInsts().size() << " instances, "
              << block->getNets().size() << " nets\n";
  } catch (const std::exception& e) {
    std::cerr << "structured_gen: " << e.what() << "\n";
    return 1;
  }
  return 0;
}
