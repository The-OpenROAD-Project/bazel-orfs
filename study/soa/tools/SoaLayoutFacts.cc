// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, The OpenROAD Authors
//
// Scaffolding for the odb SoA study: reports the exact in-memory layout of the
// slot structs of the candidate tables, so the per-slot cost of the
// array-of-structs storage can be counted rather than estimated.
//
// _dbObject's bookkeeping fields are private to dbTable, hence the macro.
#define private public
#define protected public
#include "dbBox.h"
#include "dbCore.h"
#include "dbITerm.h"
#include "dbInst.h"
#include "dbNet.h"
#include "dbSBox.h"
#undef private
#undef protected

#include <cstddef>
#include <cstdio>

#include "odb/geom.h"

using namespace odb;

#pragma clang diagnostic ignored "-Winvalid-offsetof"

namespace {

void type(const char* name, size_t size)
{
  std::printf("\n%s  sizeof=%zu\n", name, size);
}

#define FIELD(T, f)                                       \
  std::printf("  %-22s off=%3zu size=%2zu\n",             \
              #f,                                         \
              (size_t) __builtin_offsetof(T, f),          \
              sizeof(((T*) nullptr)->f))

}  // namespace

int main()
{
  type("_dbObject (base bookkeeping)", sizeof(_dbObject));
  FIELD(_dbObject, offset_in_bytes_);
  FIELD(_dbObject, oid_);

  type("_dbFreeObject (free-slot overlay)", sizeof(_dbFreeObject));
  FIELD(_dbFreeObject, next_);
  FIELD(_dbFreeObject, prev_);

  type("Rect / Oct / Point", 0);
  std::printf("  Rect=%zu Oct=%zu Point=%zu union_dbBoxShape=%zu\n",
              sizeof(Rect),
              sizeof(Oct),
              sizeof(Point),
              sizeof(_dbBox::dbBoxShape));

  type("_dbBox", sizeof(_dbBox));
  FIELD(_dbBox, offset_in_bytes_);
  FIELD(_dbBox, oid_);
  FIELD(_dbBox, flags_);
  FIELD(_dbBox, shape_);
  FIELD(_dbBox, owner_);
  FIELD(_dbBox, next_box_);
  FIELD(_dbBox, design_rule_width_);

  type("_dbSBox", sizeof(_dbSBox));
  FIELD(_dbSBox, sflags_);

  type("_dbITerm", sizeof(_dbITerm));
  FIELD(_dbITerm, offset_in_bytes_);
  FIELD(_dbITerm, oid_);
  FIELD(_dbITerm, flags_);
  FIELD(_dbITerm, ext_id_);
  FIELD(_dbITerm, net_);
  FIELD(_dbITerm, mnet_);
  FIELD(_dbITerm, inst_);
  FIELD(_dbITerm, next_net_iterm_);
  FIELD(_dbITerm, prev_net_iterm_);
  FIELD(_dbITerm, next_modnet_iterm_);
  FIELD(_dbITerm, prev_modnet_iterm_);
  FIELD(_dbITerm, sta_vertex_id_);

  type("_dbInst", sizeof(_dbInst));
  type("_dbNet", sizeof(_dbNet));
  return 0;
}
