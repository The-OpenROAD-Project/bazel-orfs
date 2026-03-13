#include <gtest/gtest.h>
#include <verilated.h>
#include <verilated_vcd_c.h>
#include <memory>
#include <string>

// Verilator generates headers from the top module name.
// The BUILD rule defines MODULE_TOP via local_defines.
#define STR1(x) #x
#define STR(x) STR1(x)
#define CAT(a, b) CAT_I(a, b)
#define CAT_I(a, b) a##b
#define INCFILE(name) STR(CAT(V, name).h)
#define VMODCLASS(name) CAT(V, name)

#include INCFILE(MODULE_TOP)

// The Chisel testbench wrapper (CountTo42CpuTestBench) exposes
// signals as "done"/"result", while the standalone rewrite module
// (CountTo42Cpu) exposes them as "io_done"/"io_result".
// Use accessor macros to abstract this difference.
#ifdef TESTBENCH_WRAPPER
  #define DONE(top) (top).done
  #define RESULT(top) (top).result
#else
  #define DONE(top) (top).io_done
  #define RESULT(top) (top).io_result
#endif

class CpuHarness {
public:
  VerilatedContext ctx;
  VMODCLASS(MODULE_TOP) top;
  std::unique_ptr<VerilatedVcdC> trace;
  uint64_t cycle_count = 0;

  explicit CpuHarness(const std::string &vcd_file) {
    ctx.traceEverOn(true);
    trace = std::make_unique<VerilatedVcdC>();
    top.trace(trace.get(), 99);
    trace->open(vcd_file.c_str());
  }

  ~CpuHarness() { trace->close(); }

  void step() {
    ctx.timeInc(1);
    top.clock = 1;
    top.eval();
    trace->dump(ctx.time());

    ctx.timeInc(1);
    top.clock = 0;
    top.eval();
    trace->dump(ctx.time());

    cycle_count++;
  }

  void reset(int cycles = 10) {
    top.reset = 1;
    for (int i = 0; i < cycles; i++) {
      step();
    }
    top.reset = 0;
  }

  bool run_until_done(uint64_t max_cycles = 10000) {
    for (uint64_t i = 0; i < max_cycles; i++) {
      step();
      if (DONE(top))
        return true;
    }
    return false;
  }
};

static std::string vcd_path(const char *test_name) {
  const char *output_dir = std::getenv("TEST_UNDECLARED_OUTPUTS_DIR");
  if (output_dir)
    return std::string(output_dir) + "/" + test_name + ".vcd";
  return std::string(test_name) + ".vcd";
}

TEST(CountTo42Cpu, CountsTo42) {
  CpuHarness h(vcd_path("CountsTo42"));
  h.reset();

  bool finished = h.run_until_done();
  ASSERT_TRUE(finished) << "CPU did not halt within cycle limit";
  ASSERT_EQ(RESULT(h.top), 42u) << "Expected register x1 == 42";

  // 2 LI + 42 ADDI + 42 BNE + 1 HALT = 87 instructions, 1 cycle each
  EXPECT_LE(h.cycle_count, 200u) << "Took too many cycles";
}

TEST(CountTo42Cpu, ResetClearsState) {
  CpuHarness h(vcd_path("ResetClearsState"));
  h.reset();

  for (int i = 0; i < 5; i++)
    h.step();

  EXPECT_NE(RESULT(h.top), 42u);
  EXPECT_FALSE(DONE(h.top));

  h.reset();

  h.step();
  EXPECT_EQ(RESULT(h.top), 0u);
  EXPECT_FALSE(DONE(h.top));
}
