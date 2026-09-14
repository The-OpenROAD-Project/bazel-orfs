"""Build a CoreMark ELF for one core, one ISA and one iteration count.

A genrule around one compiler invocation, deliberately, rather than a
cc_binary on a cc_toolchain. The study's question is which flags produce
the fewest cycles on each core, so the flag list has to be the visible
input of the rule that the sweep varies. A toolchain would bury it.

Two ELFs are built per configuration, at ITERATIONS=2 and ITERATIONS=3.
CoreMark's cost per iteration is the difference in cycles between them,
which cancels reset, .bss zeroing, data init, the CRC checks and the
whole report -- everything that is not the benchmark. That is also why
the ten-second self-timing loop in core_main.c never has to run.
"""

_COREMARK_SRCS = "@coremark//:srcs"
_COREMARK_HDRS = "@coremark//:hdrs"
_GCC = "@riscv_none_elf_gcc//:bin/riscv-none-elf-gcc"
_TOOLCHAIN = "@riscv_none_elf_gcc//:all"

# The port layer: the platform half of the build, written here because
# CoreMark ships these as `#error` stubs.
_PORT_SRCS = [
    "//test/coremark_joule/sw/port:core_portme.c",
    "//test/coremark_joule/sw/port:ee_printf.c",
    "//test/coremark_joule/sw/port:crt0.S",
]

_PORT_HDRS = [
    "//test/coremark_joule/sw/port:core_portme.h",
    "//test/coremark_joule/sw/port:sim_ctrl.h",
]

_LINK_LD = "//test/coremark_joule/sw/port:link.ld"

# Fixed for every configuration in the study. These are not sweep axes:
# there is no libc and no startup code but ours, and -mstrict-align is
# required because picorv32 and SERV both trap misaligned access.
_FIXED_CFLAGS = [
    "-nostdlib",
    "-nostartfiles",
    "-ffreestanding",
    "-mstrict-align",
    "-DTOTAL_DATA_SIZE=2000",
]

def coremark_elf(
        name,
        iterations,
        march,
        cflags,
        mabi = "ilp32",
        tags = ["manual"],
        visibility = None):
    """Compile and link one CoreMark ELF.

    Args:
      name: target name; the ELF is `<name>.elf`.
      iterations: CoreMark's iteration count, baked in at compile time so
        core_main.c's self-tuning loop is never reached. Only the two
        values 2 and 3 are used by the study; both produce the same CRCs,
        because CoreMark captures crclist on the first iteration and
        crcmatrix/crcstate on their first call.
      march: RISC-V ISA string, e.g. "rv32i" or "rv32im". Must be an ISA
        the core actually implements -- nothing here checks that, but the
        CRC gate will fail loudly on an illegal-instruction trap.
      cflags: the swept flags (optimisation, unrolling, inlining,
        alignment, tuning). Reported verbatim in CoreMark's own output
        via FLAGS_STR, so a captured stdout says how it was built.
      mabi: RISC-V ABI string.
      tags: forwarded; manual by default -- this is study apparatus.
      visibility: forwarded.
    """
    arch_flags = [
        "-march=" + march,
        "-mabi=" + mabi,
    ]

    # What CoreMark prints as COMPILER_FLAGS. Single-quoted in the shell
    # below, so a flag containing a single quote would break the build;
    # no compiler flag does.
    flags_str = " ".join(arch_flags + cflags)

    compile_flags = arch_flags + cflags + _FIXED_CFLAGS + [
        "-DITERATIONS={}".format(iterations),
    ]

    native.genrule(
        name = name,
        srcs = [
            _COREMARK_SRCS,
            _COREMARK_HDRS,
            _LINK_LD,
        ] + _PORT_SRCS + _PORT_HDRS,
        outs = [name + ".elf"],
        cmd = (
            "$(execpath {gcc}) {flags} " +
            # Headers are found by directory, so both the benchmark's own
            # and the port's have to be on the include path; coremark.h
            # includes core_portme.h by name.
            "-I $$(dirname $(execpath {hdrs})) " +
            "-I $$(dirname $(execpath {portme_h})) " +
            "-DFLAGS_STR='\"{flags_str}\"' " +
            "$(execpaths {srcs}) {port_srcs} " +
            "-T $(execpath {link_ld}) " +
            # libgcc supplies __mulsi3 and friends, which rv32i needs and
            # which are on CoreMark's hot path. Linking our own would make
            # a no-multiplier core's score a measurement of that routine.
            "-lgcc " +
            # Bare metal has one LOAD segment and it is legitimately RWX.
            "-Wl,--no-warn-rwx-segments " +
            "-o $@"
        ).format(
            flags = " ".join(compile_flags),
            flags_str = flags_str,
            gcc = _GCC,
            hdrs = _COREMARK_HDRS,
            link_ld = _LINK_LD,
            port_srcs = " ".join(["$(execpath {})".format(s) for s in _PORT_SRCS]),
            portme_h = _PORT_HDRS[0],
            srcs = _COREMARK_SRCS,
        ),
        tags = tags,
        tools = [
            _GCC,
            _TOOLCHAIN,
        ],
        visibility = visibility,
    )
