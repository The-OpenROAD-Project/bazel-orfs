#include "VLifeUniverseTestBench.h"
#include <gmock/gmock-matchers.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <exception>
#include <iostream>
#include <string>
#include <verilated_vcd_c.h>

#include "VLifeUniverseTestBench.h"
#include <exception>
#include <gmock/gmock-matchers.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <iostream>
#include <memory>
#include <string>
#include <verilated.h>
#include <verilated_vcd_c.h>

class LifeUniverseHarness {
public:
  VerilatedContext ctx;
  VLifeUniverseTestBench top;
  std::unique_ptr<VerilatedVcdC> trace;

  LifeUniverseHarness(const std::string &vcd_file) {
    ctx.traceEverOn(true);
    trace = std::make_unique<VerilatedVcdC>();
    top.trace(trace.get(), 100);
    trace->open(vcd_file.c_str());
  }

  ~LifeUniverseHarness() { trace->close(); }

  // Simulate one clock cycle
  void step() {
    ctx.timeInc(1);
    top.clock = 1;
    top.eval();
    trace->dump(ctx.time());

    ctx.timeInc(1);
    top.clock = 0;
    top.eval();
    trace->dump(ctx.time());
  }

  // Run until done signal is set
  void run_until_done() {
    while (true) {
      top.reset = ctx.time() < (10 * 2);
      step();
      if (top.done)
        break;
    }
  }
};

TEST(LifeUniverse, DirectSignalTest) {
  // Use bazel env var to place file TEST_UNDECLARED_OUTPUTS_DIR
  const char *output_dir = std::getenv("TEST_UNDECLARED_OUTPUTS_DIR");
  std::string vcd_path = output_dir ? std::string(output_dir) + "/DirectSignalTest.vcd"
                                    : "DirectSignalTest.vcd";
  LifeUniverseHarness harness(vcd_path);

  // Directly set reset high, clock low, and evaluate
  harness.top.reset = 1;
  harness.top.clock = 0;
  harness.top.eval();

  ASSERT_EQ(harness.top.reset, 1);

  // Step one cycle
  harness.step();

  // Directly set reset low and evaluate
  harness.top.reset = 0;
  harness.top.eval();

  ASSERT_EQ(harness.top.reset, 0);

  // Run until done
  harness.run_until_done();

  // Check done signal
  ASSERT_EQ(harness.top.done, 1);
}
