"""A block abstract's ports carry their design-rule limits.

A parent's repair_design buffers a net when it sees a max_transition or
max_capacitance violation on it. A net whose only driver and loads are
block ports has no cell of the parent's on it, so the limits have to come
from the abstract: max_transition on each input, from the cells it loads
inside the block, max_capacitance on each output, from its driver. On
XiangShan's tile the abstracts carried neither, and a 2.4 mm net between
two blocks stayed a bare wire at a 6 ns slew, 1.9 ns of the worst path
(OpenROAD patch 0008).

Usage: drv_limits_test.py <block> <abstract.lib> [...]
"""

import re
import sys
import unittest


def ports(path):
    """{signal pin: (direction, max_transition or None, max_capacitance or None)}.

    A pin without a timing arc is a supply (VDD, VSS) and has no limits.
    """
    with open(path) as f:
        text = f.read()
    out = {}
    for m in re.finditer(r'\n    pin\("([^"]+)"\)\s*\{(.*?)\n    \}', text, re.S):
        body = m.group(2)
        if "timing()" not in body:
            continue
        direction = re.search(r"direction\s*:\s*(\w+)", body).group(1)
        tran = re.search(r"max_transition\s*:\s*([0-9.]+)", body)
        cap = re.search(r"max_capacitance\s*:\s*([0-9.]+)", body)
        out[m.group(1)] = (
            direction,
            float(tran.group(1)) if tran else None,
            float(cap.group(1)) if cap else None,
        )
    return out


ARGS = sys.argv[1:]


class DrvLimitsTest(unittest.TestCase):
    def test_every_port_has_its_limit(self):
        self.assertTrue(ARGS and len(ARGS) % 2 == 0, "block, abstract.lib ...")
        for i in range(0, len(ARGS), 2):
            block, lib = ARGS[i : i + 2]
            found = ports(lib)
            with self.subTest(block=block):
                self.assertTrue(found, "%s: no pins" % lib)
                inputs = [p for p, (d, _, _) in found.items() if d == "input"]
                outputs = [p for p, (d, _, _) in found.items() if d == "output"]
                self.assertTrue(inputs and outputs)
                for p in inputs:
                    tran = found[p][1]
                    self.assertIsNotNone(tran, "%s %s: no max_transition" % (block, p))
                    self.assertGreater(tran, 0.0, "%s %s" % (block, p))
                for p in outputs:
                    cap = found[p][2]
                    self.assertIsNotNone(cap, "%s %s: no max_capacitance" % (block, p))
                    self.assertGreater(cap, 0.0, "%s %s" % (block, p))
                print("%s: %d inputs, %d outputs, all limited" % (block, len(inputs), len(outputs)))


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
