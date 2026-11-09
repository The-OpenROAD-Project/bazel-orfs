"""The crossing ledger of a parent macro, joined: every part's halves of
its boundary pins (crossing_ledger.tcl, each part at its own global
route) summed along each crossing net into the clock period a path
through that net needs, before there is a top level to time it on.

    crossing_ledger.py --hub <ledger> --block <M>=<ledger>... [--budget <ps>] --out <dir>

A part's ledger holds, per boundary pin, in ps, routed and zero-wire:

    out <pin> <L> <L zero> <ft> <ft zero> <lat> <flags>
    in <pin> <C> <C zero> <flags>
    arc <in> <out> <d> <d zero> <complete|truncated>

L: launch, the slowest register behind an output, clock pin to the pin.
C: capture, an input pin to the slowest register behind it, setup
included. d: a feed-through, input pin to output pin. '-' where a pin
has none. Each is the worst of every register or pin behind the pin, so
no path through a pin needs more than its halves say.

The parts are connected by rule, as top_netlist.tcl stitches them: the
hub's port u_<M>__<pin> is block M's <pin>. The need of a crossing net
is the longest chain through it: the slowest launch that reaches its
driver, through any feed-throughs on the way, and the slowest capture
from its load on.

Writes <dir>/crossings.txt, one row per crossing net, worst first:

    net from_part to_part need need_zero need_hub_zero hub hub_zero
    partner allowance class flags chain

need: the chain as routed. need_zero: every part's wires at zero.
need_hub_zero: the hub's wires at zero, the other parts as routed, the
least the net can need while the blocks stay as they are. hub: the
hub's share of need; partner: the rest; allowance: the budget less
partner, what the hub may spend. class: ok (need within the budget),
closable-by-hub-placement (need_hub_zero within it),
not-closable-by-hub. And <dir>/summary.txt: the nets over the budget,
the hub's debt (ps over the budget, summed over the nets), a count per
class, and what the ledger could not see, by name: nets nothing
launches into, nets nothing captures, outputs whose feed-throughs were
cut at the K worst.
"""

import argparse
import os
import re
import sys

HUB = "hub"
ROUTED, ZERO, HUB_ZERO = "routed", "zero", "hub_zero"
EVALS = (ROUTED, ZERO, HUB_ZERO)

# top_netlist.tcl's rule for a parent port that is a block's pin
STITCH = re.compile(r"^u_([^_].*?)__(.*)$")


class LedgerError(Exception):
    pass


def number(text, where):
    if text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        raise LedgerError("%s: not a number: %s" % (where, text))


def pair(routed, zero, where):
    """A half, (routed, zero-wire), or None: a pin has it in both or in
    neither."""
    r, z = number(routed, where), number(zero, where)
    if (r is None) != (z is None):
        raise LedgerError("%s: routed %s, zero-wire %s" % (where, routed, zero))
    return None if r is None else (r, z)


def flags_of(text):
    return [] if text == "-" else text.split(",")


def read_part(name, path):
    """A part's ledger: its header, outs {pin: (launch, flags)}, ins
    {pin: (capture, flags)} and arcs {(in, out): (d, state)}."""
    part = {"name": name, "header": {}, "notes": [], "outs": {}, "ins": {}, "arcs": {}}
    try:
        f = open(path)
    except IOError as e:
        raise LedgerError("%s: no ledger: %s" % (name, e))
    with f:
        for n, line in enumerate(f, 1):
            where = "%s:%d" % (path, n)
            fields = line.split()
            if not fields:
                continue
            if fields[0] == "#":
                if len(fields) > 1 and fields[1] == "part":
                    part["header"] = dict(zip(fields[1::2], fields[2::2]))
                elif len(fields) > 1 and fields[1] == "note":
                    part["notes"].append(" ".join(fields[2:]))
                continue
            kind = fields[0]
            if kind == "out" and len(fields) == 8:
                pin = fields[1]
                launch = pair(fields[2], fields[3], where)
                part["outs"][pin] = (launch, flags_of(fields[7]))
            elif kind == "in" and len(fields) == 5:
                pin = fields[1]
                capture = pair(fields[2], fields[3], where)
                part["ins"][pin] = (capture, flags_of(fields[4]))
            elif kind == "arc" and len(fields) == 6:
                d = pair(fields[3], fields[4], where)
                if d is None:
                    raise LedgerError("%s: an arc without a delay" % where)
                part["arcs"][(fields[1], fields[2])] = (d, fields[5])
            else:
                raise LedgerError("%s: not a ledger line: %s" % (where, line.strip()))
    if not part["header"]:
        raise LedgerError("%s: %s has no '# part' line" % (name, path))
    for i, o in part["arcs"]:
        if i not in part["ins"] or o not in part["outs"]:
            raise LedgerError("%s: arc %s %s without both its pins" % (name, i, o))
    return part


def connect(hub, blocks):
    """The crossing nets, by the hub port's name: net -> (driver, load),
    each a (part, pin). And the hub's own ports, and the block pins the
    hub has no port for (top_netlist.tcl leaves them open)."""
    nets = {}
    own = []
    for port in sorted(list(hub["outs"]) + list(hub["ins"])):
        m = STITCH.match(port)
        if not m:
            own.append(port)
            continue
        block, pin = m.group(1), m.group(2)
        if block not in blocks:
            raise LedgerError(
                "hub port %s: no ledger for block %s (--block %s=<ledger>)"
                % (port, block, block)
            )
        b = blocks[block]
        if port in hub["ins"] and pin in b["outs"]:
            nets[port] = ((block, pin), (HUB, port))
        elif port in hub["outs"] and pin in b["ins"]:
            nets[port] = ((HUB, port), (block, pin))
        elif pin in b["outs"] or pin in b["ins"]:
            raise LedgerError(
                "hub port %s and %s's pin %s point the same way" % (port, block, pin)
            )
        else:
            raise LedgerError(
                "hub port %s: %s's ledger has no pin %s" % (port, block, pin)
            )
    open_pins = []
    for block in sorted(blocks):
        b = blocks[block]
        for pin in sorted(list(b["outs"]) + list(b["ins"])):
            if "u_%s__%s" % (block, pin) not in nets:
                open_pins.append("%s/%s" % (block, pin))
    return nets, own, open_pins


class Join(object):
    """The longest chain to each output pin (up) and from each input pin
    (down), over the parts' halves and feed-throughs."""

    def __init__(self, hub, blocks):
        self.parts = dict(blocks)
        self.parts[HUB] = hub
        self.nets, self.own, self.open_pins = connect(hub, blocks)
        self.driver = {}
        self.load = {}
        for net, (drv, load) in self.nets.items():
            self.driver[load] = drv
            self.load[drv] = load
        # a part's feed-throughs by the pin they end at, and start at
        self.into = {}
        self.outof = {}
        for name, part in self.parts.items():
            for (i, o), (d, state) in part["arcs"].items():
                self.into.setdefault((name, o), []).append((i, d, state))
                self.outof.setdefault((name, i), []).append((o, d, state))
        self.memo = {}
        self.walking = []

    def term(self, part, value, ev):
        """A half's time in an evaluation: the hub's wires at zero, the
        other parts as routed, in HUB_ZERO."""
        if ev == ZERO or (ev == HUB_ZERO and part == HUB):
            return value[1]
        return value[0]

    def chain(self, part, value, ev, flags, name):
        """A chain of one half: (need, the hub's share, flags, parts)."""
        t = self.term(part, value, ev)
        return (t, t if part == HUB else 0.0, list(flags), [name])

    def extend(self, a, b):
        return (
            a[0] + b[0],
            a[1] + b[1],
            a[2] + [f for f in b[2] if f not in a[2]],
            a[3] + b[3],
        )

    def walk(self, side, key, ev):
        memo = (side, key, ev)
        if memo in self.memo:
            return self.memo[memo]
        if (side, key) in self.walking:
            loop = self.walking[self.walking.index((side, key)) :]
            raise LedgerError(
                "a loop of feed-throughs: %s"
                % " ".join("%s/%s" % k for _, k in loop + [(side, key)])
            )
        self.walking.append((side, key))
        best = self.up(key, ev) if side == "up" else self.down(key, ev)
        self.walking.pop()
        self.memo[memo] = best
        return best

    def up(self, key, ev):
        """The slowest launch that reaches output pin key: its own
        registers', or one fed through from the pin driving an input."""
        name, pin = key
        launch, flags = self.parts[name]["outs"][pin]
        best = None
        if launch is not None:
            best = self.chain(name, launch, ev, flags, name)
        for i, d, state in self.into.get(key, []):
            drv = self.driver.get((name, i))
            # the design's own input port: no register launches it
            before = self.walk("up", drv, ev) if drv else None
            if before is None:
                continue
            cand = self.extend(before, self.chain(name, d, ev, [], name))
            if best is None or cand[0] > best[0]:
                best = cand
        if best is not None and any(
            s == "truncated" for _, _, s in self.into.get(key, [])
        ):
            best = self.extend(best, (0.0, 0.0, ["truncated"], []))
        return best

    def down(self, key, ev):
        """The slowest capture from input pin key on: its own registers',
        or one fed through to the pin an output drives."""
        name, pin = key
        capture, flags = self.parts[name]["ins"][pin]
        best = None
        if capture is not None:
            best = self.chain(name, capture, ev, flags, name)
        for o, d, state in self.outof.get(key, []):
            load = self.load.get((name, o))
            # the design's own output port: no register captures it
            after = self.walk("down", load, ev) if load else None
            if after is None:
                continue
            extra = ["truncated"] if state == "truncated" else []
            cand = self.extend(self.chain(name, d, ev, extra, name), after)
            if best is None or cand[0] > best[0]:
                best = cand
        return best

    def rows(self, budget):
        """A row per crossing net, worst first, and the nets with no
        launch or no capture half."""
        rows = []
        no_launch = []
        no_capture = []
        for net in sorted(self.nets):
            drv, load = self.nets[net]
            if self.walk("up", drv, ROUTED) is None:
                no_launch.append(net)
                continue
            if self.walk("down", load, ROUTED) is None:
                no_capture.append(net)
                continue
            got = {}
            for ev in EVALS:
                got[ev] = self.extend(
                    self.walk("up", drv, ev), self.walk("down", load, ev)
                )
            need, hub, flags, parts = got[ROUTED]
            partner = need - hub
            if need <= budget:
                kind = "ok"
            elif got[HUB_ZERO][0] <= budget:
                kind = "closable-by-hub-placement"
            else:
                kind = "not-closable-by-hub"
            rows.append(
                {
                    "net": net,
                    "from": drv[0],
                    "to": load[0],
                    "need": need,
                    "need_zero": got[ZERO][0],
                    "need_hub_zero": got[HUB_ZERO][0],
                    "hub": hub,
                    "hub_zero": got[HUB_ZERO][1],
                    "partner": partner,
                    "allowance": budget - partner,
                    "class": kind,
                    "flags": flags,
                    "chain": parts,
                }
            )
        rows.sort(key=lambda r: (-r["need"], r["net"]))
        return rows, no_launch, no_capture


CLASSES = ("ok", "closable-by-hub-placement", "not-closable-by-hub")


def some(names, limit=10):
    more = len(names) - limit
    return " ".join(names[:limit]) + (" and %d more" % more if more > 0 else "")


def join(hub_path, block_paths, budget):
    """The joined ledger: (rows, summary lines)."""
    hub = read_part(HUB, hub_path)
    blocks = {name: read_part(name, path) for name, path in block_paths.items()}
    j = Join(hub, blocks)
    rows, no_launch, no_capture = j.rows(budget)
    over = [r for r in rows if r["need"] > budget]
    lines = ["crossing ledger: %d nets, %d over %g ps" % (len(rows), len(over), budget)]
    if rows:
        lines.append("worst %s %.1f ps" % (rows[0]["net"], rows[0]["need"]))
    # a chain through two nets is in both rows, and in the debt twice
    lines.append(
        "hub debt %.1f ps: each net's ps over the budget, summed over the nets"
        % sum(r["need"] - budget for r in over)
    )
    for kind in CLASSES:
        lines.append("class %s %d" % (kind, sum(1 for r in rows if r["class"] == kind)))
    for flag in ("truncated", "mcp"):
        hit = [r["net"] for r in rows if flag in r["flags"]]
        if hit:
            lines.append("%s %d nets: %s" % (flag, len(hit), some(hit)))
    lines.append("no-launcher %d nets: nothing launches into them" % len(no_launch))
    if no_capture:
        lines.append(
            "no-capture %d nets, launched and never captured: %s"
            % (len(no_capture), some(no_capture))
        )
    else:
        lines.append("no-capture 0 nets")
    lines.append("own %d hub ports of the design's own" % len(j.own))
    if j.open_pins:
        lines.append(
            "open %d block pins the hub has no port for: %s"
            % (len(j.open_pins), some(j.open_pins))
        )
    for name in [HUB] + sorted(blocks):
        part = j.parts[name]
        h = part["header"]
        cut = sorted(
            set(o for (_, o), (_, s) in part["arcs"].items() if s == "truncated")
        )
        lines.append(
            "part %s: %s, period %s ps, clock slew %s ps, skew %s ps, "
            "%d outs, %d ins, %d feed-throughs%s"
            % (
                name,
                h.get("part", "?"),
                h.get("period", "?"),
                h.get("clk_slew", "?"),
                h.get("skew", "?"),
                len(part["outs"]),
                len(part["ins"]),
                len(part["arcs"]),
                (
                    ", %d outputs cut at the %s worst: %s"
                    % (len(cut), h.get("arcs_k", "?"), some(cut))
                    if cut
                    else ""
                ),
            )
        )
        for note in part["notes"]:
            lines.append("part %s note: %s" % (name, note))
    return rows, lines, no_capture


COLUMNS = (
    "net from_part to_part need need_zero need_hub_zero hub hub_zero "
    "partner allowance class flags chain"
)


def write(out_dir, rows, lines, budget):
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with open(os.path.join(out_dir, "crossings.txt"), "w") as f:
        f.write("# crossing nets, ps, budget %g ps, worst first\n" % budget)
        f.write("# %s\n" % COLUMNS)
        for r in rows:
            f.write(
                "%s %s %s %.1f %.1f %.1f %.1f %.1f %.1f %.1f %s %s %s\n"
                % (
                    r["net"],
                    r["from"],
                    r["to"],
                    r["need"],
                    r["need_zero"],
                    r["need_hub_zero"],
                    r["hub"],
                    r["hub_zero"],
                    r["partner"],
                    r["allowance"],
                    r["class"],
                    ",".join(r["flags"]) or "-",
                    ">".join(r["chain"]),
                )
            )
    with open(os.path.join(out_dir, "summary.txt"), "w") as f:
        f.write("".join(l + "\n" for l in lines))


def parse_blocks(items):
    blocks = {}
    for item in items:
        name, eq, path = item.partition("=")
        if not eq or not name or not path:
            raise LedgerError("--block %s: want <M>=<ledger>" % item)
        if name in blocks or name == HUB:
            raise LedgerError("--block %s: given twice" % name)
        blocks[name] = path
    return blocks


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hub", required=True, help="the hub's ledger")
    ap.add_argument("--block", action="append", default=[], metavar="M=LEDGER")
    ap.add_argument("--budget", type=float, default=2000.0, help="ps")
    ap.add_argument("--out", required=True, help="directory written")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="stop on a net that is launched and never captured",
    )
    args = ap.parse_args(argv)
    try:
        rows, lines, no_capture = join(args.hub, parse_blocks(args.block), args.budget)
    except LedgerError as e:
        sys.exit("crossing_ledger: %s" % e)
    write(args.out, rows, lines, args.budget)
    print("\n".join(lines))
    if args.strict and no_capture:
        sys.exit(
            "crossing_ledger: %d nets launched and never captured: %s"
            % (len(no_capture), some(no_capture))
        )


if __name__ == "__main__":
    main(sys.argv[1:])
