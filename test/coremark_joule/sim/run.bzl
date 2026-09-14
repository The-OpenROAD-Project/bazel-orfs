"""Run a CoreMark image on a core's simulator and record what happened.

Each run produces two declared outputs -- the captured stdout and the
cycle count -- because they answer different questions and are gated
separately. The CRCs in stdout say whether the core computed the right
answer; the cycle count is only meaningful once they have.

The program reaches the simulator as a +meminit= plusarg, so one
simulator binary serves every image. The gate-level simulators are
expensive to build and this is what keeps that cost per stage rather
than per program.
"""

load("@rules_shell//shell:sh_test.bzl", "sh_test")

_ELF2HEX = "//test/coremark_joule/scripts:elf2hex"
_CHECK = "//test/coremark_joule/scripts:check_coremark"
_CM_PER_MHZ = "//test/coremark_joule/scripts:cm_per_mhz"

def coremark_hex(name, elf, words = 32768, tags = ["manual"]):
    """Flatten an ELF into a $readmemh image."""
    native.genrule(
        name = name,
        srcs = [elf],
        outs = [name + ".hex"],
        cmd = "$(execpath {elf2hex}) $(execpath {elf}) $@ --words {words}".format(
            elf = elf,
            elf2hex = _ELF2HEX,
            words = words,
        ),
        tags = tags,
        tools = [_ELF2HEX],
    )

def coremark_run(name, sim, image, max_cycles = 2000000000, tags = ["manual"]):
    """Run one image on one simulator; emit its stdout and cycle count.

    A trap or an exhausted cycle budget fails the action, so a broken run
    can never reach the arithmetic downstream as a plausible-looking
    number.
    """
    native.genrule(
        name = name,
        srcs = [image],
        outs = [
            name + ".stdout",
            name + ".cycles",
        ],
        cmd = (
            "$(execpath {sim}) " +
            "+meminit=$(execpath {image}) " +
            "+stdout=$(location {name}.stdout) " +
            "+cycles=$(location {name}.cycles) " +
            "+max_cycles={max_cycles}"
        ).format(
            image = image,
            max_cycles = max_cycles,
            name = name,
            sim = sim,
        ),
        tags = tags,
        tools = [sim],
    )

def coremark_crc_test(name, run, tags = []):
    """Gate a run on CoreMark's CRCs.

    Deliberately a test rather than a step inside coremark_run: a wrong
    answer and a failed run are different events, and keeping them apart
    means the cycle count still exists to look at when the CRCs fail.
    """
    sh_test(
        name = name,
        srcs = ["//test/coremark_joule/scripts:run_check.sh"],
        args = [
            "$(location {})".format(_CHECK),
            "$(location {}.stdout)".format(run),
        ],
        data = [
            _CHECK,
            "{}.stdout".format(run),
        ],
        tags = tags,
    )

def coremark_per_mhz(name, run_2, run_3, tags = ["manual"]):
    """CoreMark/MHz from the two- and three-iteration cycle counts.

    1e6 / (cycles_3 - cycles_2). The subtraction is one CoreMark
    iteration and cancels reset, .bss zeroing, data init, the CRC checks
    and the whole report -- which is why the benchmark never has to run
    for the ten seconds its own self-timing loop would demand.
    """
    native.genrule(
        name = name,
        srcs = [
            "{}.cycles".format(run_2),
            "{}.cycles".format(run_3),
            "{}.stdout".format(run_3),
        ],
        outs = [name + ".json"],
        cmd = (
            "$(execpath {cm}) " +
            "--cycles-2 $(location {run_2}.cycles) " +
            "--cycles-3 $(location {run_3}.cycles) " +
            "--report $(location {run_3}.stdout) " +
            "--out $@"
        ).format(
            cm = _CM_PER_MHZ,
            run_2 = run_2,
            run_3 = run_3,
        ),
        tags = tags,
        tools = [_CM_PER_MHZ],
    )
