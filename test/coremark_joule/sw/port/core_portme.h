/* CoreMark port layer for the sim-control bare-metal platform.
 *
 * CoreMark is built here from unmodified upstream sources. Everything
 * this study needs lives in the port layer, which is the surface
 * CoreMark's own barebones_porting.md tells you to write: core_portme.c,
 * core_portme.h and ee_printf.c all ship upstream as templates whose
 * platform-specific bodies are `#error` stubs.
 *
 * That is a licence constraint as much as a design one. CoreMark's
 * Acceptable Use Agreement forbids using the trademark in connection
 * with a modified copy of the Software, so the Software stays byte-exact
 * and the platform lives entirely in files like this one.
 *
 * Two choices here drive the whole measurement:
 *
 *   ITERATIONS is set at compile time, so results[0].iterations is never
 *   zero and core_main.c's self-tuning loop -- the one that doubles the
 *   iteration count until ten seconds of wall clock have passed -- never
 *   runs. Ten seconds of wall clock is not a thing an RTL simulation of
 *   a bit-serial core can be asked for.
 *
 *   The timer is a constant. The study derives cycles per iteration by
 *   subtracting a two-iteration run from a three-iteration run, counting
 *   cycles in the harness rather than in the core, so nothing in here
 *   needs to read a cycle counter -- and a constant keeps the two runs'
 *   stdout byte-identical except for the iteration digit, which is what
 *   makes the subtraction exactly one iteration rather than one
 *   iteration plus a difference in printf work.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef CORE_PORTME_H
#define CORE_PORTME_H

/* No FPU is assumed anywhere in the study: SERV has no F extension, and
 * a soft-float CoreMark report would put libgcc's float formatting on
 * the measured path for no benefit. With HAS_FLOAT 0 the %f report lines
 * in core_main.c compile out. */
#define HAS_FLOAT   0
#define HAS_TIME_H  0
#define USE_CLOCK   0
#define HAS_STDIO   0
#define HAS_PRINTF  0

#ifndef COMPILER_VERSION
#define COMPILER_VERSION "GCC" __VERSION__
#endif
#ifndef COMPILER_FLAGS
#define COMPILER_FLAGS FLAGS_STR
#endif
#ifndef MEM_LOCATION
#define MEM_LOCATION "STATIC"
#endif

typedef signed short   ee_s16;
typedef unsigned short ee_u16;
typedef signed int     ee_s32;
typedef double         ee_f32;
typedef unsigned char  ee_u8;
typedef unsigned int   ee_u32;

/* An integer wide enough to hold a pointer, and a size type to match.
 *
 * CoreMark checks this at run time -- core_main.c prints "Please define
 * ee_ptr_int to a type that holds a pointer" and stops -- so getting it
 * wrong on RV64 is caught, but only after a simulated boot. RV32's
 * pointers are 32 bits and RV64's are 64, and __riscv_xlen is the
 * compiler's own answer to which this is. ee_u32 stays 32 bits either
 * way: it is a benchmark data type, not an address. */
#if __riscv_xlen == 64
typedef unsigned long ee_ptr_int;
typedef unsigned long ee_size_t;
#else
typedef ee_u32        ee_ptr_int;
typedef unsigned int  ee_size_t;
#endif

#define NULL ((void *)0)

#define align_mem(x) (void *)(4 + (((ee_ptr_int)(x) - 1) & ~3))

#define CORETIMETYPE ee_u32
typedef ee_u32 CORE_TICKS;

/* Seeds come from volatile globals in core_portme.c. SEED_ARG would
 * need argv, which MAIN_HAS_NOARGC rules out; SEED_FUNC would need a
 * clock. Volatile is also what keeps the two iteration-count binaries
 * differing by a single word of .data instead of by generated code. */
#define SEED_METHOD SEED_VOLATILE

/* The data block is a static array rather than malloc (no heap here) or
 * the stack (CoreMark marks MEM_STACK not-yet-implemented). */
#define MEM_METHOD MEM_STATIC

#define MULTITHREAD 1
#define USE_PTHREAD 0
#define USE_FORK    0
#define USE_SOCKET  0

#define MAIN_HAS_NOARGC  1
#define MAIN_HAS_NORETURN 0

/* TOTAL_DATA_SIZE 2000 selects CoreMark's 2K performance profile:
 * seeds 0/0/0x66 over 666 bytes per algorithm, seedcrc 0xe9f5, which is
 * known_id 3 in core_main.c's tables. The expected CRCs for that profile
 * are list 0xe714, matrix 0x1fd7, state 0x8e3a -- the values
 * scripts/check_coremark.py gates on. */
#ifndef TOTAL_DATA_SIZE
#define TOTAL_DATA_SIZE 2000
#endif

/* Which run profile the seeds and CRCs belong to follows from
 * TOTAL_DATA_SIZE, exactly as CoreMark's own barebones header derives
 * it, so a caller changing the data size cannot end up with seeds from
 * one profile and expected CRCs from another. */
#if !defined(PROFILE_RUN) && !defined(PERFORMANCE_RUN) \
    && !defined(VALIDATION_RUN)
#if (TOTAL_DATA_SIZE == 1200)
#define PROFILE_RUN 1
#elif (TOTAL_DATA_SIZE == 2000)
#define PERFORMANCE_RUN 1
#else
#define VALIDATION_RUN 1
#endif
#endif

extern ee_u32 default_num_contexts;

typedef struct CORE_PORTABLE_S
{
    ee_u8 portable_id;
} core_portable;

void portable_init(core_portable *p, int *argc, char *argv[]);
void portable_fini(core_portable *p);

int ee_printf(const char *fmt, ...);

#endif /* CORE_PORTME_H */
