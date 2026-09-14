/* Does this core run anything at all?
 *
 * A gate below CoreMark, and the reason it exists: when ibex first ran
 * CoreMark it produced no output and no trap, which is indistinguishable
 * from a hang, a bad image and a broken bus adapter. This program
 * separates them. It prints a fixed string, exercises a load/store loop,
 * and halts -- so a core that fails it has a wrapper or boot problem,
 * and a core that passes it and then fails CoreMark's CRCs has a
 * different problem entirely.
 *
 * It found a real one: ibex fetches its first instruction from
 * boot_addr_i + 0x80, not boot_addr_i, so the core had been starting
 * 0x80 bytes into .text and executing whatever was there.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#include "sim_ctrl.h"

static volatile int acc;

int main(void)
{
    const char *m = "HELLO\n";
    while (*m) {
        sim_putchar(*m++);
    }

    /* A load/store loop with a known answer: 0+1+...+99 == 4950. Reading
     * back the wrong sum is how a broken byte-enable or a mis-wired read
     * path shows up, and it is silent in a string that only ever gets
     * written. */
    for (int i = 0; i < 100; i++) {
        acc += i;
    }
    sim_putchar(acc == 4950 ? 'M' : 'X');
    sim_putchar('\n');

    sim_halt();
    return 0;
}
