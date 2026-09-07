// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, The OpenROAD Authors
//
// Scaffolding for the odb SoA study.
//
// Dumps one dbTable's slot records exactly as dbTable::writePage would emit
// them -- through the type's existing operator<<, no per-type code -- so the
// wire-side question ("what does a field-major permutation of these bytes
// compress to, as a function of block size?") can be answered outside
// OpenROAD, in Python, on real bytes from a real design.
//
// Output: <out>.bin   concatenated per-slot records, allocated slots only
//         <out>.json  record lengths and table geometry
//
// The private-access macro is deliberate: the study needs at _dbBlock's
// tables, which are private to odb.

#define private public
#define protected public
#include "dbBlock.h"
#include "dbBox.h"
#include "dbITerm.h"
#include "dbInst.h"
#include "dbNet.h"
#include "dbSBox.h"
#include "dbTable.h"
#undef private
#undef protected

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "odb/db.h"
#include "odb/dbStream.h"
#include "utl/Logger.h"

using namespace odb;

namespace {

struct Dump
{
  std::vector<uint32_t> lengths;  // per allocated slot, in slot order
  std::string bytes;              // records concatenated
  uint32_t page_size = 0;
  uint32_t slot_bytes = 0;  // sizeof(T)
  uint32_t page_cnt = 0;
  uint32_t slots = 0;      // pages * page_size
  uint32_t allocated = 0;  // slots carrying an object
};

// Serialize every allocated slot of `table` through the type's own
// operator<<, recording where each record ends. This is the same call
// writePage makes, which is the point: a field-major writer that needed a
// hand-written per-type serializer would not be worth having.
template <class T, uint32_t page_size>
Dump dumpTable(_dbDatabase* db, dbTable<T, page_size>* table)
{
  Dump d;
  d.page_size = page_size;
  d.slot_bytes = sizeof(T);
  d.page_cnt = table->page_cnt_;
  d.slots = table->page_cnt_ * page_size;

  std::ostringstream out(std::ios::binary);
  dbOStream stream(db, out);
  dbOStream::Position prev = stream.pos();

  for (uint32_t p = 0; p < table->page_cnt_; ++p) {
    const T* t = (const T*) table->pages_[p]->objects_;
    for (uint32_t s = 0; s < page_size; ++s, ++t) {
      if ((t->offset_in_bytes_ & kAllocBit) == 0) {
        continue;
      }
      stream << *t;
      const dbOStream::Position now = stream.pos();
      d.lengths.push_back((uint32_t) (now - prev));
      prev = now;
      ++d.allocated;
    }
  }

  d.bytes = out.str();
  return d;
}

void write(const std::string& out_stem, const std::string& table, Dump& d)
{
  const std::string bin = out_stem + ".bin";
  std::ofstream b(bin, std::ios::binary);
  b.write(d.bytes.data(), (std::streamsize) d.bytes.size());
  b.close();

  const std::string json = out_stem + ".json";
  std::ofstream j(json);
  j << "{\n";
  j << "  \"table\": \"" << table << "\",\n";
  j << "  \"page_size\": " << d.page_size << ",\n";
  j << "  \"slot_bytes\": " << d.slot_bytes << ",\n";
  j << "  \"page_cnt\": " << d.page_cnt << ",\n";
  j << "  \"slots\": " << d.slots << ",\n";
  j << "  \"allocated\": " << d.allocated << ",\n";
  j << "  \"record_bytes\": " << d.bytes.size() << ",\n";
  j << "  \"lengths\": [";
  for (size_t i = 0; i < d.lengths.size(); ++i) {
    j << (i ? "," : "") << d.lengths[i];
  }
  j << "]\n}\n";
  j.close();

  std::printf("%-8s slots=%u allocated=%u sizeof=%u page_size=%u bytes=%zu\n",
              table.c_str(),
              d.slots,
              d.allocated,
              d.slot_bytes,
              d.page_size,
              d.bytes.size());
}

}  // namespace

int main(int argc, char** argv)
{
  if (argc < 4) {
    std::cerr << "usage: SoaDumpTable <in.odb> <out-stem> <table>...\n"
              << "  table: sbox | box | iterm | inst | net\n";
    return 2;
  }
  const std::string odb = argv[1];
  const std::string stem = argv[2];

  utl::Logger logger;
  dbDatabase* db = dbDatabase::create();
  db->setLogger(&logger);
  {
    std::ifstream f(odb, std::ios::binary);
    if (!f.good()) {
      std::cerr << "cannot read " << odb << "\n";
      return 1;
    }
    db->read(f);
  }

  _dbDatabase* impl = (_dbDatabase*) db;
  _dbBlock* block = (_dbBlock*) db->getChip()->getBlock();

  for (int i = 3; i < argc; ++i) {
    const std::string table = argv[i];
    const std::string out = stem + "." + table;
    if (table == "sbox") {
      Dump d = dumpTable(impl, block->sbox_tbl_);
      write(out, table, d);
    } else if (table == "box") {
      Dump d = dumpTable(impl, block->box_tbl_);
      write(out, table, d);
    } else if (table == "iterm") {
      Dump d = dumpTable(impl, block->iterm_tbl_);
      write(out, table, d);
    } else if (table == "inst") {
      Dump d = dumpTable(impl, block->inst_tbl_);
      write(out, table, d);
    } else if (table == "net") {
      Dump d = dumpTable(impl, block->net_tbl_);
      write(out, table, d);
    } else {
      std::cerr << "unknown table: " << table << "\n";
      return 2;
    }
  }
  return 0;
}
