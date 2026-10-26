"""Where a program's main thread spends its wall-clock time.

Runs a command with gperftools' CPU profiler preloaded in real-time mode
(CPUPROFILE_REALTIME=1: ITIMER_REAL, SIGALRM), so a sample is taken every
tick of elapsed time, on or off the CPU. The kernel delivers SIGALRM to the
main thread, so the profile is the main thread's: the time it waits in a
barrier for worker threads shows up as the barrier, not as nothing, which is
what perf's on-CPU samples miss. Serial work and waiting on parallel work are
then told apart by function.

    bazelisk run //tools/wall_profile -- [--out FILE] [--top N] -- CMD ARGS...

CMD is found on PATH or by path; its symbols come from nm, so an unstripped
binary gives function names. The profile is kept in FILE for a second look:

    bazelisk run //tools/wall_profile -- --summarize FILE --binary CMD
"""

import argparse
import bisect
import collections
import os
import shutil
import struct
import subprocess
import sys

_WORD = struct.Struct("<Q")


def read_profile(data):
    """(stacks, maps) of a gperftools legacy CPU profile.

    stacks is [(count, [pc, ...])], innermost frame first; maps is the
    /proc/self/maps text the profiler appends after the records.
    """

    def word(i):
        return _WORD.unpack_from(data, i * _WORD.size)[0]

    if len(data) < 5 * _WORD.size or word(0) != 0 or word(1) != 3:
        raise ValueError("not a gperftools CPU profile")
    i = 2 + word(1)
    stacks = []
    while True:
        count, depth = word(i), word(i + 1)
        pcs = [word(i + 2 + k) for k in range(depth)]
        i += 2 + depth
        if count == 0 and depth == 1 and pcs[0] == 0:
            break
        stacks.append((count, pcs))
    maps = data[i * _WORD.size :].decode("utf-8", errors="replace")
    return stacks, maps


def load_base(maps, binary):
    """Where binary is mapped, when it is position independent, else 0."""
    with open(binary, "rb") as f:
        header = f.read(18)
    if header[:4] != b"\x7fELF" or struct.unpack_from("<H", header, 16)[0] != 3:
        return 0  # not ET_DYN: addresses are as linked
    real = os.path.realpath(binary)
    for line in maps.splitlines():
        parts = line.split()
        if len(parts) >= 6 and os.path.realpath(parts[5]) == real:
            if int(parts[2], 16) == 0:
                return int(parts[0].split("-")[0], 16)
    return 0


def nm_symbols(binary):
    """Sorted [(address, name)] of binary's text symbols, demangled."""
    out = subprocess.run(
        ["nm", "-C", "--defined-only", binary],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    syms = []
    for line in out.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[1] in "tTwW":
            syms.append((int(parts[0], 16), parts[2]))
    syms.sort()
    return syms


def short_name(name):
    """A demangled name without its argument list."""
    if name.startswith("operator"):
        return name
    return name.split("(")[0]


def summarize(stacks, syms, base=0, top=40):
    """Report lines: inclusive and self share of the samples per function.

    A pc outside the binary's symbols (the kernel, libc, the profiler) is
    named by its address, so time in a system call stays visible.
    """
    addrs = [a for a, _ in syms]
    end = addrs[-1] if addrs else 0

    def name(pc):
        pc -= base
        k = bisect.bisect_right(addrs, pc - 1) - 1
        if k < 0 or pc > end + (1 << 20):
            return hex(pc + base)
        return short_name(syms[k][1])

    total = sum(c for c, _ in stacks)
    inclusive, own = collections.Counter(), collections.Counter()
    for count, pcs in stacks:
        names = [name(pc) for pc in pcs]
        own[names[0]] += count
        for n in set(names):
            inclusive[n] += count
    lines = [f"{total} samples"]
    if not total:
        return lines
    lines.append("-- inclusive")
    lines += [f"{100 * c / total:6.1f}% {n}" for n, c in inclusive.most_common(top)]
    lines.append("-- self")
    lines += [f"{100 * c / total:6.1f}% {n}" for n, c in own.most_common(top // 2)]
    return lines


def report(profile, binary, top):
    with open(profile, "rb") as f:
        stacks, maps = read_profile(f.read())
    base = load_base(maps, binary)
    print("\n".join(summarize(stacks, nm_symbols(binary), base, top)))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default="wall.prof", help="profile file")
    parser.add_argument("--top", type=int, default=40, help="functions shown")
    parser.add_argument("--frequency", type=int, default=1000, help="samples/s")
    parser.add_argument("--summarize", metavar="FILE", help="report FILE only")
    parser.add_argument("--binary", help="binary FILE profiled, for --summarize")
    parser.add_argument("cmd", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    cwd = os.environ.get("BUILD_WORKING_DIRECTORY", os.getcwd())
    out = os.path.join(cwd, args.out)
    if args.summarize:
        if not args.binary:
            parser.error("--summarize needs --binary")
        report(
            os.path.join(cwd, args.summarize), os.path.join(cwd, args.binary), args.top
        )
        return 0

    cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
    if not cmd:
        parser.error("no command to run")
    binary = cmd[0] if os.sep in cmd[0] else shutil.which(cmd[0])
    if binary is None:
        parser.error(f"{cmd[0]}: not found")
    binary = os.path.join(cwd, binary)
    lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libprofiler.so")
    env = dict(os.environ)
    env.update(
        LD_PRELOAD=lib,
        CPUPROFILE=out,
        CPUPROFILE_REALTIME="1",
        CPUPROFILE_FREQUENCY=str(args.frequency),
    )
    status = subprocess.run([binary] + cmd[1:], env=env, cwd=cwd).returncode
    if os.path.exists(out):
        report(out, binary, args.top)
        print(f"profile kept in {args.out}")
    else:
        print("no profile written: did the command exit through exit()?")
    return status


if __name__ == "__main__":
    sys.exit(main())
