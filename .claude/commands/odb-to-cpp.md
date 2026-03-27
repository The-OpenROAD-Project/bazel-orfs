> **Repo**: Paths like `upstream/...` and `scripts/...` are relative to the openroad-demo root.

Convert an .odb file into a C++ header that reconstructs the design using odb API calls.

ARGUMENTS: $ARGUMENTS

## Usage

```bash
openroad -no_init -threads 1 -exit scripts/gen_cpp_from_odb.tcl <input.odb> [output.h]
```

Generates a C++ header file containing an inline function `gen::buildDesign(odb::dbDatabase* db)`
that reconstructs the ODB design programmatically. The output compiles with only `//src/odb`
and `//src/utl` deps — no LEF, DEF, LIB, or binary files needed.

## What it generates

- Tech layers (routing, cut, masterslice) with directions
- Library with cell masters, pins (MTerms) with IO/signal types
- Site definition
- Chip, block, die area
- All instances with placement
- All nets with ITerms and BTerms connected

## What it does NOT generate (yet)

- Pin geometry (shapes/boxes on layers)
- Track grids
- Routing (wires, vias)
- Timing constraints (SDC)
- Liberty timing data
- Rows

## Workflow for creating a C++ unit test from an .odb reproducer

1. Whittle the .odb to minimize the design:
   ```bash
   python3 upstream/OpenROAD-flow-scripts/tools/OpenROAD/etc/whittle.py \
     --base_db_path input.odb --error_string "ERROR_STRING" \
     --step "openroad -no_init -threads 1 -exit bug.tcl" \
     --persistence 3 --use_stdout --dump_def
   ```

2. Generate C++ from the whittled .odb:
   ```bash
   openroad -no_init -threads 1 -exit scripts/gen_cpp_from_odb.tcl whittled.odb generated_design.h
   ```

3. Write a C++ test that includes the generated header:
   ```cpp
   #include "generated_design.h"
   #include "gtest/gtest.h"
   #include "odb/db.h"

   struct DbDeleter {
     void operator()(odb::dbDatabase* db) { odb::dbDatabase::destroy(db); }
   };

   TEST(MyTest, ReproducesBug) {
     std::unique_ptr<odb::dbDatabase, DbDeleter> db(odb::dbDatabase::create());
     gen::buildDesign(db.get());
     // ... call the function that triggers the bug
   }
   ```

4. Add a cc_test target with minimal deps:
   ```starlark
   cc_test(
       name = "my_test",
       srcs = ["MyTest.cpp", "generated_design.h"],
       deps = ["//src/odb", "//src/utl", "@googletest//:gtest", "@googletest//:gtest_main"],
   )
   ```

5. Iterate: the test compiles in ~6 seconds.

## Important: dbDatabase lifetime

`dbDatabase::create()` allocates from a pool. Plain `delete` crashes.
Always use `dbDatabase::destroy()` or a custom deleter (see example above).
The test fixture in `src/tst/` uses `utl::UniquePtrWithDeleter` for the same reason.
