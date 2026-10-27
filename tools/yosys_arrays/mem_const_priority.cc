// mem_const_priority: drop the priority between memory write ports whose
// addresses are distinct constants, before opt_mem_priority asks a SAT
// solver the same question pair by pair.
//
// An array whose every entry is updated in place (a counter, a flag, a
// ROB entry) written as an unpacked array is a memory with one write
// port per entry, each at a constant address. opt_mem_priority builds one
// QuickConeSat for the memory and solves every ordered pair of ports in
// it: on test/array_toys's counter, 96 % of `memory -nomap`, 74 s at 256
// entries. Two constant addresses that differ never collide; that needs
// no solver.

#include "kernel/mem.h"
#include "kernel/yosys.h"

USING_YOSYS_NAMESPACE
PRIVATE_NAMESPACE_BEGIN

struct MemConstPriorityPass : public Pass
{
  MemConstPriorityPass()
      : Pass("mem_const_priority",
             "drop write priority between ports at distinct constant addresses")
  {
  }

  void help() override
  {
    log("\n");
    log("    mem_const_priority [selection]\n");
    log("\n");
    log("Removes the priority relation between two memory write ports whose\n");
    log("addresses are both constant and differ: they can never write the same\n");
    log("word. Run before memory (opt_mem_priority) on a memory with many ports.\n");
    log("\n");
  }

  void execute(std::vector<std::string> args, Design* design) override
  {
    log_header(design, "Executing MEM_CONST_PRIORITY pass.\n");
    extra_args(args, 1, design);
    int dropped = 0;
    for (auto module : design->selected_modules()) {
      for (auto& mem : Mem::get_selected_memories(module)) {
        bool changed = false;
        for (auto& w1 : mem.wr_ports) {
          if (!w1.addr.is_fully_const()) {
            continue;
          }
          for (int j = 0; j < GetSize(mem.wr_ports); j++) {
            auto& w2 = mem.wr_ports[j];
            if (!w1.priority_mask[j] || !w2.addr.is_fully_const()
                || w1.wide_log2 != w2.wide_log2) {
              continue;
            }
            // a wide port covers 2^wide_log2 words from its aligned address
            int shift = w1.wide_log2;
            if ((w1.addr.as_const().as_int() >> shift)
                != (w2.addr.as_const().as_int() >> shift)) {
              w1.priority_mask[j] = false;
              changed = true;
              dropped++;
            }
          }
        }
        if (changed) {
          mem.emit();
        }
      }
    }
    log("Dropped %d priority relations between distinct constant addresses.\n",
        dropped);
  }
} MemConstPriorityPass;

PRIVATE_NAMESPACE_END
