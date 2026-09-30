// fanout_tree: rebuild an ODB's buffer trees by construction. See
// fanout_tree.h.
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "fanout_tree.h"
#include "odb/db.h"
#include "utl/Logger.h"

namespace {

void Usage() {
  std::cerr << "usage: fanout_tree --odb IN.odb --out OUT.odb"
               " --liberty FILE [--liberty FILE ...]"
               " --buffers CELL[,CELL...] [--max-fanout N] [--max-load-ff F]"
               " [--ff-per-drive F] [--root-ff-per-drive F]"
               " [--upsize-roots | --upsize-all] [--dont-use SUBSTR,...] [--net NAME ...]\n"
               "Liberty files are read uncompressed. A buffer's drive is the"
               " number after `x` in its name (BUFx12f_ASAP7_75t_R: 12).\n";
}

}  // namespace

int main(int argc, char** argv) {
  std::string in_path, out_path;
  std::vector<std::string> libs, buffer_names, nets;
  fanout_tree::Options opt;
  bool upsize_all = false;
  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    auto val = [&]() -> std::string {
      if (i + 1 >= argc) {
        Usage();
        std::exit(2);
      }
      return argv[++i];
    };
    if (a == "--odb") {
      in_path = val();
    } else if (a == "--out") {
      out_path = val();
    } else if (a == "--liberty") {
      libs.push_back(val());
    } else if (a == "--buffers") {
      std::stringstream ss(val());
      std::string c;
      while (std::getline(ss, c, ',')) {
        if (!c.empty()) {
          buffer_names.push_back(c);
        }
      }
    } else if (a == "--max-fanout") {
      opt.max_fanout = std::atoi(val().c_str());
    } else if (a == "--max-load-ff") {
      opt.max_load_ff = std::atof(val().c_str());
    } else if (a == "--ff-per-drive") {
      opt.ff_per_drive = std::atof(val().c_str());
    } else if (a == "--root-ff-per-drive") {
      opt.root_ff_per_drive = std::atof(val().c_str());
    } else if (a == "--upsize-roots") {
      opt.upsize_roots = true;
    } else if (a == "--upsize-all") {
      opt.upsize_roots = true;
      upsize_all = true;
    } else if (a == "--dont-use") {
      std::stringstream ss(val());
      std::string c;
      while (std::getline(ss, c, ',')) {
        opt.dont_use.push_back(c);
      }
    } else if (a == "--net") {
      nets.push_back(val());
    } else {
      Usage();
      return 2;
    }
  }
  if (in_path.empty() || out_path.empty() || buffer_names.empty()) {
    Usage();
    return 2;
  }
  try {
    utl::Logger logger;
    odb::dbDatabase* db = odb::dbDatabase::create();
    db->setLogger(&logger);
    {
      std::ifstream in(in_path, std::ios::binary);
      if (!in) {
        throw std::runtime_error("cannot read " + in_path);
      }
      db->read(in);
    }
    odb::dbBlock* block = db->getChip() ? db->getChip()->getBlock() : nullptr;
    if (block == nullptr) {
      throw std::runtime_error(in_path + " has no block");
    }
    fanout_tree::PinCaps caps;
    for (const auto& l : libs) {
      caps.ReadLiberty(l);
    }
    std::vector<fanout_tree::Buffer> buffers;
    for (const auto& n : buffer_names) {
      odb::dbMaster* m = db->findMaster(n.c_str());
      if (m == nullptr) {
        throw std::runtime_error("buffer cell not in the ODB's libraries: " + n);
      }
      fanout_tree::Buffer b;
      b.master = m;
      b.drive = fanout_tree::DriveOf(n);
      buffers.push_back(b);
    }
    fanout_tree::Rebuilder rb(block, buffers, caps, opt);
    if (nets.empty()) {
      rb.Run();
    } else {
      for (const auto& n : nets) {
        odb::dbNet* net = block->findNet(n.c_str());
        if (net == nullptr) {
          throw std::runtime_error("no net " + n);
        }
        rb.RebuildNet(net);
      }
    }
    if (upsize_all) {
      std::cout << "fanout_tree: " << rb.UpsizeAll() << " more drivers upsized\n";
    }
    auto problems = rb.Check();
    const auto& s = rb.stats();
    std::cout << "fanout_tree: " << s.nets_rebuilt << " nets rebuilt, " << s.sinks
              << " sinks, buffers " << s.buffers_removed << " removed "
              << s.buffers_added << " added, max depth " << s.max_depth_before
              << " -> " << s.max_depth_after << ", " << s.roots_upsized
              << " roots upsized, " << problems.size()
              << " check failures\n";
    if (!problems.empty()) {
      for (size_t i = 0; i < problems.size() && i < 20; ++i) {
        std::cerr << "fanout_tree: " << problems[i] << "\n";
      }
      return 1;
    }
    std::ofstream out(out_path, std::ios::binary);
    if (!out) {
      throw std::runtime_error("cannot write " + out_path);
    }
    db->write(out);
  } catch (const std::exception& e) {
    std::cerr << "fanout_tree: " << e.what() << "\n";
    return 1;
  }
  return 0;
}
