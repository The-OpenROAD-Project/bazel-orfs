#define STR1(x) #x
#define STR(x) STR1(x)
#define CAT(a, b) CAT_I(a, b)
#define CAT_I(a, b) a##b
#define INCFILE(name) STR(CAT(V, name).h)
#define VMODCLASS(name) CAT(V, name)

#include INCFILE(MODULE_TOP)
#include <exception>
#include <iostream>
#include <string>
#include <verilated_vcd_c.h>

void run(const std::string &file) {
  VerilatedContext ctx;
  VMODCLASS(MODULE_TOP) top;
  auto trace = std::make_unique<VerilatedVcdC>();
  ctx.traceEverOn(true);
  top.trace(trace.get(), 100);
  trace->open(file.c_str());

  while (true) {

    top.reset = ctx.time() < (10 * 2);
    ctx.timeInc(1);
    top.clock = 1;
    top.eval();
    trace->dump(ctx.time());

    ctx.timeInc(1);
    top.clock = 0;
    top.eval();
    trace->dump(ctx.time());

    if (top.done) {
      break;
    }
  }
}

int main(int argc, const char **argv, const char **envp) {
  try {
    run(argv[1]);
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "ERROR: " << e.what() << "\n";
    return 1;
  } catch (...) {
    std::cerr << "ERROR: Unknown exception caught\n";
    return 1;
  }
}
