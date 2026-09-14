/* CoreMark port layer: seeds, the stubbed timer, and init/fini.
 *
 * See core_portme.h for why the timer is a constant and why ITERATIONS
 * is a compile-time value.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#include "coremark.h"
#include "sim_ctrl.h"

#if VALIDATION_RUN
volatile ee_s32 seed1_volatile = 0x3415;
volatile ee_s32 seed2_volatile = 0x3415;
volatile ee_s32 seed3_volatile = 0x66;
#endif
#if PERFORMANCE_RUN
volatile ee_s32 seed1_volatile = 0x0;
volatile ee_s32 seed2_volatile = 0x0;
volatile ee_s32 seed3_volatile = 0x66;
#endif
#if PROFILE_RUN
volatile ee_s32 seed1_volatile = 0x8;
volatile ee_s32 seed2_volatile = 0x8;
volatile ee_s32 seed3_volatile = 0x8;
#endif

#ifndef ITERATIONS
#error "ITERATIONS must be set at compile time; a zero iteration count sends core_main.c into its ten-second self-tuning loop."
#endif

/* The one word of .data that differs between the two-iteration and the
 * three-iteration binary. Volatile, so the compiler cannot fold the
 * count into the generated code and the two ELFs stay identical
 * everywhere else -- which is the premise the cycle subtraction rests
 * on. */
volatile ee_s32 seed4_volatile = ITERATIONS;
volatile ee_s32 seed5_volatile = 0;

ee_u32 default_num_contexts = 1;

/* Timing: deliberately inert.
 *
 * Cycles are counted by the harness, over the whole run to the halt
 * write, and the per-iteration cost is the difference between two runs.
 * A real timer here would buy nothing and cost something: the tick value
 * would differ between the two runs, the report lines would differ in
 * width, and the difference in ee_printf work would land inside the
 * subtraction.
 *
 * EE_TICKS_PER_SEC is 1 and get_time() returns 1, so time_in_secs() is
 * 1 for both runs. CoreMark then prints its "must execute for at least
 * 10 secs" error in both, and total_errors is non-zero in both. That is
 * expected and is why the pass/fail gate is the CRC lines rather than
 * CoreMark's own error count -- see scripts/check_coremark.py.
 */
#define EE_TICKS_PER_SEC 1

void start_time(void)
{
}

void stop_time(void)
{
}

CORE_TICKS get_time(void)
{
    return (CORE_TICKS)1;
}

secs_ret time_in_secs(CORE_TICKS ticks)
{
    return (secs_ret)ticks / (secs_ret)EE_TICKS_PER_SEC;
}

void portable_init(core_portable *p, int *argc, char *argv[])
{
    (void)argc;
    (void)argv;

    if (sizeof(ee_ptr_int) != sizeof(ee_u8 *))
    {
        ee_printf(
            "ERROR! Please define ee_ptr_int to a type that holds a "
            "pointer!\n");
    }
    if (sizeof(ee_u32) != 4)
    {
        ee_printf("ERROR! Please define ee_u32 to a 32b unsigned type!\n");
    }
    p->portable_id = 1;
}

void portable_fini(core_portable *p)
{
    p->portable_id = 0;
    /* Stopping the clock here rather than returning through crt0 means
     * the cycle count ends at the same instruction in every run, on
     * every core, whatever the compiler did with main's epilogue. */
    sim_halt();
}
