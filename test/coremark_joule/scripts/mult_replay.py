#!/usr/bin/env python3
"""Turn a recorded module boundary into a standalone replay testbench.

5.2's whole-core timing-annotated simulation does not work and, where it
does run, runs at a few cycles per second -- so reaching the cycles where
CoreMark multiplies costs hours before anything is measured. But the
multiplier is a preserved module in the hardened netlist, its per-instance
delays are in the same SDF the whole design's are, and every one of its
port values is already recorded in the zero-delay run's dump. So the
module can be simulated on its own, with the real cells and the real
delays, driven by exactly what the core drove it with.

Nothing here re-synthesizes anything. A standalone hardening of the
multiplier would give a different netlist -- different context, different
cell choices, its own clock tree and parasitics -- and the bound wanted
is on the multiplier this study actually reports power for.

What is replayed, and what is not:

- the clock leaves are driven by the testbench, because the buffers that
  drive them are outside the module and their delays are not in its SDF;
- every other input is replayed per cycle from the dump, promoted nets
  included. Those are buffered copies of reset and of data signals that
  optimization pushed through the module boundary, and inventing them
  would be inventing the module's inputs;
- the outputs are replayed too, as an oracle: an arm that does not
  reproduce them is not measuring the same work.

The limitation this cannot escape: inputs arrive at the cycle boundary
as the dump records them, not staggered as they arrive in the core. So
what it measures is the glitch the partial-product tree generates from
its own path imbalance, which is the bound wanted, and not the glitch
injected at its boundary.
"""

import argparse
import sys

CLOCK_MARK = "clknet"


def read_ports(path):
    """(direction, name, width, spelling), in the order the netlist declares.

    The spelling is the netlist's own, escape and all: a dump names a
    port unescaped, a netlist may not, and a generated instantiation has
    to use the netlist's.
    """
    ports = []
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 3:
                spelling = parts[3] if len(parts) > 3 else parts[1]
                ports.append((parts[0], parts[1], int(parts[2]), spelling))
    return ports


def declare(spelling):
    """An identifier as Verilog needs it written: escaped names take a space."""
    return spelling + " " if spelling.startswith("\\") else spelling


def parse_header(stream):
    """name -> identifier, for $var lines at any scope depth.

    Keyed by name, not by identifier. A VCD gives one identifier to every
    name of the same net, so an identifier -> name map keeps whichever
    alias was declared first and loses the rest -- and a port that lost
    that race then matches nothing and silently keeps its initial value.
    That is how `rst_ni` came through as 0 for a whole window: the
    multiplier sat in reset, its state machine never advanced, and only
    the one output that depends on state rather than on inputs was
    wrong.
    """
    names = {}
    for line in stream:
        s = line.strip()
        if s.startswith("$var"):
            parts = s.split()
            if len(parts) >= 5:
                names.setdefault(parts[4], parts[3])
        elif s.startswith("$enddefinitions"):
            return names
    return names


def normalize(value, width):
    """A VCD value as a fixed-width binary string, plus its unknown bits.

    The unknown bits are returned per position rather than as a flag.
    A bit that is X in every change carries no information and becomes a
    constant either way, so it can neither lose the replay anything nor
    contribute a transition to either arm; a bit that is X only
    sometimes is a real difference between the replay and the recording.
    Collapsing the two into one flag hides exactly that distinction.
    """
    value = value.lower()
    if len(value) < width:
        pad = value[0] if value and value[0] in "xz" else "0"
        value = pad * (width - len(value)) + value
    elif len(value) > width:
        value = value[-width:]
    mask = [i for i, c in enumerate(value) if c in "xz"]
    return value.replace("x", "0").replace("z", "0"), mask


def sample(stream, ports, clock):
    """Snapshot every port at each clock posedge, after that instant's events.

    A zero-delay dump puts the edge and everything it causes at one
    timestamp, so the snapshot has to be taken once the whole timestamp
    is consumed -- sampling mid-block would catch the design halfway
    through settling.
    """
    by_name = parse_header(stream)
    width = {n: w for _, n, w, _ in ports}

    # Every port has to be found. A port the dump does not name would
    # otherwise keep the zero it was initialised with, and drive the
    # replay with a value the recording never held.
    absent = [n for _, n, _, _ in ports if n not in by_name]
    if absent:
        raise ValueError(
            "%d port(s) are not in the dump, which would replay as 0: %s"
            % (len(absent), ", ".join(absent[:8])))

    wanted = {by_name[n]: n for _, n, _, _ in ports}
    clock_id = by_name.get(clock)
    if clock_id is None:
        raise ValueError("clock %r is not in the dump" % clock)

    values = {n: "0" * width[n] for _, n, _, _ in ports}
    # Whether the value a port currently holds was recorded as X or Z.
    # Snapshotted with the values, because "this port was unknown at
    # some point in the window" and "this port was unknown during the
    # cycles being measured" are different claims, and only the second
    # one says whether a replay of those cycles is exact.
    unknown_now = {n: False for _, n, _, _ in ports}
    rows, masks, unknown_ports = [], [], {}
    pending_edge = False
    clock_now = "0"

    def flush():
        rows.append(dict(values))
        masks.append({n for n, u in unknown_now.items() if u})

    for line in stream:
        s = line.strip()
        if not s:
            continue
        if s[0] == "#":
            if pending_edge:
                flush()
                pending_edge = False
            continue
        if s[0] in "bBrR":
            parts = s.split()
            if len(parts) != 2:
                continue
            val, ident = parts[0][1:], parts[1]
        elif s[0] in "01xzXZ":
            val, ident = s[0], s[1:]
        else:
            continue
        if ident == clock_id:
            if clock_now == "0" and val == "1":
                pending_edge = True
            clock_now = val
            if ident not in wanted:
                continue
        name = wanted.get(ident)
        if name is None:
            continue
        clean, mask = normalize(val, width[name])
        counts = unknown_ports.setdefault(name, {"changes": 0, "bits": {}})
        counts["changes"] += 1
        for i in mask:
            bit = width[name] - 1 - i
            counts["bits"][bit] = counts["bits"].get(bit, 0) + 1
        values[name] = clean
        unknown_now[name] = bool(mask)
    if pending_edge:
        flush()
    return rows, masks, unknown_ports


def pack(rows, ports, keep):
    """One hex word per cycle, ports concatenated MSB-first in declared order."""
    selected = [(n, w, s) for d, n, w, s in ports if keep(d, n)]
    total = sum(w for _, w, _ in selected)
    out = []
    for row in rows:
        bits = "".join(row[n] for n, _, _ in selected)
        out.append("%0*x" % ((total + 3) // 4, int(bits, 2) if bits else 0))
    return out, selected, total


def testbench(module, ports, n_in, n_out, cycles, period_ps, unknown_out_bits):
    """A self-contained replay testbench, generated because the ports are the design.

    The module is instantiated from the hardened netlist by its own
    escaped name, so nothing is re-synthesized and nothing is retyped.
    """
    ins = [(n, w, s) for d, n, w, s in ports if is_input(d, n)]
    clocks = [(n, s) for d, n, w, s in ports
              if d == "input" and CLOCK_MARK in n]
    outs = [(n, w, s) for d, n, w, s in ports if d == "output"]

    lines = ["/* Generated by mult_replay.py -- do not edit.",
             " *",
             " * The multiplier of the hardened ibex netlist, replayed on its own",
             " * from the boundary the whole-core zero-delay run recorded (5.2).",
             " * With +sdf it carries that design's own per-instance delays; the",
             " * difference between the two arms is the glitch.",
             " */",
             "`timescale 1ps / 1ps",
             "",
             "module tb_mult_replay;",
             "  localparam int unsigned PeriodPs = %d;" % period_ps,
             "  localparam int unsigned NCycles  = %d;" % cycles,
             "",
             "  logic clk = 1'b0;",
             "  logic [%d:0] stim   [0:NCycles-1];" % (n_in - 1),
             "  logic [%d:0] want   [0:NCycles-1];" % (n_out - 1),
             "  logic [%d:0] cur = '0;" % (n_in - 1),
             "  logic [%d:0] got;" % (n_out - 1),
             "  /* Bits that were X in every recorded change: unused, and",
             "   * compared against nothing rather than compared against X. */",
             "  localparam logic [%d:0] OutMask = %d'b%s;"
             % (n_out - 1, n_out,
                "".join("0" if i in unknown_out_bits else "1"
                        for i in range(n_out - 1, -1, -1))),
             "  int unsigned n, mismatches = 0;",
             "  string sdf_file, vcd_file, stim_file, want_file;",
             ""]
    a = lines.append

    hi = n_in - 1
    for name, w, spelling in ins:
        a("  wire %s%s = cur[%d:%d];"
          % ("[%d:0] " % (w - 1) if w > 1 else "", name, hi, hi - w + 1))
        hi -= w
    a("")
    for name, spelling in clocks:
        a("  wire %s = clk;" % name)
    a("")
    for name, w, spelling in outs:
        a("  wire %s%s;" % ("[%d:0] " % (w - 1) if w > 1 else "", name))
    a("")
    a("  %s dut (" % declare(module))
    conns = ["      .%s(%s)" % (declare(s).rstrip() if not s.startswith("\\")
                                else s + " ", n)
             for d, n, w, s in ports]
    a(",\n".join(conns))
    a("  );")
    a("")
    a("  always #(PeriodPs / 2) clk = ~clk;")
    a("")
    a("  initial begin")
    a("    if (!$value$plusargs(\"stim=%s\", stim_file)) stim_file = \"stim.hex\";")
    a("    if (!$value$plusargs(\"expect=%s\", want_file))")
    a("      want_file = \"expect.hex\";")
    a("    $readmemh(stim_file, stim);")
    a("    $readmemh(want_file, want);")
    a("    /* Before any edge: a delay annotated after the design has")
    a("     * started is a delay that did not apply to what came before. */")
    a("    if ($value$plusargs(\"sdf=%s\", sdf_file)) $sdf_annotate(sdf_file, dut);")
    a("    if ($value$plusargs(\"vcd=%s\", vcd_file)) begin")
    a("      $dumpfile(vcd_file);")
    a("      $dumpvars(0, tb_mult_replay);")
    a("    end")
    a("    for (n = 0; n < NCycles; n++) begin")
    a("      @(posedge clk);")
    a("      /* A picosecond after the edge, not on it. Driving an input")
    a("       * at the instant the flops capture is a race, and which way")
    a("       * it resolves is a property of the netlist rather than of")
    a("       * the design: the same testbench reproduced one hardening")
    a("       * exactly and lost a `valid` pulse per multiply on the")
    a("       * next. It is also what the core does -- these inputs come")
    a("       * from flops elsewhere, so they arrive after the edge, not")
    a("       * on it. */")
    a("      #1 cur = stim[n];")
    a("      /* Checked near the end of the cycle, once the annotated arm")
    a("       * has had almost a whole period to settle. */")
    a("      #(PeriodPs - PeriodPs / 8);")
    a("      got = {%s};" % ", ".join(n for n, _, _ in outs))
    a("      if ((got & OutMask) !== (want[n] & OutMask))")
    a("        mismatches = mismatches + 1;")
    a("    end")
    a("    $display(\"tb_mult_replay: %0d cycles, %0d output mismatches%s\",")
    a("             NCycles, mismatches, sdf_file != \"\" ? \" (SDF)\" : \" (zero delay)\");")
    a("    $finish;")
    a("  end")
    a("endmodule")
    return "\n".join(lines) + "\n"


def count_words(path):
    """Cycles in a packed stimulus file: one hex word a cycle."""
    with open(path) as f:
        return sum(1 for line in f if line.strip())


def generate_only(args, ports):
    """Write just the testbench, sized by an existing stimulus file."""
    cycles = count_words(args.stim)
    n_in = sum(w for d, n, w, _ in ports if is_input(d, n))
    n_out = sum(w for d, n, w, _ in ports if d == "output")
    with open(args.module) as f:
        module = f.read().strip()
    unknown_out_bits = set()
    if args.unknown_out_bits:
        unknown_out_bits = {int(b) for b in args.unknown_out_bits.split(",") if b}
    with open(args.tb, "w") as f:
        f.write(testbench(module, ports, n_in, n_out, cycles,
                          args.period_ps, unknown_out_bits))
    sys.stdout.write(
        "mult_replay: testbench for %d cycles, %d stimulus bits, %d "
        "expected bits -> %s\n" % (cycles, n_in, n_out, args.tb))
    return 0


def is_input(direction, name):
    """Replayed inputs: everything but the clock leaves the testbench drives."""
    return direction == "input" and CLOCK_MARK not in name


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vcd", help="the recording to sample. Omit to "
                    "generate only the testbench, against an existing --stim.")
    ap.add_argument("--ports", required=True)
    ap.add_argument("--clock", help="the clock to sample on; required with --vcd")
    ap.add_argument("--stim", required=True)
    ap.add_argument("--expect", required=True)
    ap.add_argument("--only-busy", action="store_true",
                    help="emit only the cycles the unit is working, "
                         "back to back: the 100 %% duty upper bound")
    ap.add_argument("--busy", default="mult_en_i",
                    help="port whose high level marks a cycle of real work")
    ap.add_argument("--tb", help="where to write the generated testbench")
    ap.add_argument("--module", help="file naming the netlist module to instantiate")
    ap.add_argument("--period-ps", type=int, default=1282)
    ap.add_argument("--unknown-out-bits", default="",
                    help="comma-separated packed output bit positions to "
                         "exclude from the oracle, for the generate-only path")
    ap.add_argument("--report", help="where to write the packing description")
    args = ap.parse_args(argv)

    ports = read_ports(args.ports)

    if not args.vcd:
        # Generating the testbench against a stimulus that was recorded
        # earlier. The recording is the expensive half -- it needs a
        # whole-core run to reach the cycles worth measuring -- so it is
        # committed, and the testbench that consumes it is generated
        # from the netlist every time, where it cannot go stale.
        return generate_only(args, ports)

    with open(args.vcd, errors="replace") as f:
        rows, masks, unknown = sample(f, ports, args.clock)

    if args.only_busy:
        # The upper bound: the unit's own working cycles, concatenated,
        # with the idle cycles between bursts taken out. For this
        # multiplier that is a reachable operating point rather than a
        # fiction -- a multiply occupies it for three cycles, so a
        # stream of them saturates it. The recorded outputs are not an
        # oracle for this arm: removing the idle cycles changes what the
        # module's own flops see, which is the point of the arm.
        keep = [i for i, r in enumerate(rows) if r.get(args.busy) == "1"]
        rows = [rows[i] for i in keep]
        masks = [masks[i] for i in keep]

    stim, in_sel, n_in = pack(rows, ports, is_input)
    exp, out_sel, n_out = pack(rows, ports, lambda d, n: d == "output")
    with open(args.stim, "w") as f:
        f.write("\n".join(stim) + "\n")
    with open(args.expect, "w") as f:
        f.write("\n".join(exp) + "\n")

    text = ["cycles sampled: %d" % len(rows),
            "stimulus ports: %d (%d bits)" % (len(in_sel), n_in),
            "expected ports: %d (%d bits)" % (len(out_sel), n_out)]
    inputs = {n for d, n, _, _ in ports if is_input(d, n)}
    busy = [i for i, r in enumerate(rows) if r.get(args.busy) == "1"]
    text.append("%s high on %d of %d cycles" % (args.busy, len(busy), len(rows)))
    always, sometimes = [], []
    for name, counts in sorted(unknown.items()):
        for bit, n in sorted(counts["bits"].items()):
            row = (name, bit, n, counts["changes"],
                   "input" if name in inputs else "output")
            (always if n == counts["changes"] else sometimes).append(row)
    if always:
        text.append("bits unknown in every change -- constant, so no "
                    "information is lost and no transition is counted:")
        for name, bit, n, of, where in always:
            text.append("  %-24s[%2d] %-6s %d of %d changes"
                        % (name, bit, where, n, of))
    if sometimes:
        text.append("bits unknown in SOME changes -- the replay differs "
                    "from the recording here:")
        for name, bit, n, of, where in sometimes:
            text.append("  %-24s[%2d] %-6s %d of %d changes"
                        % (name, bit, where, n, of))
    if not always and not sometimes:
        text.append("no port ever carried X or Z")
    if args.tb:
        with open(args.module) as f:
            module = f.read().strip()
        unknown_out_bits = set()
        offset = n_out
        for name, w, _ in out_sel:
            offset -= w
            for bit in unknown.get(name, {}).get("bits", {}):
                unknown_out_bits.add(offset + bit)
        with open(args.tb, "w") as f:
            f.write(testbench(module, ports, n_in, n_out, len(rows),
                              args.period_ps, unknown_out_bits))
        text.append("testbench: %s" % args.tb)

    report = "\n".join(text) + "\n"
    if args.report:
        with open(args.report, "w") as f:
            f.write(report)
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
