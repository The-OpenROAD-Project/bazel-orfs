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
_CHECK_SMOKE = "//test/coremark_joule/scripts:check_smoke"
_CM_PER_MHZ = "//test/coremark_joule/scripts:cm_per_mhz"

def coremark_hex(name, elf, words = 32768, base = 0, tags = ["manual"]):
    """Flatten an ELF into a $readmemh image.

    Args:
      name: target name; the image is `<name>.hex`.
      elf: the ELF to flatten.
      words: size of the memory array, in 32-bit words.
      base: address of the array's first word. Zero for the flat map
        every core but VeeR shares; VeeR's external memory is at
        0x80000000, and its data sections load there while running in a
        DCCM the harness cannot reach.
      tags: forwarded; manual.
    """
    native.genrule(
        name = name,
        srcs = [elf],
        outs = [name + ".hex"],
        cmd = "$(execpath {elf2hex}) $(execpath {elf}) $@ --words {words} --base {base}".format(
            base = base,
            elf = elf,
            elf2hex = _ELF2HEX,
            words = words,
        ),
        tags = tags,
        tools = [_ELF2HEX],
    )

def coremark_run(
        name,
        sim,
        image,
        max_cycles = 2000000000,
        bus_probe = False,
        tags = ["manual"]):
    """Run one image on one simulator; emit its stdout and cycle count.

    A trap or an exhausted cycle budget fails the action, so a broken run
    can never reach the arithmetic downstream as a plausible-looking
    number.

    Args:
      name: target name.
      sim: the simulator binary.
      image: the $readmemh image.
      max_cycles: the budget; exhausting it fails the run.
      bus_probe: also emit `<name>.busprobe`, the wrapper's count of
        transfers on each external bus. Only wrappers that handle
        `+busprobe=` can satisfy it -- today that is VeeR, where the
        instruction bus carries only cache misses and the count is what
        makes "CoreMark fits in the instruction cache" a number.
      tags: forwarded; manual.
    """
    outs = [
        name + ".stdout",
        name + ".cycles",
    ]
    probe_arg = ""
    if bus_probe:
        outs.append(name + ".busprobe")
        probe_arg = " +busprobe=$(location {}.busprobe)".format(name)

    native.genrule(
        name = name,
        srcs = [image],
        outs = outs,
        cmd = (
            "$(execpath {sim}) " +
            "+meminit=$(execpath {image}) " +
            "+stdout=$(location {name}.stdout) " +
            "+cycles=$(location {name}.cycles) " +
            "+max_cycles={max_cycles}{probe}"
        ).format(
            image = image,
            max_cycles = max_cycles,
            name = name,
            probe = probe_arg,
            sim = sim,
        ),
        tags = tags,
        tools = [sim],
    )

def bus_traffic(name, run_2, run_3, per_mhz, bus_bytes, tags = ["manual"]):
    """What one CoreMark iteration costs on the external bus.

    The same differential the cycle count uses: the traffic a third
    iteration adds over a second. It cancels the boot, the copy into the
    hardened memories and the cold pass that fills a cache, and what is
    left is what one hot iteration -- the SAIF window -- sends outside
    the boundary. Zero is the answer the energy number needs.

    Args:
      name: target name; the summary is `<name>.json`.
      run_2: the two-iteration coremark_run(), which must have been
        declared with bus_probe = True.
      run_3: the three-iteration one.
      per_mhz: the coremark_per_mhz() json, to express the traffic per
        kilocycle as well as per iteration.
      bus_bytes: width of one transfer. 8 for VeeR's AHB-Lite ports, 4
        for the external port the three cacheless tiles present.
      tags: forwarded; manual.
    """
    native.genrule(
        name = name,
        srcs = [
            "{}.busprobe".format(run_2),
            "{}.busprobe".format(run_3),
            "{}.json".format(per_mhz),
        ],
        outs = [name + ".json"],
        cmd = ("$(execpath //test/coremark_joule/scripts:bus_probe) " +
               "--probe-2 $(location {run_2}.busprobe) " +
               "--probe-3 $(location {run_3}.busprobe) " +
               "--per-mhz $(location {per_mhz}.json) " +
               "--bus-bytes {bus_bytes} " +
               "--out $@").format(
            bus_bytes = bus_bytes,
            per_mhz = per_mhz,
            run_2 = run_2,
            run_3 = run_3,
        ),
        tags = tags,
        tools = ["//test/coremark_joule/scripts:bus_probe"],
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

def smoke_test(name, run, tags = []):
    """Gate a core on the boot/load-store smoke run.

    Below the CRC gate on purpose: a core that fails this has a wrapper
    or boot problem, and one that passes it and then fails the CRCs has a
    different problem. Keeping them apart is what turned "ibex produces
    no output" into "ibex starts at boot_addr + 0x80".
    """
    sh_test(
        name = name,
        srcs = ["//test/coremark_joule/scripts:run_check.sh"],
        args = [
            "$(location {})".format(_CHECK_SMOKE),
            "$(location {}.stdout)".format(run),
        ],
        data = [
            _CHECK_SMOKE,
            "{}.stdout".format(run),
        ],
        tags = tags,
    )

def coremark_saif(
        name,
        sim,
        image,
        run_2,
        run_3,
        constraints,
        max_other_dropped = 0,
        tags = ["manual"]):
    """Capture a SAIF over CoreMark's last, hot iteration.

    The window comes from the two RTL runs rather than from a choice:
    the last iteration ends where the benchmark's first output appears
    and is one `cycles_3 - cycles_2` long. Measured on the fast
    simulation, applied to the slow one.

    Args:
      name: target name; the SAIF is `<name>.saif`.
      sim: the gate-level simulator to run.
      image: the three-iteration memory image.
      run_2: the two-iteration RTL run, for its cycle count.
      run_3: the three-iteration RTL run, for its cycle count and the
        cycle its first output appeared.
      constraints: the design's constraints.sdc, read for the period
        the SAIF is timed against. It used to be a literal here with a
        comment saying it must equal the SDC's period, and it stopped
        being equal the moment auto_period re-derived the periods: every
        SAIF was then timed against the old clock. A SAIF records real
        time and OpenSTA reads it as transitions divided by duration, so
        the toggle rates -- and the dynamic power -- came out wrong by
        the ratio between the two periods, by as much as 2.14x. Nothing
        downstream could detect it, which is why it is read from the one
        file that states the period rather than copied next to a warning
        not to let the copy drift.
      max_other_dropped: how many non-clock nets this design loses to
        scripts/filter_saif.py. Zero asserts that everything the SAIF
        format cannot carry is a clock net, which §3.5 establishes needs
        no annotation.
      tags: forwarded; manual.
    """
    raw = name + "_raw.saif"
    native.genrule(
        name = name + "_raw",
        srcs = [
            image,
            "{}.cycles".format(run_2),
            "{}.cycles".format(run_3),
            constraints,
        ],
        outs = [raw],
        cmd = (
            "$(execpath {win}) " +
            "--sim $(execpath {sim}) " +
            "--image $(location {image}) " +
            "--cycles-2 $(location {run_2}.cycles) " +
            "--cycles-3 $(location {run_3}.cycles) " +
            "--saif $(location {raw}) " +
            "--clk-period-from-sdc $(location {constraints})"
        ).format(
            constraints = constraints,
            image = image,
            raw = raw,
            run_2 = run_2,
            run_3 = run_3,
            sim = sim,
            win = "//test/coremark_joule/scripts:saif_window",
        ),
        tags = tags,
        tools = [
            sim,
            "//test/coremark_joule/scripts:saif_window",
        ],
    )

    # A SAIF cannot carry a net name containing `/` -- that is the
    # hierarchy separator, and OpenSTA's lexer has no escape that lets a
    # name hold one. Hierarchical CTS produces such names, and read_saif
    # stops at the first with a parse error, annotating nothing at all.
    # Dropping them is what turns a total loss into a bounded one.
    native.genrule(
        name = name,
        srcs = [raw],
        outs = [name + ".saif"],
        cmd = " ".join([
            "$(execpath //test/coremark_joule/scripts:filter_saif)",
            "$(location {})".format(raw),
            "$@",
            "--max-other {}".format(max_other_dropped),
        ]),
        tags = tags,
        tools = ["//test/coremark_joule/scripts:filter_saif"],
    )

def coremark_per_joule(
        name,
        per_mhz,
        power,
        core,
        isa,
        constraints,
        boundary,
        tags = ["manual"]):
    """Combine performance, frequency and power into one pinned point.

    Args:
      name: target name; the point is `<name>.json`.
      per_mhz: the *_per_mhz.json.
      power: the stage_power() target; both its arms are read.
      core: core name, for the plot's label.
      isa: the -march the ELF was built with.
      constraints: the design's constraints.sdc. The reported frequency
        is read from its `set clk_period`, so the period the design was
        built at and the frequency its energy is divided by cannot
        disagree -- they did, and the study reported ibex at a frequency
        its netlist missed by 74 ps. auto_period pins the period; this
        makes the frequency follow.
      boundary: what the hardened block contains. Mandatory, because
        the boundary rule is the study's central claim and a point that
        does not meet it has to say so next to its own number rather
        than in a study-wide footnote that stops being true the moment
        one point does meet it. Single-quoted into the shell below, so
        it must not contain an apostrophe.
      tags: forwarded; manual.
    """
    native.genrule(
        name = name,
        srcs = [
            per_mhz,
            power + "_vector_driven.json",
            power + "_vectorless.json",
            constraints,
        ],
        outs = [name + ".json"],
        cmd = (
            "$(execpath {bin}) " +
            "--per-mhz $(location {per_mhz}) " +
            "--power $(location {power}_vector_driven.json) " +
            "--vectorless-power $(location {power}_vectorless.json) " +
            "--frequency-from-sdc $(location {constraints}) " +
            "--core {core} --isa {isa} --boundary '{boundary}' --out $@"
        ).format(
            bin = "//test/coremark_joule/scripts:cm_per_joule",
            boundary = boundary,
            constraints = constraints,
            core = core,
            isa = isa,
            per_mhz = per_mhz,
            power = power,
        ),
        tags = tags,
        tools = ["//test/coremark_joule/scripts:cm_per_joule"],
    )
