#include <verilated.h>

#include <cstdint>
#include <memory>

#include "Vcounter.h"
#include "gtest/gtest.h"

// Mode encoding matches counter_pkg::mode_t
enum Mode : uint8_t {
  IDLE = 0b00,
  COUNT = 0b01,
  HOLD = 0b10,
};

class CounterTest : public testing::Test {
 protected:
  std::unique_ptr<Vcounter> dut;

  void SetUp() override { dut = std::make_unique<Vcounter>(); }

  void TearDown() override { dut->final(); }

  void tick() {
    dut->clk = 0;
    dut->eval();
    dut->clk = 1;
    dut->eval();
  }

  void reset(int n = 2) {
    dut->rst = 1;
    dut->enable = 0;
    dut->mode_sel = IDLE;
    for (int i = 0; i < n; ++i) tick();
    dut->rst = 0;
  }
};

TEST_F(CounterTest, ResetClearsCount) {
  reset();
  EXPECT_EQ(dut->count, 0);
}

TEST_F(CounterTest, CountModeIncrements) {
  reset();
  dut->enable = 1;
  dut->mode_sel = COUNT;
  for (int i = 1; i <= 10; ++i) {
    tick();
    EXPECT_EQ(dut->count, static_cast<uint32_t>(i));
  }
}

TEST_F(CounterTest, HoldModeFreezesCount) {
  reset();
  dut->enable = 1;
  dut->mode_sel = COUNT;
  for (int i = 0; i < 5; ++i) tick();
  EXPECT_EQ(dut->count, 5u);

  dut->mode_sel = HOLD;
  for (int i = 0; i < 5; ++i) tick();
  EXPECT_EQ(dut->count, 5u);
}

TEST_F(CounterTest, IdleModeResetsToZero) {
  reset();
  dut->enable = 1;
  dut->mode_sel = COUNT;
  for (int i = 0; i < 3; ++i) tick();
  EXPECT_EQ(dut->count, 3u);

  dut->mode_sel = IDLE;
  tick();
  EXPECT_EQ(dut->count, 0u);
}

TEST_F(CounterTest, EnableGatesAllModes) {
  reset();
  dut->enable = 0;
  dut->mode_sel = COUNT;
  for (int i = 0; i < 5; ++i) tick();
  EXPECT_EQ(dut->count, 0u);

  dut->enable = 1;
  tick();
  EXPECT_EQ(dut->count, 1u);
}

TEST_F(CounterTest, ModeTransition) {
  reset();
  dut->enable = 1;

  // Count to 4
  dut->mode_sel = COUNT;
  for (int i = 0; i < 4; ++i) tick();
  EXPECT_EQ(dut->count, 4u);

  // Hold at 4
  dut->mode_sel = HOLD;
  for (int i = 0; i < 3; ++i) tick();
  EXPECT_EQ(dut->count, 4u);

  // Resume counting from 4
  dut->mode_sel = COUNT;
  tick();
  EXPECT_EQ(dut->count, 5u);
}
