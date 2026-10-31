"""structgen's netlists simulated cell by cell against the toys' RTL, as
a reference model in Python, under random stimulus: the CAM and the
flags. Each has a negative control, the netlist with two of its output
bits swapped, which must mismatch: a simulator that compared nothing
would pass the plain check too."""

import random
import re
import sys
import unittest

import structgen

sys.setrecursionlimit(100000)

_ASSIGN = re.compile(r"^\s*assign (\S+) = (\S+);$")


def _fn(master, p):
    """A cell's output from its input pins' values."""
    kind = re.match(r"[A-Z]+[0-9]*", master).group(0)
    if kind.startswith("INV"):
        return 1 - p["A"]
    if kind.startswith("BUF"):
        return p["A"]
    if kind == "AND2":
        return p["A"] & p["B"]
    if kind == "OR2":
        return p["A"] | p["B"]
    if kind in ("NAND2", "NAND3"):
        return 1 - (p["A"] & p["B"] & p.get("C", 1))
    if kind in ("NOR2", "NOR3"):
        return 1 - (p["A"] | p["B"] | p.get("C", 0))
    if kind == "XOR2":
        return p["A"] ^ p["B"]
    if kind == "XNOR2":
        return 1 - (p["A"] ^ p["B"])
    if kind == "AO22":
        return (p["A1"] & p["A2"]) | (p["B1"] & p["B2"])
    if kind == "AO21":
        return (p["A1"] & p["A2"]) | p["B"]
    raise ValueError(f"no model for {master}")


class Sim:
    """A Netlist after buffer() and size(), clocked by step()."""

    def __init__(self, net, swap=None):
        self.cells = net.cells
        self.driver = {c[3]: k for k, c in enumerate(self.cells)}
        self.alias = {}
        for line in net.lines:
            m = _ASSIGN.match(line)
            if m:
                self.alias[m.group(1)] = m.group(2)
        if swap:
            a, b = swap
            self.alias[a], self.alias[b] = self.alias[b], self.alias[a]
        self.flops = [k for k, c in enumerate(self.cells) if c[0].startswith("DFF")]
        self.state = {k: 0 for k in self.flops}

    def value(self, name, inputs, memo):
        if name == "1'b0":
            return 0
        if name == "1'b1":
            return 1
        if name in memo:
            return memo[name]
        if name in inputs:
            v = inputs[name]
        elif name in self.alias:
            v = self.value(self.alias[name], inputs, memo)
        elif name in self.driver:
            k = self.driver[name]
            master, pins, _, _ = self.cells[k]
            if master.startswith("DFF"):
                v = 1 - self.state[k]  # QN
            else:
                v = _fn(
                    master,
                    {p: self.value(n, inputs, memo) for p, n in pins.items()},
                )
        else:
            raise KeyError(f"net {name} has no driver")
        memo[name] = v
        return v

    def step(self, inputs, outputs):
        """The outputs before the clock edge, then the edge."""
        memo = {}
        out = {o: self.value(o, inputs, memo) for o in outputs}
        nxt = {k: self.value(self.cells[k][1]["D"], inputs, memo) for k in self.flops}
        self.state = nxt
        return out


def _bus(name, w, v):
    return {f"{name}[{i}]": (v >> i) & 1 for i in range(w)}


def _get(out, name, w):
    return sum(out[f"{name}[{i}]"] << i for i in range(w))


def run_cam(depth, width, cycles, swap=None, seed=1):
    """Mismatches between the CAM netlist and its reference."""
    net = structgen.Netlist()
    structgen.cam(net, depth, width)
    net.buffer()
    net.size()
    sim = Sim(net, swap)
    a = structgen._abits(depth)
    rng = random.Random(seed)
    keys = [rng.randrange(1 << width) for _ in range(4)]
    k = [0] * depth
    outs = ["hit"] + [f"idx[{i}]" for i in range(a)]
    bad = 0
    for _ in range(cycles):
        w_en, w_addr = rng.randrange(2), rng.randrange(depth)
        w_key, key = rng.choice(keys), rng.choice(keys)
        inputs = {"w_en": w_en} | _bus("w_addr", a, w_addr)
        inputs |= _bus("w_key", width, w_key) | _bus("key", width, key)
        out = sim.step(inputs, outs)
        m = [i for i in range(depth) if k[i] == key]
        if out["hit"] != (1 if m else 0) or _get(out, "idx", a) != (m[0] if m else 0):
            bad += 1
        if w_en:
            k[w_addr] = w_key
    return bad


def run_flags(depth, width, cycles, swap=None, seed=1):
    """Mismatches between the flags netlist and its reference."""
    net = structgen.Netlist()
    structgen.flags(net, depth, width)
    net.buffer()
    net.size()
    sim = Sim(net, swap)
    a, b = structgen._abits(depth), structgen._abits(width)
    rng = random.Random(seed)
    f = [[0] * width for _ in range(depth)]
    outs = [f"r_data[{i}]" for i in range(width)]
    bad = 0
    for cycle in range(cycles):
        reset = 1 if cycle == 0 else int(rng.random() < 0.02)
        ins = {"reset": reset}
        ports = {}
        for p in ("s0", "s1", "c0", "c1"):
            ports[p] = (rng.randrange(2), rng.randrange(depth), rng.randrange(width))
            en, idx, bit = ports[p]
            ins |= {f"{p}_en": en} | _bus(f"{p}_idx", a, idx) | _bus(f"{p}_bit", b, bit)
        flush = int(rng.random() < 0.1)
        flush_idx, head = rng.randrange(depth), rng.randrange(depth)
        r_addr = rng.randrange(depth)
        ins |= {"flush": flush} | _bus("flush_idx", a, flush_idx)
        ins |= _bus("head", a, head) | _bus("r_addr", a, r_addr)
        out = sim.step(ins, outs)
        if _get(out, "r_data", width) != sum(f[r_addr][i] << i for i in range(width)):
            bad += 1
        # the RTL's update, in its order
        if reset:
            f = [[0] * width for _ in range(depth)]
            continue
        for p, val in (("s0", 1), ("s1", 1), ("c0", 0), ("c1", 0)):
            en, idx, bit = ports[p]
            if en:
                f[idx][bit] = val
        if flush:
            mask = (1 << a) - 1
            for i in range(depth):
                if ((i - head) & mask) >= ((flush_idx - head) & mask):
                    f[i] = [0] * width
    return bad


class StructgenTest(unittest.TestCase):
    def test_cam(self):
        self.assertEqual(run_cam(32, 8, 400), 0)

    def test_cam_mutated(self):
        self.assertGreater(run_cam(32, 8, 400, swap=("idx[0]", "idx[1]")), 0)

    def test_flags(self):
        self.assertEqual(run_flags(32, 8, 400), 0)

    def test_flags_mutated(self):
        self.assertGreater(run_flags(32, 8, 400, swap=("r_data[0]", "r_data[1]")), 0)


if __name__ == "__main__":
    unittest.main()
